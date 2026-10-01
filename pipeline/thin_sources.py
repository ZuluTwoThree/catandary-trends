"""Entries whose source is too thin for an article (Owner 2026-10-01, option b).

The hard content guard refuses bodies under 60 words as garbage. From a source of a
few hundred characters the model honestly writes 40-59 words, so such an entry was
refused every night, stayed unprocessed and was tried again — three Gemma generations
a night, forever (Carbios at Ecotextile News: six nights by 01.10.; thirteen such
entries that night, and their leftovers alone triggered a second run).

Rule: when an entry's every attempt fails ONLY for being too short, the night is noted;
in the third distinct night the entry is filtered with reason `source_too_thin`.
Real token soup (any other guard reason) keeps the old behaviour and stays queued —
that failure is transient (the 05.09. episode). State: data/garbled_too_short.json,
{entry_id: ["YYYY-MM-DD", …]}.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date
from pathlib import Path

from pipeline.config import DATA_DIR

logger = logging.getLogger("thin_sources")

STATE_FILE = DATA_DIR / "garbled_too_short.json"
NIGHTS = 3
FILTER_REASON = "source_too_thin"
_REASONS = re.compile(r"produced garbage \(([^)]*)\)")


def only_too_short(message: str) -> bool:
    """True when the guard's reasons in a GarbledOutputError message are all too_short."""
    m = _REASONS.search(message or "")
    if not m:
        return False
    reasons = [r.strip() for r in m.group(1).split(",") if r.strip()]
    return bool(reasons) and all(r.startswith("too_short") for r in reasons)


def _load(path: Path) -> dict[str, list[str]]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def note_too_short(entry_id: int, message: str, today: date | None = None,
                   path: Path | None = None) -> bool:
    """Record tonight for this entry; True when it has now been too short on NIGHTS
    distinct nights and should be filtered. Never raises."""
    if not only_too_short(message):
        return False
    path = path or STATE_FILE
    day = (today or date.today()).isoformat()
    try:
        state = _load(path)
        nights = sorted(set(state.get(str(entry_id), [])) | {day})
        if len(nights) >= NIGHTS:
            state.pop(str(entry_id), None)
        else:
            state[str(entry_id)] = nights
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=0, sort_keys=True), encoding="utf-8")
        tmp.replace(path)
        return len(nights) >= NIGHTS
    except OSError as exc:
        logger.warning("could not record too-short night for %d: %s", entry_id, exc)
        return False
