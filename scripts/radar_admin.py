"""Admin CLI for Catandary Trend-Radar customers.

The entire customer lifecycle for the solo operator: onboard after a
Stripe payment, start trials, reconfigure, pause/cancel, inspect MRR.

Usage:
    python scripts/radar_admin.py add --name "Acme GmbH" --email kunde@acme.de \\
        --tier pro --verticals TECH,HEALTH --keywords "quantum computing,longevity" \\
        [--contact "Max Muster"] [--brand-name "Acme Radar"] [--brand-color "#0ea5e9"] \\
        [--brand-logo-url URL] [--recipients a@x.de,b@x.de] [--language de] \\
        [--parent-id 3] [--stripe-id cus_123] [--notes "..."]
    python scripts/radar_admin.py trial --name ... --email ... --verticals ... [--days 14]
    python scripts/radar_admin.py list [--status active]
    python scripts/radar_admin.py show <id>
    python scripts/radar_admin.py set <id> --keywords "..." --tier pro ...
    python scripts/radar_admin.py convert <id> --tier solo   # trial -> paying
    python scripts/radar_admin.py pause <id> | resume <id> | cancel <id>
    python scripts/radar_admin.py rotate-token <id>
    python scripts/radar_admin.py mrr
"""

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline import radar_db
from pipeline.config import PORTAL_BASE_URL


def _csv(value: str | None) -> list[str]:
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


def _print_customer(c: dict, verbose: bool = True):
    mandate = f" (Mandant von #{c['parent_id']})" if c["parent_id"] else ""
    print(f"#{c['id']}  {c['name']}{mandate}  [{c['tier']}/{c['status']}]  {c['mrr_eur']:.0f} €/Monat")
    if verbose:
        print(f"    Kontakt:    {c['contact_name'] or '—'} <{c['email']}>")
        if c["extra_recipients"]:
            print(f"    Weitere:    {', '.join(c['extra_recipients'])}")
        print(f"    Vertikale:  {', '.join(c['verticals'])}")
        print(f"    Watchlist:  {', '.join(c['keywords']) or '—'}")
        print(f"    Sprache:    {c['language']}")
        if c["brand_name"] or c["brand_logo_url"]:
            print(f"    Branding:   {c['brand_name'] or '—'}  {c['brand_color'] or ''}")
        if c["trial_ends_at"]:
            print(f"    Trial bis:  {c['trial_ends_at']}")
        if c["stripe_customer_id"]:
            print(f"    Stripe:     {c['stripe_customer_id']}")
        print(f"    Portal:     {PORTAL_BASE_URL}/radar/{c['token']}")
        if c["notes"]:
            print(f"    Notizen:    {c['notes']}")


def cmd_add(args, tier=None, trial_days: int | None = None):
    tier = tier or args.tier
    trial_ends = None
    if trial_days:
        trial_ends = (datetime.now(timezone.utc) + timedelta(days=trial_days)).strftime("%Y-%m-%d")
    customer = radar_db.insert_customer(
        name=args.name,
        email=args.email,
        tier=tier,
        verticals=_csv(args.verticals),
        keywords=_csv(args.keywords),
        contact_name=args.contact,
        extra_recipients=_csv(args.recipients),
        language=args.language,
        brand_name=args.brand_name,
        brand_color=args.brand_color,
        brand_logo_url=args.brand_logo_url,
        parent_id=args.parent_id,
        trial_ends_at=trial_ends,
        stripe_customer_id=args.stripe_id,
        notes=args.notes,
    )
    print("Kunde angelegt:\n")
    _print_customer(customer)
    print("\nNächste Schritte:")
    print(f"  1. Erstes Briefing erzeugen:  python -m pipeline.briefing_generator --customer {customer['id']} --send")
    print(f"  2. Portal-Link verschicken:   {PORTAL_BASE_URL}/radar/{customer['token']}")


def cmd_list(args):
    customers = radar_db.list_customers(status=args.status)
    if not customers:
        print("Keine Kunden gefunden.")
        return
    for c in customers:
        _print_customer(c, verbose=False)
    summary = radar_db.get_mrr_summary()
    print(f"\nAktive Kunden: {summary['active_customers']}  |  MRR: {summary['total_mrr']:.0f} €")


def cmd_show(args):
    customer = radar_db.get_customer(args.id)
    if not customer:
        sys.exit(f"Kunde {args.id} nicht gefunden.")
    _print_customer(customer)
    briefings = radar_db.get_briefings(args.id, limit=8)
    if briefings:
        print("\n    Briefings:")
        for b in briefings:
            sent = f"versandt {b['sent_at']}" if b["sent_at"] else "nicht versandt"
            print(f"      {b['week_label']}  {len(b['trend_ids'])} Trends, {sent}")


def cmd_set(args):
    fields = {}
    if args.verticals is not None:
        fields["verticals"] = _csv(args.verticals)
    if args.keywords is not None:
        fields["keywords"] = _csv(args.keywords)
    if args.recipients is not None:
        fields["extra_recipients"] = _csv(args.recipients)
    for key, attr in [("tier", "tier"), ("email", "email"), ("contact_name", "contact"),
                      ("brand_name", "brand_name"), ("brand_color", "brand_color"),
                      ("brand_logo_url", "brand_logo_url"), ("language", "language"),
                      ("notes", "notes"), ("stripe_customer_id", "stripe_id"),
                      ("mrr_eur", "mrr")]:
        val = getattr(args, attr, None)
        if val is not None:
            fields[key] = val
    if not fields:
        sys.exit("Keine Änderungen angegeben.")
    customer = radar_db.update_customer(args.id, **fields)
    print("Aktualisiert:\n")
    _print_customer(customer)


