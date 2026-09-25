"""#110 stage 2: the relabel pass only rewrites a press row when the head is
confident AND disagrees with market_shift; everything else is left alone."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.relabel_signal_types import decide


def test_decide_respects_floor_unknown_classes_and_no_op_agreement():
    labels = np.array(["regulation", "regulation", "market_shift", "patent", "partnership"])
    conf = np.array([0.95, 0.59, 0.99, 0.99, 0.60])
    assert decide(labels, conf, 0.6) == ["regulation", None, None, None, "partnership"]
    assert decide(labels, conf, 0.7) == ["regulation", None, None, None, None]
    assert decide([], [], 0.6) == []
