#!/usr/bin/env python3
"""
Uncle Bubba's Drones — catalog builder.

Pulls the public product feed from Shopify-based drone retailers and writes
catalog.js, which index.html loads.

Every Shopify store publishes its whole catalogue at /products.json.
No API key, no login, no scraping. This reads that.

USAGE
    python3 build_catalog.py

    Options:
      --limit N     max products to keep per retailer (default 1000)
      --out FILE    output path (default catalog.js)
      --report      print a summary and write nothing

REQUIREMENTS
    Python 3.8+. Nothing to install — uses the standard library only.
"""

import json
import re
import sys
import time
import argparse
import urllib.request
import urllib.error
from datetime import date

# ─────────────────────────────────────────────────────────────────────────────
# RETAILERS
#
# Add a store by appending a dict here. It must be a Shopify store — check by
# opening https://thatstore.com/products.json in a browser. If you see JSON,
# it works.
#
#   affiliate : appended to every product URL. Leave "" if you have no program.
#   use       : "FPV", "Photography", or "both" — the Built for filter.
# ─────────────────────────────────────────────────────────────────────────────

RETAILERS = [
    {
        "name": "Pyrodrone",
        "domain": "https://pyrodrone.com",
        "affiliate": "",
        "use": "FPV",
    },
    {
        "name": "RaceDayQuads",
        "domain": "https://www.racedayquads.com",
        "affiliate": "",
        "use": "FPV",
    },
    {
        "name": "djioemparts",
        "domain": "https://djioemparts.com",
        "affiliate": "",
        "use": "Photography",
    },
    {
        "name": "Rotor Riot",
        "domain": "https://rotorriot.com",
        "affiliate": "",
        "use": "FPV",
    },
    {
        "name": "Drone Nerds",
        "domain": "https://www.dronenerds.com",
        "affiliate": "",        # Rakuten affiliate program — add your tracking here
        "use": "both",          # consumer + enterprise DJI
    },
    {
        "name": "NewBeeDrone",
        "domain": "https://newbeedrone.com",
        "affiliate": "",
        "use": "FPV",
    },
    # GetFPV is Magento, not Shopify — no products.json, so its items are
    # hand-added in index.html and unaffected by this script.
]

# ─────────────────────────────────────────────────────────────────────────────
# CATEGORY RULES
#
# First pattern that matches the product title or type wins. Order matters:
# put the specific ones above the general ones.
# ─────────────────────────────────────────────────────────────────────────────

CATEGORY_RULES = [
    # Specific first. A flight controller made by T-Motor must not land in
    # Motors, and a radio's hall gimbal must not land in Gimbal & Camera.
    ("DRN", r"\b(bnf|pnp|rtf|ready.to.fly|bind.n.fly|quadcopter|cinelifter)\b"),
    ("GGL", r"\b(goggle|goggles|vrx|headset|faceplate)\b"),
    ("VTX", r"\b(vtx|video transmitter|air unit)\b"),
    ("FC",  r"(flight controller|\bfc\b|\besc\b|\bstack\b|\baio\b|speed controller)"),
    ("RXC", r"(hall gimbal|gimbal set|stick end|grip tape|\bradio\b|"
            r"\btransmitter\b|\btx1[56]\b|remote controller)"),
    ("BAT", r"\b(lipo|lihv|battery|batteries|li-ion|charger|\bcell\b|mah)\b"),
    ("PRP", r"\b(prop|props|propeller|propellers|prop guard)\b"),
    ("MTR", r"(?<!-)\b(motor|motors|bell)\b"),      # (?<!-) skips "T-Motor"
    ("ANT", r"\b(antenna|antennas|\bgps\b|receiver|pigtail|\brx\b)\b"),
    ("GMB", r"\b(camera|lens|nd filter|gimbal adapter|gimbal motor)\b"),
    ("FRM", r"\b(frame|arm|arms|plate|standoff|canopy|duct|ducts)\b"),
    ("TLS", r"\b(tool|tools|screwdriver|soldering|iron|filament|wrench|driver|screw)\b"),
    ("ACC", r".*"),   # catch-all — must stay last
]

# Product titles matching these are skipped entirely — clothing, stickers,
# gift cards and so on. Not drone parts.
SKIP = re.compile(
    r"\b(t.shirt|shirt|hat|hoodie|sticker|decal|swag|gift card|mug|"
    r"lanyard keychain|poster|banner|magazine|subscription)\b", re.I)