def cmd_convert(args):
    customer = radar_db.get_customer(args.id)
    if not customer:
        sys.exit(f"Kunde {args.id} nicht gefunden.")
    if customer["tier"] != "trial":
        sys.exit(f"Kunde {args.id} ist kein Trial (tier={customer['tier']}).")
    fields = {"tier": args.tier, "trial_ends_at": None}
    # trial may exceed the target tier's limits; trim instead of failing
    limits = radar_db.TIER_LIMITS[args.tier]
    fields["verticals"] = customer["verticals"][: limits["verticals"]]
    fields["keywords"] = customer["keywords"][: limits["keywords"]]
    fields["extra_recipients"] = customer["extra_recipients"][: max(0, limits["recipients"] - 1)]
    customer = radar_db.update_customer(args.id, **fields)
    print(f"Trial konvertiert zu {args.tier} ({customer['mrr_eur']:.0f} €/Monat):\n")
    _print_customer(customer)


def _set_status(customer_id: int, status: str):
    customer = radar_db.update_customer(customer_id, status=status)
    print(f"Status gesetzt: {status}\n")
    _print_customer(customer, verbose=False)


def cmd_rotate(args):
    token = radar_db.rotate_token(args.id)
    print(f"Neuer Portal-Link: {PORTAL_BASE_URL}/radar/{token}")


def cmd_mrr(args):
    summary = radar_db.get_mrr_summary()
    print("MRR-Übersicht (aktive Kunden)\n")
    for tier in ("solo", "pro", "agency", "trial"):
        entry = summary["by_tier"].get(tier)
        if entry:
            print(f"  {tier:<8} {entry['count']:>3} Kunden  {entry['mrr']:>8.0f} €")
    print(f"\n  Gesamt-MRR: {summary['total_mrr']:.0f} €  ({summary['active_customers']} aktive Kunden)")
    target = 3000
    if summary["total_mrr"] < target:
        print(f"  Ziel 3.000 €: noch {target - summary['total_mrr']:.0f} € offen")
    else:
        print("  Ziel 3.000 € MRR erreicht ✔")


def _add_config_args(p, require_core: bool):
    p.add_argument("--name", required=require_core)
    p.add_argument("--email", required=require_core)
    p.add_argument("--verticals", required=require_core,
                   help="Kommagetrennt: FOOD,TECH,HEALTH,ECO,DESIGN,FASHION,BIZ,LIFESTYLE")
    p.add_argument("--keywords", default=None, help="Watchlist, kommagetrennt")
    p.add_argument("--contact", default=None)
    p.add_argument("--recipients", default=None, help="Weitere Empfänger, kommagetrennt")
    p.add_argument("--language", default="de", choices=["de", "en"])
    p.add_argument("--brand-name", default=None)
    p.add_argument("--brand-color", default=None)
    p.add_argument("--brand-logo-url", default=None)
    p.add_argument("--parent-id", type=int, default=None,
                   help="Agency-Kunden-ID, falls dies ein Mandanten-Radar ist")
    p.add_argument("--stripe-id", default=None)
    p.add_argument("--notes", default=None)


def main():
    parser = argparse.ArgumentParser(description="Trend-Radar Kundenverwaltung")
    sub = parser.add_subparsers(dest="command", required=True)

    p_add = sub.add_parser("add", help="Zahlenden Kunden anlegen")
    p_add.add_argument("--tier", required=True, choices=["solo", "pro", "agency"])
    _add_config_args(p_add, require_core=True)

    p_trial = sub.add_parser("trial", help="14-Tage-Trial anlegen")
    p_trial.add_argument("--days", type=int, default=14)
    _add_config_args(p_trial, require_core=True)

    p_list = sub.add_parser("list", help="Kunden auflisten")
    p_list.add_argument("--status", default=None, choices=["active", "paused", "cancelled"])

    p_show = sub.add_parser("show", help="Kundendetails")
    p_show.add_argument("id", type=int)

    p_set = sub.add_parser("set", help="Kundenfelder ändern")
    p_set.add_argument("id", type=int)
    p_set.add_argument("--tier", default=None, choices=["trial", "solo", "pro", "agency"])
    p_set.add_argument("--mrr", type=float, default=None, dest="mrr",
                       help="MRR überschreiben (z.B. Jahresrabatt)")
    _add_config_args(p_set, require_core=False)

    p_conv = sub.add_parser("convert", help="Trial in zahlendes Abo umwandeln")
    p_conv.add_argument("id", type=int)
    p_conv.add_argument("--tier", required=True, choices=["solo", "pro", "agency"])

    for name in ("pause", "resume", "cancel"):
        p = sub.add_parser(name)
        p.add_argument("id", type=int)

    p_rot = sub.add_parser("rotate-token", help="Portal-Token erneuern")
    p_rot.add_argument("id", type=int)

    sub.add_parser("mrr", help="MRR-Übersicht")

    args = parser.parse_args()
    radar_db.init_radar_schema()

    if args.command == "add":
        cmd_add(args)
    elif args.command == "trial":
        cmd_add(args, tier="trial", trial_days=args.days)
    elif args.command == "list":
        cmd_list(args)
    elif args.command == "show":
        cmd_show(args)
    elif args.command == "set":
        cmd_set(args)
    elif args.command == "convert":
        cmd_convert(args)
    elif args.command == "pause":
        _set_status(args.id, "paused")
    elif args.command == "resume":
        _set_status(args.id, "active")
    elif args.command == "cancel":
        _set_status(args.id, "cancelled")
    elif args.command == "rotate-token":
        cmd_rotate(args)
    elif args.command == "mrr":
        cmd_mrr(args)


if __name__ == "__main__":
    main()
