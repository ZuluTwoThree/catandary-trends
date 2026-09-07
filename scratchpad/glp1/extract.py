"""Ausgeliefertes Dokument und Pruefanhang eines Laufs auf die Platte."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from pipeline import dossier_structure as ds
from pipeline.db import get_connection

did = int(sys.argv[1])
stem = sys.argv[2]
with get_connection() as conn:
    row = conn.execute("select report_md from dossiers where id = ?",
                       (did,)).fetchone()
md = dict(row)["report_md"]
mark = ds.AUDIT_ANNEX_MARK
if mark in md:
    doc, annex = md.split(mark, 1)
else:
    doc, annex = md, ""
out = Path(__file__).parent
(out / f"{stem}_final.md").write_text(doc.rstrip() + "\n")
(out / f"{stem}_annex.md").write_text(annex.lstrip() + "\n")
print(f"{stem}_final.md {len(doc.split())} Woerter · "
      f"{stem}_annex.md {len(annex.split())} Woerter")
