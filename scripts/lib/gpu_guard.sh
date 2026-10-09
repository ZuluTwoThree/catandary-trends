#!/usr/bin/env bash
# Gemeinsamer Kollisionswächter der GPU-Cron-Wrapper (#98, 2026-09-05).
#
# Ein llama-server auf :8090 gehört immer genau EINEM Job. Jeder GPU-Handover
# (pipeline/gpu_handover.py) stoppt die systemd-Unit und startet sie mit seinem
# Modell — läuft parallel ein zweiter Job, zieht er dem ersten das Modell unter
# den Requests weg. Vorfall 2026-09-05: der Samstags-Ingester ersetzte den
# Gemma-Server eines noch laufenden Full Cycles durch den Embedding-Server;
# Stage 6 generierte gegen das Embedding-Modell, und beim Abbruch stoppte der
# Cycle den Embedding-Server der Ingester → 2.275 Distill-Aufrufe mit
# Connection refused.
#
# Nutzung in einem Wrapper (nach `cd "$REPO"`):
#     source "$REPO/scripts/lib/gpu_guard.sh"
#     if gpu_guard_wait weekly_ingesters; then <GPU-Schritt>; else <Skip + Note>; fi
#
#   gpu_guard_wait <job> [max_min]
#       Wartet, bis kein FREMDER bekannter GPU-Job mehr läuft. Default-Wartezeit
#       GPU_GUARD_MAX_MIN=90 (Minuten), Poll-Intervall GPU_GUARD_POLL_SEC=60.
#       rc 0 = frei, rc 1 = nach Ablauf immer noch belegt → GPU-Schritt SKIPPEN,
#       CPU-/Netz-Schritte laufen weiter. Loggt die blockierenden Prozesse.
#   gpu_guard_busy
#       Ohne Warten: rc 0 + Zeilen "pid kommandozeile", wenn ein fremder GPU-Job
#       läuft; rc 1 wenn frei.
#   gpu_guard_note <job> <status> [key=value ...]
#       Schreibt data/<job>_last.json (date=UTC-ISO, job, status, + Felder;
#       Ganzzahlen werden als Zahl gespeichert) — scripts/review_notify.py
#       nimmt frische Notizen in die Morgen-Mail auf.
#   llama_unit_record_owner <job> / llama_unit_stop_owned <job>
#       Besitzvermerk data/llama-server.<job>.pid ("MAINPID OWNERPID") für die
#       systemd-Unit; stop_owned stoppt die Unit NUR, wenn ihre MainPID noch die
#       vermerkte ist — ein fremder Server bleibt stehen (Warnung im Log).
#       Gleiches Format wie pipeline.gpu_handover (Python-Handover).
#
# "Fremd" = jeder Prozess, dessen Kommandozeile eines der GPU_GUARD_PATTERNS
# trifft und der weder der Aufrufer selbst, einer seiner Vorfahren (die
# cron-Shell) noch einer seiner Nachkommen ($(...)-Subshells) ist. Die
# Prozessliste kommt von `pgrep` aus dem PATH — die Tests schieben ein
# Fake-pgrep davor (tests/test_gpu_guard.py).