# ─────────────────────────────────────────────────────────────────────────────
# COMPATIBILITY
#
# The feed doesn't carry fitment data, but product titles usually do. A part
# called "Armattan Bobcat Replacement Top Plate" fits an Armattan Bobcat.
# These rules read what the title already tells us.
# ─────────────────────────────────────────────────────────────────────────────

# Stack mount pattern — the thing that actually decides whether an FC or ESC fits
MOUNTS = [
    (r"30\.5\s*[x×]\s*30\.5", "Frames with a 30.5x30.5mm stack mount"),
    (r"25\.5\s*[x×]\s*25\.5", "Frames with a 25.5x25.5mm stack mount"),
    (r"\b30\s*[x×]\s*30\b",   "Frames with a 30x30mm stack mount"),
    (r"\b20\s*[x×]\s*20\b",   "Frames with a 20x20mm stack mount"),
    (r"\b16\s*[x×]\s*16\b",   "Frames with a 16x16mm mount"),
]

# Named aircraft and gear that replacement parts belong to
PLATFORMS = [
    (r"armattan\s+bobcat", "Armattan Bobcat"),
    (r"armattan\s+beaver", "Armattan Beaver"),
    (r"armattan\s+tadpole", "Armattan Tadpole"),
    (r"armattan\s+badger", "Armattan Badger"),
    (r"impulserc\s+apex", "ImpulseRC APEX"),
    (r"iflight\s+aos\s*7", "iFlight AOS 7"),
    (r"iflight\s+aos\s*5", "iFlight AOS 5"),
    (r"sector\s*x5", "HGLRC Sector X5"),
    (r"demibot", "Ummagawd Demibot"),
    (r"\bqav-?r\s*2", "Lumenier QAV-R 2"),
    (r"\bqav-?s\s*2", "Lumenier QAV-S 2"),
    (r"qav-?pro", "Lumenier QAV-PRO"),
    (r"phreakstyle", "XILO Phreakstyle"),
    (r"tx16s", "RadioMaster TX16S"),
    (r"tx15\b", "RadioMaster TX15"),
    (r"\btx12\b", "RadioMaster TX12"),
    (r"boxer", "RadioMaster Boxer"),
    (r"pocket", "RadioMaster Pocket"),
    (r"x9\s*lite", "FrSky X9 Lite"),
    (r"goggles\s*3", "DJI Goggles 3"),
    (r"goggles\s*2", "DJI Goggles 2"),
    (r"\bavata\s*2", "DJI Avata 2"),
    (r"\bavata\b", "DJI Avata"),
    (r"o4\s*(pro\s*)?air\s*unit", "DJI O4 Air Unit"),
    (r"o3\s*air\s*unit", "DJI O3 Air Unit"),
    (r"caddx\s*vista|\bvista\b", "Caddx Vista"),
    (r"walksnail", "Walksnail Avatar system"),
    (r"hdzero", "HDZero system"),
    (r"matrice\s*400", "DJI Matrice 400"),
    (r"matrice\s*350|\bm350\b", "DJI Matrice 350 RTK"),
    (r"matrice\s*30\b", "DJI Matrice 30 Series"),
    (r"matrice\s*4t\b", "DJI Matrice 4T"),
    (r"matrice\s*4e\b", "DJI Matrice 4E"),
    (r"matrice\s*4(?!\d)", "DJI Matrice 4 Series"),
    (r"mavic\s*3\s*enterprise|m3e\b", "DJI Mavic 3 Enterprise"),
    (r"mavic\s*3", "DJI Mavic 3"),
    (r"phantom\s*4", "DJI Phantom 4"),
    (r"phantom\s*3", "DJI Phantom 3"),
    (r"\bneo\b", "DJI Neo"),
    (r"mini\s*4\s*pro", "DJI Mini 4 Pro"),
    (r"mini\s*3\s*pro", "DJI Mini 3 Pro"),
    (r"air\s*3s", "DJI Air 3S"),
    (r"\bair\s*3\b", "DJI Air 3"),
]

CONNECTORS = [(r"\bxt60\b","XT60"), (r"\bxt30\b","XT30"),
              (r"\bph2\.0\b","PH2.0"), (r"\bbt2\.0\b","BT2.0"),
              (r"\ba30\b","A30")]


