#!/usr/bin/env python3
"""The signal cloud for the landing page hero (docs/launch/preview.html) — a static file.

Owner 29.09.2026: the hero animation becomes the real signal cloud, morphing between
the two layouts of the latest cloud run (pipeline/signal_space.py): "style" (the tiers
as four continents — how a text is written) and "topic" (tier style taken out — what
it is about). Same points, two positions each.

Nothing but geometry leaves the database: per point the two positions, the tier and
the month — no title, no id, no text. A deterministic sample (smallest
(trend_id * 2654435761) mod 2^32) of the run's per-month sample, so every month is
equally represented. Points without a tier are left out (the hero shows four colours).

    .venv/bin/python scripts/export_landing_cloud.py [--n 20000] [--out docs/launch/assets/signal-cloud.bin]

File layout (little-endian): b"CATC", u32 n, f32 extent, then n records of
  6 x u16 (style x,y,z, topic x,y,z; value/65535 * 2*extent - extent) · u8 tier · u8 month
tier: 0 science · 1 patents · 2 funding · 3 market. Upload next to the landing as
/assets/signal-cloud.bin (the page falls back to its old animation without it).
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline import db  # noqa: E402
from pipeline import signal_space as ss  # noqa: E402

TIERS = ("science", "patent", "funding", "market")
EXTENT = 1.25          # |coordinate| cap after framing; the bulk lies within 1


def layout(buf: bytes, rng: float) -> tuple[np.ndarray, np.ndarray]:
    rec = ss.unpack(buf)
    xyz = np.stack([ss.dequantise(rec[a], rng) for a in ("x", "y", "z")], axis=1)
    return rec, xyz


def frame(xyz: np.ndarray) -> np.ndarray:
    """Centre on the median, scale so 95 % of the points fall inside the unit ball."""
    c = xyz - np.median(xyz, axis=0)
    r = np.quantile(np.linalg.norm(c, axis=1), 0.95)
    return c / (r if r > 0 else 1.0)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--n", type=int, default=20000)
    ap.add_argument("--out", default=str(ROOT / "docs" / "launch" / "assets" / "signal-cloud.bin"))
    args = ap.parse_args()
    with db.get_connection() as c:
        r = c.execute("SELECT id, layout, alt_layout, points, alt_points, coord_range, alt_coord_range, codes "
                      "FROM signal_space_runs WHERE alt_points IS NOT NULL ORDER BY id DESC LIMIT 1").fetchone()
    if not r:
        print("no cloud run with two layouts — recompute the cloud first")
        return 1
    lay = {r["layout"]: (bytes(r["points"]), float(r["coord_range"])),
           r["alt_layout"]: (bytes(r["alt_points"]), float(r["alt_coord_range"]))}
    if set(lay) != {"topic", "style"}:
        print(f"unexpected layouts {sorted(lay)}")
        return 1
    rec_t, xyz_t = layout(*lay["topic"])
    rec_s, xyz_s = layout(*lay["style"])
    assert (rec_t["trend_id"] == rec_s["trend_id"]).all(), "the two layouts must hold the same points"
    codes = json.loads(r["codes"]) if isinstance(r["codes"], str) else r["codes"]
    code_to_tier = {int(k): v for k, v in (codes.get("tier") or {}).items()}
    tier_idx = np.array([TIERS.index(code_to_tier[c]) if code_to_tier.get(c) in TIERS else 255
                         for c in rec_t["tier"]], dtype=np.uint8)
    # far outliers of either layout would land on the panel's captions — leave them out
    inside = (np.linalg.norm(frame(xyz_s), axis=1) <= 1.15) & (np.linalg.norm(frame(xyz_t), axis=1) <= 1.15)
    ok = (tier_idx != 255) & inside
    h = (rec_t["trend_id"].astype(np.uint64) * np.uint64(ss.HASH_MUL)) % np.uint64(ss.HASH_MOD)
    order = np.argsort(np.where(ok, h, np.uint64(2 ** 63)), kind="stable")[: min(args.n, int(ok.sum()))]
    s, t = frame(xyz_s)[order], frame(xyz_t)[order]
    q = lambda v: np.round((np.clip(v, -EXTENT, EXTENT) + EXTENT) / (2 * EXTENT) * 65535).astype("<u2")  # noqa: E731
    recs = np.zeros(len(order), dtype=[("c", "<u2", (6,)), ("tier", "u1"), ("month", "u1")])
    recs["c"][:, :3], recs["c"][:, 3:] = q(s), q(t)
    recs["tier"] = tier_idx[order]
    recs["month"] = np.clip(rec_t["month"][order], 0, 255)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(b"CATC" + struct.pack("<If", len(order), EXTENT) + recs.tobytes())
    counts = {TIERS[i]: int((recs["tier"] == i).sum()) for i in range(4)}
    print(f"run {r['id']}: {len(order):,} points -> {out} ({out.stat().st_size / 1e3:.0f} KB); tiers {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