# Bekannte GPU-Jobs (ERE für pgrep -f). Reihenfolge egal; Ergänzungen hier,
# nicht in den Wrappern.
GPU_GUARD_PATTERNS="${GPU_GUARD_PATTERNS:-scheduled_cycle\.sh|full_cycle_cron\.sh|run_full_cycle|resume_cycle\.sh|signal_batch|weekly_ingesters\.sh|monthly_startup_sources\.sh|research_pulse|field_research|newsletter_deep_dive|newsletter_generator|weekly_newsletter_publish\.sh|newsletter_tonight\.sh|history_embed\.py work.*--handover}"
GPU_GUARD_MAX_MIN="${GPU_GUARD_MAX_MIN:-90}"
# Ruhezustand von :8090 (Owner 04.10.2026): das 8B schlank (-c 32768 = 4 Slots x 8 192, ~7,6 GB) statt der
# 24-Slot-Arbeitskonfiguration (~22 GB). Zwilling von
# pipeline.gpu_handover.CANONICAL_RESTING_SCRIPT (Test pinnt beide); die Wrapper stellen
# ihn am Ende her, der Handover holt sich fuer Stufen 2-4/8 selbst das Arbeitsskript.
LLAMA_REST_SCRIPT="${LLAMA_REST_SCRIPT:-start-qwen3-8b.sh}"
# Fremde VRAM-Nutzer, die der Cycle-Wrapper vor dem Nachtlauf beenden darf (ERE auf den
# Prozessnamen aus nvidia-smi). Owner 04.10.: nemo-speech und whisper-server werden
# waehrend des Pipeline-Laufs nicht gebraucht; ohne das passt das 22-GB-8B nicht neben
# ihre ~4,8 GB. Leer = nichts beenden.
GPU_EVICT_PATTERNS="${GPU_EVICT_PATTERNS:-nemo-speech|whisper-server}"
# Seit 2026-10-09 (Owner: 16 Fächer fürs 8B) stoppt der Nachtlauf diese Anwendungen NICHT mehr —
# das 8B braucht 16,2 statt ~22 GB und passt daneben. Die Liste bleibt: der Ops-Wächter zählt
# sie als bekannt (ops_probe.gpu_evict_patterns). GPU_EVICT_DAY_APPS=1 stellt das Stoppen wieder an
# (nötig, wenn LLAMA_8B_WORK_SCRIPT=start-qwen3-8b-208k.sh, 24 Fächer).
GPU_EVICT_DAY_APPS="${GPU_EVICT_DAY_APPS:-0}"
GPU_GUARD_POLL_SEC="${GPU_GUARD_POLL_SEC:-60}"
GPU_GUARD_DATA_DIR="${GPU_GUARD_DATA_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." 2>/dev/null && pwd)/data}"
# Vermerk der vor dem Nachtlauf gestoppten Docker-Container (gpu_evict_pid/gpu_evict_restore).
GPU_EVICT_STATE="${GPU_EVICT_STATE:-$GPU_GUARD_DATA_DIR/gpu_evicted_containers}"
GPU_PROC_ROOT="${GPU_PROC_ROOT:-/proc}"
LLAMA_SERVER_UNIT="${LLAMA_SERVER_UNIT:-llama-server.service}"

_gpu_guard_ppid() { ps -o ppid= -p "$1" 2>/dev/null | tr -d ' '; }

# Eigene PID + alle Vorfahren (bis PID 1), eine je Zeile.
_gpu_guard_chain() {
  local p="$1" guard=0
  while [ -n "$p" ] && [ "$p" -gt 1 ] 2>/dev/null && [ "$guard" -lt 64 ]; do
    echo "$p"
    p=$(_gpu_guard_ppid "$p")
    guard=$((guard + 1))
  done
}

# rc 0, wenn $1 ein Nachkomme von $2 ist (Elternkette von $1 erreicht $2).
_gpu_guard_descends_from() {
  local p guard=0
  p=$(_gpu_guard_ppid "$1")
  while [ -n "$p" ] && [ "$p" -gt 1 ] 2>/dev/null && [ "$guard" -lt 64 ]; do
    [ "$p" = "$2" ] && return 0
    p=$(_gpu_guard_ppid "$p")
    guard=$((guard + 1))
  done
  return 1
}