def prop_class_from_stator(name):
    """A 2306 motor swings 5" props; a 1404 is a toothpick motor."""
    m = re.search(r"(?<!\d)(\d{2})(\d{2})(?:\.\d)?(?!\d)", name)
    if not m:
        return None
    d = int(m.group(1))
    if d <= 11: return '1.5-2" micro builds'
    if d <= 14: return '3" toothpick builds'
    if d <= 20: return '3.5-4" builds'
    if d <= 23: return '5" builds'
    return '6-7" long range builds'


def derive_fits(title, product_type, cat):
    """Best-effort compatibility from the product title. Never invents."""
    blob = f"{title} {product_type}"
    hits = []

    # A named platform in the title is the strongest signal
    for pattern, label in PLATFORMS:
        if re.search(pattern, blob, re.I) and label not in hits:
            hits.append(label)
    if hits:
        return hits[:4]

    # Electronics: the mount pattern is the real question
    if cat in ("FC", "VTX"):
        for pattern, label in MOUNTS:
            if re.search(pattern, blob, re.I):
                return [label]

    # Motors: stator size implies prop size
    if cat == "MTR":
        pc = prop_class_from_stator(title)
        if pc:
            return [f"{pc} - confirm mount pattern with your frame"]

    # Chargers aren't "for" a build — they charge a range of packs
    if re.search(r"charger|charging (hub|dock)|power supply", blob, re.I):
        rng = re.search(r"\b([1-8])\s*-\s*([1-8])S\b", blob, re.I)
        if rng:
            return [f"Charges {rng.group(1)}S-{rng.group(2)}S batteries"]
        one = re.search(r"\b([1-8])S\b", blob, re.I)
        if one:
            return [f"Charges {one.group(1)}S batteries"]
        return ["See retailer listing for supported batteries"]

    # Batteries: cell count plus connector is the compatibility statement
    if cat == "BAT":
        cell = re.search(r"\b([1-8])S\b", blob, re.I)
        conn = next((lbl for pat, lbl in CONNECTORS
                     if re.search(pat, blob, re.I)), None)
        if cell and conn:
            return [f"{cell.group(1)}S builds with a {conn} connector"]
        if cell:
            return [f"{cell.group(1)}S builds - check connector"]

    # Propellers: leading size number
    if cat == "PRP":
        m = re.search(r'\b(\d)(?:\.\d)?\s*(?:"|inch|in\b|\s*[x×]\s*\d)', blob, re.I)
        if m:
            return [f'{m.group(1)}" builds']
        # bare size codes: 5136 -> 5.1x3.6, 51466 -> 5.1x4.6x6-blade
        m = re.search(r"(?<!\d)(\d)(\d)(\d{2,3})(?!\d)", title)
        if m:
            return [f'{m.group(1)}" builds']

    return ["See retailer listing for compatibility"]


