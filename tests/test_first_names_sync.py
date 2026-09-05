"""frontend/src/lib/first-names.ts is generated from pipeline/first_names.py —
the review UI and the publish gates must trigger on the same given names."""
import re
from pathlib import Path

from pipeline.first_names import FIRST_NAMES

TS = Path(__file__).parent.parent / "frontend" / "src" / "lib" / "first-names.ts"


def test_list_size_and_exclusions():
    assert len(FIRST_NAMES) >= 2000
    for excluded in ("will", "may", "morgan", "paris", "mercedes", "hong"):
        assert excluded not in FIRST_NAMES
    for kept in ("markus", "carsten", "ursula", "xiaoming", "aisha", "kwame"):
        assert kept in FIRST_NAMES


def test_ts_list_matches_python():
    names = set(re.findall(r'"([^"]+)"', TS.read_text()))
    assert names == set(FIRST_NAMES), "run scripts/gen_first_names_ts.py"