gpu_guard_busy() {
  local pids own_chain c args found=1
  pids=$(pgrep -f "$GPU_GUARD_PATTERNS" 2>/dev/null) || return 1
  own_chain=" $(_gpu_guard_chain "$$" | tr '\n' ' ') "
  for c in $pids; do
    [ -d "/proc/$c" ] || continue                            # schon beendet (z. B. die $(pgrep)-Subshell)
    case "$own_chain" in *" $c "*) continue ;; esac        # selbst / Vorfahre
    _gpu_guard_descends_from "$c" "$$" && continue           # eigener Kindprozess
    args=$(ps -o args= -p "$c" 2>/dev/null)
    # Fehltreffer ausschliessen (2026-09-05: ein Claude-Code-Wecker mit dem Text
    # "full_cycle_cron.sh" in seiner Kommandozeile hielt den Publish 90 min auf):
    # Tool-Shells, Editoren, grep/pgrep/tail selbst — alles, was den Namen nur zitiert.
    case "$args" in
      *shell-snapshots*|*"pgrep "*|*"grep "*|*"tail "*|*" vi "*|*" vim "*|*" nano "*|*" less "*) continue ;;
    esac
    echo "$c $(printf '%s' "$args" | cut -c1-140)"
    found=0
  done
  return "$found"
}

gpu_guard_wait() {
  local job="${1:-gpu-job}" max_min="${2:-$GPU_GUARD_MAX_MIN}"
  local poll="$GPU_GUARD_POLL_SEC" deadline waited=0 busy
  deadline=$(( $(date +%s) + max_min * 60 ))
  while busy=$(gpu_guard_busy); do
    if [ "$waited" -eq 0 ]; then
      echo "[gpu_guard/$job] fremder GPU-Job aktiv — warte (max ${max_min} min):"
      echo "$busy" | sed 's/^/    /'
    fi
    if [ "$(date +%s)" -ge "$deadline" ]; then
      echo "[gpu_guard/$job] SKIP: nach ${max_min} min immer noch belegt durch:"
      echo "$busy" | sed 's/^/    /'
      return 1
    fi
    sleep "$poll"
    waited=$((waited + 1))
  done
  if [ "$waited" -gt 0 ]; then
    echo "[gpu_guard/$job] frei nach ~$(( waited * poll / 60 )) min — weiter"
  fi
  return 0
}

gpu_guard_note() {
  local job="$1" status="$2"; shift 2
  mkdir -p "$GPU_GUARD_DATA_DIR" 2>/dev/null
  "${GPU_GUARD_PY:-python3}" - "$GPU_GUARD_DATA_DIR/${job}_last.json" "$job" "$status" "$@" <<'PY'
import json, sys
from datetime import datetime, timezone
path, job, status, *kv = sys.argv[1:]
note = {"date": datetime.now(timezone.utc).isoformat(), "job": job, "status": status}
for item in kv:
    k, _, v = item.partition("=")
    note[k] = int(v) if v.lstrip("-").isdigit() else v
with open(path, "w", encoding="utf-8") as fh:
    json.dump(note, fh, ensure_ascii=False, indent=2)
print(f"[gpu_guard/{job}] note → {path} ({status})")
PY
}

# ---- Besitz der systemd-Unit (Cleanup nur eigene Server, #98 c) --------------

llama_unit_owner_file() { echo "$GPU_GUARD_DATA_DIR/llama-server.$1.pid"; }

llama_unit_main_pid() {
  systemctl --user show -p MainPID --value "$LLAMA_SERVER_UNIT" 2>/dev/null | tr -d ' '
}

llama_unit_record_owner() {
  local job="$1" pid
  pid=$(llama_unit_main_pid)
  if [ -n "$pid" ] && [ "$pid" != "0" ]; then
    mkdir -p "$GPU_GUARD_DATA_DIR" 2>/dev/null
    echo "$pid $$" > "$(llama_unit_owner_file "$job")"
    echo "[gpu_guard/$job] llama-server PID $pid gehört jetzt diesem Job"
  else
    echo "[gpu_guard/$job] WARN: MainPID der Unit unbekannt — kein Besitzvermerk"
  fi
}

