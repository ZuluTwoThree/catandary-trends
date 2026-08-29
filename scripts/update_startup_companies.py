#!/usr/bin/env python3
"""Inkrementeller Firmenstamm-Update-Pfad für den Startup Explorer (#94 Teil 1).

`scripts/build_startup_companies.py` baut `startup_companies` per TRUNCATE +
Insert komplett neu — das würde das nachträgliche Enrichment zerstören
(Wikidata: QIDs/Gründungsdaten/Gründerlisten/Websites; Firmen-Embeddings via
scripts/embed_startup_companies.py). Deshalb klammert
`scripts/monthly_startup_sources.sh` den Rebuild bewusst aus, mit der Folge,
dass neue GLEIF-/CH-/CORDIS-/SBIR-/Form-D-Rohdaten nie zu Firmenprofilen
werden und neue Events (Form D, SBIR, Presse-Runden) für nach dem Rebuild
entstandene Firmen kein Ziel finden.

Dieses Skript ist STRIKT ADDITIV:
  1. Kandidaten aus denselben vier Event-Quellen wie der Rebuild
     (Form D · SBIR · CORDIS · Presse-Runden), beschränkt auf raw_entries/
     startup_press_rounds-Zeilen ohne bestehenden startup_events-Eintrag.
     (GLEIF/CH tragen keine Events — deren Anreicherung übernimmt bereits
     `scripts/enrich_startup_companies.py`, coalesce-basiert, additiv, läuft
     schon monatlich. Hier nicht dupliziert.)
  2. EXAKT dieselbe Entity-Resolution wie der Rebuild — importiert aus
     `pipeline/startup_resolution.py` (Stufe A: harte Anker CIK/DUNS/PIC
     innerhalb einer Quelle; Stufe B: name_norm + Geo-Gate quellübergreifend
     via `merge()`). Stufe C (Embedding-Fuzzy) existiert im Rebuild NICHT im
     Code — hier neu, optional, siehe --no-embed-match unten.
  3. Für jede resultierende Gruppe:
       - Stufe A gegen den BESTAND (cik/duns/pic exakt) → Treffer = bestehende
         Firma, NUR fehlende Felder ergänzt (COALESCE — nie überschrieben).
       - Stufe B gegen den BESTAND (name_norm + Geo-Gate, nur bei genau
         einem Kandidaten) → dito.
       - Stufe C (optional): Embedding-Nearest-Neighbor gegen
         startup_companies.embedding_1024 (pgvector), nur ab hoher Schwelle
         (--embed-threshold, Default 0.90) automatisch verknüpft — sonst
         ungemergt (Plan §4: "ein Duplikat ist billiger als ein falscher
         Merge"). Braucht Postgres + einen erreichbaren Embedding-Server;
         ohne beides wird klar ausgewiesen, wie viele Kandidaten NUR
         deswegen neu angelegt würden.
       - Kein Treffer → neue Firma, additiv eingefügt. Dieselbe
         Ausschluss-Idee wie beim manuellen Rebuild-Audit (Fondsvehikel /
         Presse-Namensartefakte) wird angewandt — siehe
         pipeline.company_norm.classify_new_company_exclusion für die
         Herleitung und ihre bekannten Grenzen.
  4. Events für NEUE Firmen docken automatisch an (sie werden zusammen mit
     der Firma eingefügt). Für bereits bestehende, bisher event-lose Firmen
     ist kein Extra-Schritt nötig — Matches ergänzen Events direkt.
  5. `pipeline.startup_match.refresh_aggregates()` (bestehende, importierte
     Funktion) zieht event_count/first_event_at/last_event_at nach.

NICHT angetastet: wikidata_qid, founders, founded_date, lei, ch_number,
embedding_1024, verticals, name, name_norm, total_funding_usd (bei
Matches — Neuanlagen bekommen total_funding_usd wie der Rebuild berechnet,
siehe _corroborates_regd-Import). Das sind Enrichment- bzw. abgeleitete
Spalten, die anderen Skripten/dem initialen Build gehören.

    python scripts/update_startup_companies.py                    # Dry-Run (Default)
    python scripts/update_startup_companies.py --limit 200         # gestaffelt
    python scripts/update_startup_companies.py --since 2026-08-01
    python scripts/update_startup_companies.py --apply --limit 200
    python scripts/update_startup_companies.py --no-embed-match --apply
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from collections import defaultdict
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).parent.parent))

import pipeline.db as db_mod
from pipeline.company_norm import (
    classify_new_company_exclusion, norm_company_name,
    strip_possessive_prefix, trigram_similarity,
)
from pipeline.db import get_connection
from pipeline.startup_match import refresh_aggregates
from pipeline.startup_resolution import (
    Group, MIN_PRESS_KEY_LEN, _corroborates_regd, _geo_compatible,
    load_cordis, load_formd, load_press, load_sbir, merge,
)
from scripts.ingest_secform_d import INDUSTRY_VERTICAL

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("update_startup_companies")

DEFAULT_EMBED_THRESHOLD = 0.90
DEFAULT_TRIGRAM_THRESHOLD = 0.6


# ---------------------------------------------------------------- Kandidaten

def load_candidate_groups(since: str | None, limit: int) -> list[Group]:
    """Dieselben vier Quellen wie der Rebuild, aber nur unverknüpfte Zeilen,
    danach exakt derselbe Stufe-B-Merge (`pipeline.startup_resolution.merge`)."""
    all_groups = (
        list(load_formd(unassigned_only=True, since=since, limit=limit).values())
        + list(load_sbir(unassigned_only=True, since=since, limit=limit).values())
        + list(load_cordis(unassigned_only=True, since=since, limit=limit).values())
        + _cleaned_press(load_press(unassigned_only=True, since=since, limit=limit))
    )
    return merge(all_groups)


def _cleaned_press(groups: dict) -> list:
    """Geo-Possessiv-Praefixe nur im Presse-Pfad abstreifen (strip_possessive_
    prefix) — VOR dem Merge, damit 'Stockholm's Pixelgen Technologies' als
    'Pixelgen Technologies' auf die bestehende Firma matcht statt eine
    Dublette anzulegen. Bewusst nicht in norm_company_name/Rebuild: dort
    wuerde es rueckwirkend Bestands-Keys verschieben."""
    out = list(groups.values())
    for g in out:
        g.names = [strip_possessive_prefix(n) for n in g.names]
    return out


# ---------------------------------------------------------------- Bestand laden

def load_existing_anchors(conn) -> tuple[dict, dict, dict]:
    """cik -> id · duns -> [ids] (nur eindeutig verwertbar) · pic -> id.
    Ohne excluded-Filter: ein harter Anker identifiziert dieselbe Rechts-
    einheit unabhängig davon, ob sie als Fondsvehikel/Presse-Artefakt
    markiert ist — Ziel ist Dubletten-Vermeidung, nicht Anzeige-Eignung."""
    rows = conn.execute(
        "select id, cik, duns, pic from startup_companies "
        "where cik is not null or duns is not null or pic is not null").fetchall()
    by_cik, by_duns, by_pic = {}, defaultdict(list), {}
    for r in rows:
        if r["cik"]:
            by_cik[r["cik"]] = r["id"]
        if r["duns"]:
            by_duns[r["duns"]].append(r["id"])
        if r["pic"]:
            by_pic[r["pic"]] = r["id"]
    return by_cik, by_duns, by_pic


def load_existing_by_name(conn) -> dict[str, list[dict]]:
    rows = conn.execute(
        "select id, name_norm, country, region from startup_companies").fetchall()
    idx: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        idx[r["name_norm"]].append(dict(r))
    return idx


def load_all_names(conn) -> dict[int, str]:
    rows = conn.execute("select id, name_norm from startup_companies").fetchall()
    return {r["id"]: r["name_norm"] for r in rows}


# ---------------------------------------------------------------- Stufe C (optional)

def embed_match(group: Group, threshold: float, embed_fn, search_fn) -> tuple[int | None, float | None, str]:
    """Embedding-Nearest-Neighbor gegen den Bestand. `embed_fn(text) ->
    list[float]|None` und `search_fn(vec, limit) -> list[(id, sim)]` sind
    injizierbar (Tests laufen ohne Live-Server/Postgres).

    Rückgabe: (company_id|None, similarity|None, status) — status ist
    'matched', 'below_threshold' oder 'unavailable' (kein Postgres oder
    Embedding-Server nicht erreichbar — der Aufrufer zählt das getrennt,
    siehe --no-embed-match-Ausgabe)."""
    if not db_mod.USE_POSTGRES:
        return None, None, "unavailable"
    text = group.display_name()
    vec = embed_fn(text)
    if vec is None:
        return None, None, "unavailable"
    hits = search_fn(vec, 1)
    if not hits:
        return None, None, "below_threshold"
    cid, sim = hits[0]
    if sim >= threshold:
        return cid, sim, "matched"
    return None, sim, "below_threshold"


def embed_server_ready(embed_model: str, probe_timeout: float = 5.0) -> bool:
    """Schnelle, sichere Verfügbarkeitsprüfung für Stufe C — bewusst KEIN
    echter Embedding-Call.

    Befund beim Testlauf gegen die Live-DB (2026-08-29, #94): llama-server
    lief bereits (Port 8090), aber mit dem CONTENT-GEN-Modell (Gemma-4-26B)
    geladen, nicht dem Embedding-Modell — llama-server ignoriert den
    `model`-Namen im Request (bekanntes Verhalten, siehe
    llama-start-scripts-no-alias-Memory) und hätte eine echte
    /v1/embeddings-Anfrage entweder falsch beantwortet oder bis zum vollen
    LLAMACPP_TIMEOUT (Default 600s!) blockiert. Ein Update-Lauf darf dafür
    nicht minutenlang hängen. Deshalb: GET /v1/models mit kurzem Timeout,
    UND Abgleich, ob der Modellname wie das erwartete Embedding-Modell
    aussieht (Modell-Identitäts-Guard, analog Stage 10 draft_judge)."""
    from pipeline.llamacpp_client import LLAMACPP_HOST
    import httpx
    try:
        with httpx.Client(timeout=probe_timeout) as client:
            r = client.get(f"{LLAMACPP_HOST}/v1/models")
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        logger.warning("Embedding-Server nicht erreichbar (%s): %s", LLAMACPP_HOST, e)
        return False
    loaded = [str(m.get("id") or m.get("model") or "") for m in data.get("data", [])]
    # Grobes Namens-Matching (Basename, case-insensitiv) statt exaktem
    # Pfadvergleich — Start-Skripte referenzieren das GGUF mit vollem Pfad.
    embed_stub = embed_model.lower()
    if not any(embed_stub in m.lower() for m in loaded):
        logger.warning("Embedding-Server erreichbar, aber falsches Modell geladen "
                       "(erwartet '%s', geladen %s) — Stufe C übersprungen.",
                       embed_model, loaded)
        return False
    return True


def _pgvector_search(conn, vec: list[float], limit: int) -> list[tuple[int, float]]:
    lit = "[" + ",".join(f"{float(x):.7g}" for x in vec[:1024]) + "]"
    rows = conn.execute(
        "select id, 1 - (embedding_1024 <=> ?::vector) as sim "
        "from startup_companies where embedding_1024 is not null "
        "order by embedding_1024 <=> ?::vector limit ?",
        (lit, lit, limit)).fetchall()
    return [(r["id"], float(r["sim"])) for r in rows]


# ---------------------------------------------------------------- Resolution

def resolve(groups: list[Group], by_cik: dict, by_duns: dict, by_pic: dict,
            by_name: dict, *, embed_enabled: bool, embed_threshold: float,
            embed_fn=None, search_fn=None) -> dict:
    """Ordnet jede Gruppe genau einer Kategorie zu. Rückgabe: dict mit
    Listen 'stage_a', 'stage_b', 'stage_c', 'new' — jeder Eintrag ist
    (group, matched_company_id|None, extra) für die spätere Anwendung."""
    result = {"stage_a": [], "stage_b": [], "stage_c": [], "new": [],
              "embed_unavailable_count": 0}
    for g in groups:
        # Stufe A: harte Anker
        cid = None
        if g.cik and g.cik in by_cik:
            cid = by_cik[g.cik]
        elif g.duns and len(by_duns.get(g.duns, [])) == 1:
            cid = by_duns[g.duns][0]
        elif g.pic and g.pic in by_pic:
            cid = by_pic[g.pic]
        if cid is not None:
            result["stage_a"].append((g, cid, "hard_anchor"))
            continue

        # Stufe B: name_norm + Geo-Gate, nur bei eindeutigem Kandidaten.
        # Presse-only-Gruppen (keine Geografie) brauchen zusätzlich den
        # MIN_PRESS_KEY_LEN-Schutz aus merge() — sonst würde ein kurzer,
        # generischer Presse-Name blind gegen 145k Bestandsnamen matchen.
        nn = norm_company_name(g.display_name())
        is_press_only = g.sources == {"press"}
        if not (is_press_only and len(nn) < MIN_PRESS_KEY_LEN):
            candidates = by_name.get(nn, [])
            geo_ok = [c for c in candidates
                      if _geo_compatible(g, SimpleNamespace(country=c["country"], region=c["region"]))]
            if len(geo_ok) == 1:
                result["stage_b"].append((g, geo_ok[0]["id"], "name_geo"))
                continue

        # Stufe C: optionale Embedding-Fuzzy-Zuordnung
        if embed_enabled:
            cid, sim, status = embed_match(g, embed_threshold, embed_fn, search_fn)
            if status == "unavailable":
                result["embed_unavailable_count"] += 1
            elif cid is not None:
                result["stage_c"].append((g, cid, f"embedding:{sim:.3f}"))
                continue

        result["new"].append((g, None, None))
    return result


# ---------------------------------------------------------------- Anwenden

def _event_rows(g: Group, company_id: int) -> list[tuple]:
    return [(company_id, e["event_type"], e["event_date"], e["amount"],
             e["currency"], e["round_label"], json.dumps(e["investors"]),
             json.dumps(e["meta"]), e["source"][:200], e["source_url"],
             e["raw_entry_id"]) for e in g.events]


def apply_match(conn, g: Group, company_id: int) -> int:
    """Events andocken + NUR fehlende Identifier ergänzen (COALESCE)."""
    rows = _event_rows(g, company_id)
    n_before = conn.execute(
        "select count(*) c from startup_events where company_id = ?",
        (company_id,)).fetchone()["c"]
    conn.executemany(
        "INSERT OR IGNORE INTO startup_events (company_id, event_type, "
        "event_date, amount, currency, round_label, investors, meta, "
        "source, source_url, raw_entry_id) VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    n_after = conn.execute(
        "select count(*) c from startup_events where company_id = ?",
        (company_id,)).fetchone()["c"]
    conn.execute(
        "update startup_companies set "
        "country = coalesce(country, ?), region = coalesce(region, ?), "
        "city = coalesce(city, ?), website = coalesce(website, ?), "
        "sector = coalesce(sector, ?), employees = coalesce(employees, ?), "
        "cik = coalesce(cik, ?), duns = coalesce(duns, ?), pic = coalesce(pic, ?) "
        "where id = ?",
        (g.country, g.region, g.city, g.website, g.sector, g.employees,
         g.cik, g.duns, g.pic, company_id))
    existing_name = conn.execute(
        "select name from startup_companies where id = ?", (company_id,)).fetchone()["name"]
    alias_rows = [(company_id, n.strip()[:500], "update94")
                  for n in {x.strip() for x in g.names}
                  if n.strip() and n.strip() != existing_name]
    if alias_rows:
        conn.executemany(
            "INSERT OR IGNORE INTO startup_aliases (company_id, alias, source) "
            "VALUES (?, ?, ?)", alias_rows)
    return n_after - n_before


def apply_new(conn, g: Group) -> int:
    """Neue Firma additiv einfügen — Feldaufbau wie build_startup_companies.write(),
    zzgl. der excluded-Heuristik (siehe pipeline.company_norm)."""
    name = g.display_name()
    dates = sorted(e["event_date"] for e in g.events)
    usd = [float(e["amount"]) for e in g.events
           if e["amount"] and e["currency"] == "USD"
           and not _corroborates_regd(e, g.events)]
    vert = INDUSTRY_VERTICAL.get((g.sector or "").upper())
    excluded = classify_new_company_exclusion(name, g.sources)
    returning = " RETURNING id" if db_mod.USE_POSTGRES else ""
    cur = conn.execute(
        "INSERT INTO startup_companies (name, name_norm, country, region, city, "
        "website, sector, cik, duns, pic, employees, first_event_at, last_event_at, "
        "event_count, total_funding_usd, verticals, excluded) "
        f"VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?){returning}",
        (name[:500], norm_company_name(name)[:500], g.country, g.region,
         g.city, g.website, g.sector, g.cik, g.duns, g.pic, g.employees,
         dates[0], dates[-1], len(g.events), sum(usd) if usd else None,
         json.dumps([vert] if vert else []), excluded))
    company_id = cur.lastrowid
    conn.executemany(
        "INSERT OR IGNORE INTO startup_events (company_id, event_type, event_date, "
        "amount, currency, round_label, investors, meta, source, source_url, "
        "raw_entry_id) VALUES (?,?,?,?,?,?,?,?,?,?,?)", _event_rows(g, company_id))
    alias_rows = [(company_id, n.strip()[:500], "update94")
                  for n in {x.strip() for x in g.names} if n.strip() and n.strip() != name]
    if alias_rows:
        conn.executemany(
            "INSERT OR IGNORE INTO startup_aliases (company_id, alias, source) "
            "VALUES (?, ?, ?)", alias_rows)
    return company_id


# ---------------------------------------------------------------- Dubletten-Selbstkontrolle

def trigram_self_check(new_groups: list, all_names: dict[int, str],
                       threshold: float, max_examples: int = 10) -> list[dict]:
    """Für jede 'würde-neu-anlegen'-Gruppe: gibt es einen Trigram-Nahtreffer
    (similarity > threshold) im Bestand? Inverted-Index über die Trigramme
    ALLER Bestandsnamen, damit nicht 145k Vergleiche pro Kandidat laufen."""
    index: dict[str, set[int]] = defaultdict(set)
    from pipeline.company_norm import _char_trigrams
    for cid, nn in all_names.items():
        for tg in _char_trigrams(nn):
            index[tg].add(cid)

    findings = []
    for g, _, _ in new_groups:
        nn = norm_company_name(g.display_name())
        candidate_ids: set[int] = set()
        for tg in _char_trigrams(nn):
            candidate_ids |= index.get(tg, set())
        best_id, best_sim = None, 0.0
        for cid in candidate_ids:
            sim = trigram_similarity(nn, all_names[cid])
            if sim > best_sim:
                best_id, best_sim = cid, sim
        if best_id is not None and best_sim > threshold:
            findings.append({"candidate": g.display_name(), "near_miss_id": best_id,
                             "near_miss_name": all_names[best_id], "similarity": round(best_sim, 3)})
    return findings[:max_examples] if max_examples else findings


# ---------------------------------------------------------------- Report

def _fmt_examples(entries, n=10) -> list[str]:
    out = []
    for g, cid, extra in entries[:n]:
        label = f"{g.display_name()!r} [{','.join(sorted(g.sources))}]"
        if cid is not None:
            out.append(f"  -> attach to #{cid} ({extra}): {label}")
        else:
            out.append(f"  -> new company: {label}")
    return out


def print_report(res: dict, trigram_findings: list, embed_enabled: bool,
                 embed_available: bool, args) -> None:
    total = sum(len(res[k]) for k in ("stage_a", "stage_b", "stage_c", "new"))
    stage_c_ran = embed_enabled and embed_available
    print("=" * 72)
    print("Startup-Firmenstamm-Update — Dry-Run-Bericht" if not args.apply
          else "Startup-Firmenstamm-Update — ANGEWENDET")
    print("=" * 72)
    print(f"Kandidaten nach Merge: {total}")
    print(f"  Stufe A (harter Anker CIK/DUNS/PIC): {len(res['stage_a'])}")
    for line in _fmt_examples(res["stage_a"]):
        print(line)
    print(f"  Stufe B (Name + Geo-Gate, eindeutig): {len(res['stage_b'])}")
    for line in _fmt_examples(res["stage_b"]):
        print(line)
    print(f"  Stufe C (Embedding, Schwelle {args.embed_threshold}): "
          f"{len(res['stage_c'])}" + ("" if stage_c_ran else " [nicht gelaufen]"))
    for line in _fmt_examples(res["stage_c"]):
        print(line)
    print(f"  Neue Firmen: {len(res['new'])}")
    if not stage_c_ran:
        reason = ("durch --no-embed-match deaktiviert" if not embed_enabled
                  else "Embedding-Server/Postgres nicht erreichbar")
        print(f"    Hinweis: Stufe C lief nicht ({reason}) — alle "
              f"{len(res['new'])} 'neue Firma'-Kandidaten wurden NICHT auf einen "
              f"Embedding-Nahtreffer geprüft und würden NUR deswegen neu angelegt.")
    excl_counts: dict[str, int] = defaultdict(int)
    for g, _, _ in res["new"]:
        r = classify_new_company_exclusion(g.display_name(), g.sources)
        excl_counts[r or "(kein Ausschluss)"] += 1
    for reason, n in sorted(excl_counts.items(), key=lambda kv: -kv[1]):
        print(f"    {reason}: {n}")
    for line in _fmt_examples(res["new"]):
        print(line)
    print()
    print(f"Dubletten-Selbstkontrolle (Trigram-Ähnlichkeit > {args.trigram_threshold} "
          f"im Bestand, würde trotzdem neu angelegt):")
    if not trigram_findings:
        print("  keine Nahtreffer gefunden.")
    else:
        print(f"  {len(trigram_findings)} Beispiele (Stichprobe, Orchestrator sollte "
              f"diese vor --apply gegenprüfen):")
        for f in trigram_findings:
            print(f"    {f['candidate']!r} ~ #{f['near_miss_id']} {f['near_miss_name']!r} "
                  f"(sim={f['similarity']})")
    print("=" * 72)


# ---------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser(description="Inkrementeller Startup-Firmenstamm-Update (#94)")
    ap.add_argument("--apply", action="store_true", help="Schreibt tatsächlich (Default: Dry-Run)")
    ap.add_argument("--limit", type=int, default=0, help="Kandidaten-Deckel PRO QUELLE (0 = unbegrenzt)")
    ap.add_argument("--since", type=str, default=None, help="Nur Kandidaten ab diesem Datum (YYYY-MM-DD)")
    ap.add_argument("--no-embed-match", action="store_true", help="Stufe C (Embedding-Fuzzy) abschalten")
    ap.add_argument("--embed-threshold", type=float, default=DEFAULT_EMBED_THRESHOLD)
    ap.add_argument("--trigram-threshold", type=float, default=DEFAULT_TRIGRAM_THRESHOLD)
    args = ap.parse_args()

    t0 = time.time()
    embed_enabled = not args.no_embed_match

    with get_connection() as conn:
        by_cik, by_duns, by_pic = load_existing_anchors(conn)
        by_name = load_existing_by_name(conn)
        all_names = load_all_names(conn)

    groups = load_candidate_groups(args.since, args.limit)
    logger.info("Kandidaten nach Quell-Ladung + Stufe-B-Merge: %d Gruppen", len(groups))

    embed_fn = search_fn = None
    embed_available = False
    if embed_enabled and db_mod.USE_POSTGRES:
        from pipeline import llamacpp_client
        from pipeline.config import EMBED_MODEL
        embed_fn = lambda text: llamacpp_client.generate_embedding(text, model=EMBED_MODEL)  # noqa: E731

        def search_fn(vec, limit):
            with get_connection() as c:
                return _pgvector_search(c, vec, limit)
        # Schnelle Verfügbarkeits+Identitäts-Probe (GET /v1/models, Sekunden)
        # statt eines echten Embedding-Calls mit bis zu 600s Timeout — siehe
        # embed_server_ready()-Docstring für den realen Befund, der das nötig machte.
        embed_available = embed_server_ready(EMBED_MODEL)

    res = resolve(groups, by_cik, by_duns, by_pic, by_name,
                  embed_enabled=embed_enabled and embed_available,
                  embed_threshold=args.embed_threshold,
                  embed_fn=embed_fn, search_fn=search_fn)

    trigram_findings = trigram_self_check(res["new"], all_names, args.trigram_threshold)

    print_report(res, trigram_findings, embed_enabled, embed_available, args)

    if not args.apply:
        logger.info("Dry-Run — nichts geschrieben (%.0fs).", time.time() - t0)
        return 0

    n_events_added = 0
    n_new = 0
    with get_connection() as conn:
        for g, cid, _ in res["stage_a"] + res["stage_b"] + res["stage_c"]:
            n_events_added += apply_match(conn, g, cid)
        for g, _, _ in res["new"]:
            apply_new(conn, g)
            n_new += 1
    refresh_aggregates()
    logger.info("Angewendet in %.0fs: %d neue Firmen, %d Events an bestehende Firmen "
                "angedockt.", time.time() - t0, n_new, n_events_added)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
