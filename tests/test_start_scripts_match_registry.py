"""Die Startskript-Registry muss zu den Dateien auf der Platte passen.

Anlass (2026-09-25): Gemma und der Draft-Richter wurden auf 16K-Varianten umgestellt
(`start-gemma4-26b-ctx16k.sh`, `start-qwen3.8-27b-ctx16k.sh`). Die Umstellung fasst SECHS
Stellen an — `gpu_handover.MODEL_START_SCRIPTS`, `draft_judge.JUDGE_START_SCRIPT`,
`scheduled_cycle.sh` (zweimal) und zwei Newsletter-Wrapper. Bleibt eine zurück, startet der
Handover ein anderes Modell als der Aufrufer erwartet; beim Alias-Vorfall am 2026-07-23 kostete
genau so ein Auseinanderlaufen einen ganzen Nachtlauf (0 Trends).

Die Tests laufen ohne GPU und ohne llama-server: sie lesen nur Dateien.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from pipeline import draft_judge, gpu_handover

REPO = Path(__file__).resolve().parents[1]
LLAMA = gpu_handover.LLAMA_CPP_ROOT
skip_no_llama = pytest.mark.skipif(not LLAMA.is_dir(), reason="kein ~/llama.cpp auf diesem Host")


@skip_no_llama
@pytest.mark.parametrize("key", sorted(gpu_handover.MODEL_START_SCRIPTS))
def test_registered_start_script_exists_and_loads_that_model(key: str) -> None:
    """Jedes registrierte Skript existiert und lädt genau das Modell, unter dem es steht.

    `_preflight_model_matches` prüft zur Laufzeit dasselbe und verweigert sonst den Start —
    hier fällt es schon beim Testlauf auf, nicht erst nachts um drei.
    """
    script = gpu_handover.MODEL_START_SCRIPTS[key]
    assert script.is_file(), f"{key}: {script} fehlt"
    text = script.read_text()
    # Schlüssel ist entweder ein GGUF-Dateiname (Stages 2-6) oder eine servierte Modell-ID
    # (Richter: "Qwen3.8-27B"); beide müssen im -m-Pfad des Skripts vorkommen.
    assert key in text, f"{key}: {script.name} referenziert dieses Modell nicht"
    assert "--port 8090" in text, f"{script.name}: bindet nicht auf den Produktionsport"


@skip_no_llama
def test_resting_script_is_registered_and_present() -> None:
    assert gpu_handover.CANONICAL_RESTING_MODEL in gpu_handover.MODEL_START_SCRIPTS
    assert (LLAMA / gpu_handover.CANONICAL_RESTING_SCRIPT).is_file()


@skip_no_llama
def test_judge_start_script_matches_handover_registry() -> None:
    """draft_judge und der Handover müssen dasselbe Richter-Skript meinen."""
    registered = gpu_handover.MODEL_START_SCRIPTS[draft_judge.JUDGE_MODEL]
    assert registered.name == draft_judge.JUDGE_START_SCRIPT
    assert (LLAMA / draft_judge.JUDGE_START_SCRIPT).is_file()


def _shell_referenced_scripts(path: Path) -> set[str]:
    return set(re.findall(r"start-[A-Za-z0-9._-]+\.sh", path.read_text()))


@skip_no_llama
@pytest.mark.parametrize("rel", ["scripts/scheduled_cycle.sh",
                                 "scripts/weekly_newsletter_publish.sh",
                                 "scripts/newsletter_tonight.sh"])
def test_shell_wrappers_reference_existing_scripts(rel: str) -> None:
    """Kein Wrapper darf auf ein Startskript zeigen, das es nicht (mehr) gibt."""
    for name in _shell_referenced_scripts(REPO / rel):
        assert (LLAMA / name).is_file(), f"{rel} nennt {name}, das es in {LLAMA} nicht gibt"


@skip_no_llama
def test_content_gen_wrappers_agree_with_registry() -> None:
    """Stage 6, Newsletter-Edition und der Abend-Newsletter laden dasselbe Gemma-Skript
    wie der Handover — sonst startet ein Pfad ein anderes Modell als der andere."""
    expected = gpu_handover.MODEL_START_SCRIPTS[
        "gemma-4-26B-A4B-it-qat-UD-Q4_K_XL.gguf"].name
    for rel in ("scripts/scheduled_cycle.sh", "scripts/weekly_newsletter_publish.sh",
                "scripts/newsletter_tonight.sh"):
        gemma = {n for n in _shell_referenced_scripts(REPO / rel) if "gemma" in n}
        assert gemma == {expected}, f"{rel} nutzt {gemma or 'kein Gemma-Skript'}, erwartet {expected}"


@skip_no_llama
def test_scheduled_cycle_judge_swap_matches_registry() -> None:
    """Der Stage-10-Block hängt den Symlink selbst um — auf dasselbe Skript wie die Registry."""
    text = (REPO / "scripts/scheduled_cycle.sh").read_text()
    expected = gpu_handover.MODEL_START_SCRIPTS[draft_judge.JUDGE_MODEL].name
    assert f"ln -sf {expected} /home/dirk/llama.cpp/start-active.sh" in text
    # Der Identitäts-Check danach prüft den servierten Modellnamen, nicht das Skript.
    assert f'grep -q "{draft_judge.JUDGE_MODEL}"' in text


@skip_no_llama
def test_resting_state_is_restored_to_the_classifier() -> None:
    """Am Ende des Laufs muss der Symlink wieder auf den Ruhezustand zeigen — seit
    04.10.2026 ueber die Shell-Variable LLAMA_REST_SCRIPT (scripts/lib/gpu_guard.sh), deren
    Default der Zwilling von gpu_handover.CANONICAL_RESTING_SCRIPT ist."""
    text = (REPO / "scripts/scheduled_cycle.sh").read_text()
    assert 'ln -sf "$LLAMA_REST_SCRIPT" /home/dirk/llama.cpp/start-active.sh' in text
    guard = (REPO / "scripts/lib/gpu_guard.sh").read_text()
    m = re.search(r'LLAMA_REST_SCRIPT="\$\{LLAMA_REST_SCRIPT:-([^}]+)\}"', guard)
    assert m, "LLAMA_REST_SCRIPT fehlt in gpu_guard.sh"
    assert m.group(1) == gpu_handover.CANONICAL_RESTING_SCRIPT
    for wrapper in ("scripts/weekly_ingesters.sh", "scripts/weekly_newsletter_publish.sh",
                    "scripts/run_food_pilot.sh"):
        w = (REPO / wrapper).read_text()
        assert "start-qwen3-8b-208k.sh /home/dirk/llama.cpp/start-active.sh" not in w, \
            f"{wrapper}: stellt noch das 24-Slot-Skript als Ruhezustand her"
        assert "$LLAMA_REST_SCRIPT" in w, f"{wrapper}: nutzt LLAMA_REST_SCRIPT nicht"


@skip_no_llama
def test_resting_script_is_the_lean_one_slot_8b() -> None:
    """Ruhezustand = dasselbe 8B-GGUF schlank: -c 32768 ohne --parallel (= 4 Default-Slots,
    ~7,6 GB statt ~22 GB, Owner 04.10.2026).
    Das Arbeitsskript der Stufen 2-4 bleibt die 24-Slot-Konfiguration."""
    rest = (LLAMA / gpu_handover.CANONICAL_RESTING_SCRIPT).read_text()
    work = gpu_handover.MODEL_START_SCRIPTS[gpu_handover.CANONICAL_RESTING_MODEL].read_text()
    assert gpu_handover.CANONICAL_RESTING_MODEL in rest
    assert "--port 8090" in rest
    assert not re.search(r"--parallel\s+(\d+)", rest), "Ruhe-Skript setzt --parallel — der Default (4) ist gewollt"
    m = re.search(r"--parallel\s+(\d+)", work)
    assert m and int(m.group(1)) >= gpu_handover.EIGHT_B_MIN_SLOTS, \
        "Arbeitsskript hat weniger Slots, als der Handover verlangt"