llama_unit_stop_owned() {
  local job="$1" f cur rec
  f=$(llama_unit_owner_file "$job")
  cur=$(llama_unit_main_pid)
  rec=$(awk '{print $1}' "$f" 2>/dev/null)
  if [ -z "$cur" ] || [ "$cur" = "0" ]; then
    rm -f "$f"; return 0                                  # läuft nicht (mehr)
  fi
  if [ -z "$rec" ]; then
    echo "[gpu_guard/$job] kein Besitzvermerk — stoppe die Unit (Altverhalten)"
    systemctl --user stop "$LLAMA_SERVER_UNIT"; return $?
  fi
  if [ "$cur" = "$rec" ]; then
    systemctl --user stop "$LLAMA_SERVER_UNIT"
    local rc=$?
    rm -f "$f"
    echo "[gpu_guard/$job] eigenen llama-server (PID $cur) gestoppt"
    return "$rc"
  fi
  echo "[gpu_guard/$job] WARN: llama-server PID $cur gehört nicht diesem Job (unsere war $rec) — bleibt stehen"
  rm -f "$f"
  return 0
}


# --- Tagesanwendungen vor dem Nachtlauf freiräumen (seit 2026-10-07) ---------------
# nemo-speech und whisper-server laufen in Docker-Containern als root mit
# restart=unless-stopped. Ein `kill` als normaler Benutzer scheitert still (fremder
# Benutzer), und selbst ein erfolgreicher kill holte Docker sofort zurück. Am 07.10.
# blieben so 3 GB belegt, das 24-Slot-8B startete nicht (OOM, „did not serve … within
# 240s"), run 1 und run 2 endeten rc=1, die Nacht lieferte 0 Trends. Bis dahin ging es
# nur, weil die Container von Hand gestoppt worden waren. Jetzt: Prozess → Container
# über die cgroup, `docker stop`, Name vermerken; nach dem Lauf `docker start`.

gpu_container_of() {   # PID → Docker-Container-ID (64 hex) oder leer
  sed -nE 's#.*docker-([0-9a-f]{64})\.scope.*#\1#p; s#.*/docker/([0-9a-f]{64}).*#\1#p' \
    "$GPU_PROC_ROOT/$1/cgroup" 2>/dev/null | head -1
}

_GPU_EVICTED_NOW=" "
gpu_evict_pid() {      # VRAM-Prozess freigeben: Container stoppen, sonst kill. rc 0 = frei
  local pid=$1 cid name
  cid=$(gpu_container_of "$pid")
  if [ -n "$cid" ]; then
    name=$(docker inspect -f '{{.Name}}' "$cid" 2>/dev/null | sed 's#^/##'); name=${name:-$cid}
    case "$_GPU_EVICTED_NOW" in *" $name "*) return 0 ;; esac      # zweiter Prozess desselben Containers
    if docker stop -t 30 "$cid" >/dev/null 2>&1; then
      _GPU_EVICTED_NOW="$_GPU_EVICTED_NOW$name "
      mkdir -p "$(dirname "$GPU_EVICT_STATE")"
      grep -qxF "$name" "$GPU_EVICT_STATE" 2>/dev/null || echo "$name" >> "$GPU_EVICT_STATE"
      echo "  stopped container $name (docker stop — restarted after the cycle)"
      return 0
    fi
    echo "  WARNING: docker stop $name failed — its VRAM stays occupied"
    return 1
  fi
  kill "$pid" 2>/dev/null && return 0
  echo "  WARNING: kill $pid failed (other user?) — its VRAM stays occupied"
  return 1
}

gpu_evict_restore() {  # nach dem Lauf: vermerkte Container wieder starten. rc 0 = nichts offen
  [ -s "$GPU_EVICT_STATE" ] || return 0
  local names name failed=0
  names=$(tr '\n' ' ' < "$GPU_EVICT_STATE")
  if gpu_guard_busy >/dev/null; then
    echo "  day-time containers NOT restarted — a GPU job is running; later: docker start $names"
    return 1
  fi
  while read -r name; do
    [ -n "$name" ] || continue
    if docker start "$name" >/dev/null 2>&1; then echo "  restarted container $name"
    else echo "  WARNING: docker start $name failed"; failed=1; fi
  done < "$GPU_EVICT_STATE"
  [ "$failed" -eq 0 ] && rm -f "$GPU_EVICT_STATE"
  return "$failed"
}
