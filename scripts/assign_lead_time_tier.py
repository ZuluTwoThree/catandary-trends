"""One-shot: add `lead_time_tier` (future | market | now) to every source in
sources.yaml. Defaults by type; explicit overrides by source name.

Rules:
  type=research  -> future  (science/academic, 5-10y lead)
  type=press_wire -> market (corporate announcements, 1-2y lead)
  type=trade_media -> market, unless overridden to `now` (consumer-facing,
                     lifestyle, real-time culture) or `future` (deep analytical)
"""
from pathlib import Path
import yaml

YAML = Path(__file__).resolve().parents[1] / "sources.yaml"

# Explicit overrides. All other trade_media default to "market".
OVERRIDES_NOW = {
    # Fashion / beauty / luxury consumer-facing
    "Hypebeast", "Highsnobiety", "Robb Report", "Luxury Daily",
    "Vogue UK", "Fashionista", "WWD", "Glossy",
    # Food consumer / dining
    "Eater", "Nation's Restaurant News",
    # Design / architecture consumer
    "Dezeen", "ArchDaily", "Wallpaper", "Designboom", "Creative Bloq",
    # Travel / experience
    "Skift",
    # Gaming / culture now
    "GamesIndustry.biz",
}

OVERRIDES_FUTURE = {
    # Deep analytical / research-adjacent trade media
    "MIT Technology Review", "IEEE Spectrum", "Carbon Brief",
    "Nature Food", "Trends in Food Science & Technology",
    "Good Food Institute",
    "Platformer", "Nieman Lab", "Rest of World",
    "McKinsey Insights",
    "Norwegian SciTech News",
    "Semiconductor Engineering",  # deep-tech upstream
}


def tier_for(name: str, type_: str) -> str:
    if type_ == "research":
        return "future"
    if name in OVERRIDES_FUTURE:
        return "future"
    if name in OVERRIDES_NOW:
        return "now"
    return "market"  # trade_media default + press_wire


def walk_and_tag(node):
    if isinstance(node, list):
        for item in node:
            walk_and_tag(item)
    elif isinstance(node, dict):
        if "name" in node and "type" in node and "feed_url" in node:
            node["lead_time_tier"] = tier_for(node["name"], node["type"])
        for v in node.values():
            walk_and_tag(v)


data = yaml.safe_load(YAML.read_text(encoding="utf-8"))
walk_and_tag(data)
YAML.write_text(yaml.dump(data, allow_unicode=True, sort_keys=False, width=120), encoding="utf-8")

# Summary
counts = {"future": 0, "market": 0, "now": 0}
def count(node):
    if isinstance(node, list):
        for i in node: count(i)
    elif isinstance(node, dict):
        t = node.get("lead_time_tier")
        if t in counts: counts[t] += 1
        for v in node.values(): count(v)
count(data)
print(f"Tagged sources: future={counts['future']}  market={counts['market']}  now={counts['now']}")