def fetch_feed(domain, page, timeout=30):
    """Pull one page of a Shopify product feed. 250 products max per page."""
    url = f"{domain}/products.json?limit=250&page={page}"
    req = urllib.request.Request(url, headers={
        "User-Agent": "UncleBubbasDrones/1.0 (catalog builder; +https://unclebubbasdrones.com)",
        "Accept": "application/json",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


# Words that mean "a part for a drone" rather than "a drone"
_PART_WORDS = re.compile(
    r"\b(propeller|prop|blade|guard|battery|charger|motor|arm|plate|frame|"
    r"cable|strap|case|bag|mount|adapter|module|antenna|filter|lens|screw|"
    r"cover|shell|gimbal|kit|part|parts|holder|dampener|stand|spare)\b", re.I)

def categorise(title, product_type):
    blob = f"{title} {product_type}".lower()
    # A complete aircraft: says drone/aircraft and names no component
    if re.search(r"\b(drone|aircraft|quadcopter|matrice|inspire)\b", blob, re.I) \
       and not _PART_WORDS.search(title):
        return "DRN"
    for cat, pattern in CATEGORY_RULES:
        if re.search(pattern, blob, re.I):
            return cat
    return "ACC"


def clean(html):
    """Strip tags and whitespace out of a Shopify description."""
    text = re.sub(r"<[^>]+>", " ", html or "")
    text = re.sub(r"&[a-z]+;", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def build_product(item, retailer):
    """Turn one Shopify product into a catalog entry, or None to skip it."""
    title = item.get("title", "").strip()
    if not title or SKIP.search(title):
        return None

    variants = item.get("variants") or []
    if not variants:
        return None

    # Cheapest variant that's actually in stock. If none are, skip the product —
    # a link to something sold out is worse than no link.
    in_stock = [v for v in variants if v.get("available")]
    if not in_stock:
        return None
    v = min(in_stock, key=lambda x: float(x.get("price") or 1e9))

    price = round(float(v["price"]), 2)
    # Some retailers hide prices under manufacturer MAP policy ("call for
    # pricing"). Those arrive as 0 or a token amount — skip rather than
    # publish a price that isn't real.
    if price < 1.0:
        return None
    offer = {
        "source": retailer["name"],
        "price": price,
        "url": f"{retailer['domain']}/products/{item['handle']}{retailer['affiliate']}",
    }

    # compare_at_price above price means a genuine discount. Some stores set it
    # BELOW price by mistake — ignore those rather than show a fake sale.
    cap = v.get("compare_at_price")
    if cap:
        try:
            was = round(float(cap), 2)
            if was > price:
                offer["was"] = was
        except (TypeError, ValueError):
            pass

    meta = clean(item.get("body_html"))[:110]
    if meta and not meta.endswith("."):
        meta = meta.rsplit(" ", 1)[0] + "…"

    use = ["FPV", "Photography"] if retailer["use"] == "both" else [retailer["use"]]

    cat = categorise(title, item.get("product_type", ""))

    return {
        "id": f"{retailer['name'][:3].upper()}-{item['id']}",
        "cat": cat,
        "brand": (item.get("vendor") or retailer["name"]).strip(),
        "name": title,
        "meta": meta or "See retailer listing for full specifications",
        "fits": derive_fits(title, item.get("product_type", ""), cat),
        "use": use,
        "offers": [offer],
        # Kept for reference; the site doesn't render these yet.
        "_image": (item.get("images") or [{}])[0].get("src", ""),
        "_sku": v.get("sku", ""),
    }


def pull_retailer(retailer, limit):
    print(f"\n  {retailer['name']}")
    products, page, seen = [], 1, set()

    while len(products) < limit:
        try:
            data = fetch_feed(retailer["domain"], page)
        except urllib.error.HTTPError as e:
            print(f"    page {page}: HTTP {e.code} — stopping")
            break
        except Exception as e:
            print(f"    page {page}: {e} — stopping")
            break

        items = data.get("products", [])
        if not items:
            break

        kept = 0
        for item in items:
            if item["id"] in seen:
                continue
            seen.add(item["id"])
            p = build_product(item, retailer)
            if p:
                products.append(p)
                kept += 1
            if len(products) >= limit:
                break

        print(f"    page {page}: {len(items)} fetched, {kept} kept "
              f"({len(products)} total)")
        page += 1
        time.sleep(1)          # be polite — don't hammer their server

    return products


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=1000,
                    help="max products per retailer (default 1000)")
    ap.add_argument("--out", default="catalog.js", help="output file")
    ap.add_argument("--report", action="store_true",
                    help="print a summary without writing the file")
    args = ap.parse_args()

    print("Uncle Bubba's Drones — catalog builder")
    print("=" * 45)

    all_products = []
    for r in RETAILERS:
        all_products.extend(pull_retailer(r, args.limit))

    if not all_products:
        print("\nNothing fetched. Check your connection and try again.")
        sys.exit(1)

    # ── summary ──────────────────────────────────────────────────────────────
    from collections import Counter
    by_cat = Counter(p["cat"] for p in all_products)
    by_shop = Counter(p["offers"][0]["source"] for p in all_products)
    on_sale = sum(1 for p in all_products if p["offers"][0].get("was"))

    print("\n" + "=" * 45)
    print(f"  {len(all_products)} products")
    print(f"  {on_sale} on sale")
    print("\n  By retailer:")
    for k, n in by_shop.most_common():
        print(f"    {k:<16} {n}")
    print("\n  By category:")
    for k, n in by_cat.most_common():
        print(f"    {k:<16} {n}")

    if args.report:
        print("\n(--report: nothing written)")
        return

    # ── write catalog.js ─────────────────────────────────────────────────────
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(f"// Generated by build_catalog.py on {date.today()}\n")
        f.write(f"// {len(all_products)} products — do not edit by hand.\n\n")
        f.write("const generatedProducts = ")
        json.dump(all_products, f, indent=1, ensure_ascii=False)
        f.write(";\n")

    print(f"\n  Written to {args.out}")
    print("\n  Next: upload it alongside index.html and commit.")


if __name__ == "__main__":
    main()
