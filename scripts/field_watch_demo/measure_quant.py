"""Reifegrad-Block (K(t), Zykluszeit, Zentralität) für das Trajectory Sheet.

Nutzt die Messkaskade aus dem archivierten `pipeline/dossier_quant.py`
(Tag archive/dossiers-2026-09-19) — sie ist nicht mehr im Baum, aber
deterministisch und geprüft (Runden 1–30). Bis `scripts/field_watch.py`
sie ersetzt, wird sie hier aus dem Tag geladen; ein GPU-Handover für den
Query-Vektor (Cache in data/) ist Teil des Laufs.

Usage: measure_quant.py "<Feldphrase>" out.json
"""
import importlib.util, json, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TAG = "archive/dossiers-2026-09-19"

def load_from_tag(name: str, path: str, tmp: Path):
    src = subprocess.run(["git", "-C", str(ROOT), "show", f"{TAG}:{path}"], check=True, capture_output=True, text=True).stdout
    p = tmp / Path(path).name; p.write_text(src)
    spec = importlib.util.spec_from_file_location(name, p)
    m = importlib.util.module_from_spec(spec); sys.modules[name] = m; spec.loader.exec_module(m)
    return m

def main(topic: str, out: str):
    sys.path.insert(0, str(ROOT))
    with tempfile.TemporaryDirectory() as td:
        dq = load_from_tag("pipeline.dossier_quant", "pipeline/dossier_quant.py", Path(td))
        res = {"topic": topic, "quant": dq.build_quant_evidence(topic)}
    json.dump(res, open(out, "w"), default=str, indent=1)
    print("quant ok:", res["quant"].get("ok"), res["quant"].get("reason"))

if __name__ == "__main__":
    main(*sys.argv[1:])
