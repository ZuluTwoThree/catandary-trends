#!/usr/bin/env python3
"""Empirical check: does our production embedding model preserve semantics across
languages? (Qwen3-Embedding-8B is documented multilingual; this verifies it on the
actual server / input path the pipeline uses.)

Method: a handful of patent-style concepts, each written in EN/DE/ZH/JA/FR. Embed
every variant through the production path (EMBED_BACKEND), then compare:

  - cross-lingual, SAME concept   (e.g. EN vs ZH "solid-state battery electrolyte")
  - cross-concept,  SAME language (EN battery vs EN antibody)

Multilingual semantic preservation holds iff same-concept-across-languages cosine
is clearly higher than different-concept-same-language cosine, and a query in one
language retrieves the right concept regardless of the document language.

    python scripts/test_multilingual_embed.py
"""
from __future__ import annotations
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))
from pipeline.config import EMBED_BACKEND, EMBED_MODEL, MODEL_EMBEDDING
from pipeline import llamacpp_client
from pipeline.llm_processor import generate_embedding

# Patent-style concepts, parallel translations (kept tight to isolate the concept).
CONCEPTS = {
    "solid_state_battery": {
        "EN": "Solid-state lithium battery with a sulfide solid electrolyte for electric vehicles",
        "DE": "Festkörper-Lithium-Batterie mit Sulfid-Festelektrolyt für Elektrofahrzeuge",
        "ZH": "用于电动汽车的硫化物固态电解质固态锂电池",
        "JA": "電気自動車向けの硫化物固体電解質を用いた全固体リチウム電池",
        "FR": "Batterie lithium à l'état solide avec électrolyte solide sulfure pour véhicules électriques",
    },
    "monoclonal_antibody": {
        "EN": "Method for producing a humanized monoclonal antibody against a tumor antigen",
        "DE": "Verfahren zur Herstellung eines humanisierten monoklonalen Antikörpers gegen ein Tumorantigen",
        "ZH": "一种生产针对肿瘤抗原的人源化单克隆抗体的方法",
        "JA": "腫瘍抗原に対するヒト化モノクローナル抗体を製造する方法",
        "FR": "Procédé de production d'un anticorps monoclonal humanisé dirigé contre un antigène tumoral",
    },
    "carbon_capture": {
        "EN": "Direct air capture system using an amine sorbent to remove carbon dioxide",
        "DE": "Direct-Air-Capture-System mit Amin-Sorbens zur Entfernung von Kohlendioxid",
        "ZH": "使用胺吸附剂去除二氧化碳的直接空气捕获系统",
        "JA": "アミン吸着剤を用いて二酸化炭素を除去する直接空気回収システム",
        "FR": "Système de capture directe de l'air utilisant un sorbant aminé pour éliminer le dioxyde de carbone",
    },
    "neural_accelerator": {
        "EN": "Hardware accelerator for neural network inference with on-chip memory",
        "DE": "Hardware-Beschleuniger für neuronale Netzinferenz mit On-Chip-Speicher",
        "ZH": "具有片上存储器的用于神经网络推理的硬件加速器",
        "JA": "オンチップメモリを備えたニューラルネットワーク推論用ハードウェアアクセラレータ",
        "FR": "Accélérateur matériel pour l'inférence de réseaux neuronaux avec mémoire sur puce",
    },
}


def embed(text: str) -> np.ndarray:
    vec = (llamacpp_client.generate_embedding(text, model=EMBED_MODEL)
           if EMBED_BACKEND == "llamacpp" else generate_embedding(MODEL_EMBEDDING, text))
    if not vec:
        raise RuntimeError("embedding server returned nothing — is it up on :8090?")
    a = np.asarray(vec, dtype=np.float32)
    return a / (np.linalg.norm(a) + 1e-9)


def main() -> int:
    print(f"backend={EMBED_BACKEND} model={EMBED_MODEL if EMBED_BACKEND=='llamacpp' else MODEL_EMBEDDING}\n")
    langs = ["EN", "DE", "ZH", "JA", "FR"]
    vecs: dict[tuple[str, str], np.ndarray] = {}
    for cname, bylang in CONCEPTS.items():
        for lang in langs:
            vecs[(cname, lang)] = embed(bylang[lang])

    # 1) cross-lingual same-concept cosine (vs EN as the reference query language)
    print("Cross-lingual cosine vs EN (same concept, different language):")
    same_lingual = []
    for cname in CONCEPTS:
        en = vecs[(cname, "EN")]
        sims = {lang: float(en @ vecs[(cname, lang)]) for lang in langs if lang != "EN"}
        same_lingual += list(sims.values())
        print(f"  {cname:22} " + "  ".join(f"{l}={s:.3f}" for l, s in sims.items()))

    # 2) cross-concept same-language cosine (the 'noise floor')
    print("\nCross-concept cosine within EN (different concept — should be LOW):")
    cnames = list(CONCEPTS)
    cross_concept = []
    for i in range(len(cnames)):
        for j in range(i + 1, len(cnames)):
            s = float(vecs[(cnames[i], "EN")] @ vecs[(cnames[j], "EN")])
            cross_concept.append(s)
            print(f"  {cnames[i]:22} vs {cnames[j]:22} = {s:.3f}")

    # 3) retrieval test: for each non-EN variant, does its nearest EN doc = same concept?
    print("\nCross-lingual retrieval (query in X-lang → nearest EN concept):")
    correct = total = 0
    for cname in CONCEPTS:
        for lang in langs:
            if lang == "EN":
                continue
            q = vecs[(cname, lang)]
            best = max(CONCEPTS, key=lambda c: float(q @ vecs[(c, "EN")]))
            total += 1
            correct += (best == cname)
    print(f"  top-1 accuracy: {correct}/{total} = {100*correct/total:.0f}%")

    sl = np.array(same_lingual); cc = np.array(cross_concept)
    print("\n── Verdict ──")
    print(f"  same-concept cross-lingual cosine:  mean {sl.mean():.3f}  min {sl.min():.3f}")
    print(f"  different-concept same-lang cosine: mean {cc.mean():.3f}  max {cc.max():.3f}")
    gap = sl.mean() - cc.max()
    ok = sl.min() > cc.max() and correct == total
    print(f"  separation (min same-lingual − max cross-concept): {sl.min() - cc.max():+.3f}")
    print("  ✅ multilingual semantics PRESERVED" if ok else
          "  ⚠️  weak/failed separation — translate before embed for non-EN")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
