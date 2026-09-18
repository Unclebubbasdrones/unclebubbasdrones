#!/usr/bin/env python3
"""
Uncle Bubba's Drones — model page builder.

Creates one page per drone model ("Parts for the DJI Mini 4 Pro"), plus an
index listing them all.

Why per-model and not per-product: nobody searches for a SKU. They search
"Mini 4 Pro replacement propellers". A page per model matches how people
actually look, and forty real pages beat two thousand thin ones — search
engines penalise large numbers of near-identical pages.

USAGE
    python3 build_model_pages.py

    Reads index.html and catalog.js from the current folder, writes
    drone-<model>.html files plus drones.html.

    Options:
      --min N       minimum parts before a model gets its own page (default 3)
      --dir PATH    where to write (default: current folder)
"""

import json
import re
import os
import sys
import argparse
from datetime import date

# Not a model at all — build classes and catch-alls get no page
NOT_A_MODEL = re.compile(
    r"^(complete aircraft|frames? with|see retailer)|\bbuilds?\b|"
    r"check (mount|frame|compat)|confirm mount", re.I)

# Fits nearly anything — screwdrivers, landing pads, thermal paste. These get
# ONE "Universal" page instead of appearing on every single model page.
UNIVERSAL = re.compile(
    r"^(any |most |universal|standalone)|repair bench|\bsystems?$|"
    r"\breceivers\)?$|most fpv goggles", re.I)


def slugify(name):
    s = name.lower()
    s = re.sub(r'["\u201c\u201d]', "", s)
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return re.sub(r"-+", "-", s).strip("-")


def load_products(folder):
    """Pull the hand-built list out of index.html and the feed out of catalog.js."""
    products = []

    idx = os.path.join(folder, "index.html")
    if not os.path.exists(idx):
        sys.exit("index.html not found — run this in the folder with your site files.")
    src = open(idx, encoding="utf-8").read()
    try:
        start = src.index("const products = ") + len("const products = ")
        # walk the brackets so we stop at the array's real end
        depth, i = 0, start
        while i < len(src):
            if src[i] == "[":
                depth += 1
            elif src[i] == "]":
                depth -= 1
                if depth == 0:
                    break
            elif src[i] in "\"'":
                q, i = src[i], i + 1
                while i < len(src) and src[i] != q:
                    i += 2 if src[i] == "\\" else 1
            i += 1
        products += json.loads(src[start:i + 1])
    except (ValueError, json.JSONDecodeError) as e:
        sys.exit(f"Couldn't read products from index.html: {e}")
    hand = len(products)

    cat = os.path.join(folder, "catalog.js")
    if os.path.exists(cat):
        txt = open(cat, encoding="utf-8").read()
        m = re.search(r"const generatedProducts = (\[.*\]);", txt, re.S)
        if m:
            feed = json.loads(m.group(1))
            seen = {p["offers"][0]["url"].split("?")[0] for p in products}
            for g in feed:
                if not g.get("offers"):
                    continue
                if g["offers"][0]["url"].split("?")[0] in seen:
                    continue
                products.append(g)
    print(f"  {hand} hand-built + {len(products) - hand} from feed = {len(products)}")
    return products


def group_by_model(products, minimum):
    models = {}
    for p in products:
        universal = False
        for fit in p.get("fits", []):
            if NOT_A_MODEL.search(fit):
                continue
            if UNIVERSAL.search(fit):
                universal = True
                continue
            models.setdefault(fit, []).append(p)
        if universal:
            models.setdefault("Universal", []).append(p)
    return {k: v for k, v in models.items() if len(v) >= minimum}


HEAD = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<meta name="description" content="{desc}">
<link rel="canonical" href="https://unclebubbasdrones.com/{slug}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&family=Manrope:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<link rel="stylesheet" href="_shared.css">
<style>
  .parts{{margin-top:8px;}}
  .part{{display:flex;justify-content:space-between;align-items:center;gap:14px;
    padding:13px 2px;border-bottom:1px solid var(--line);}}
  .part:first-child{{border-top:1px solid var(--line);}}
  .pl{{flex:1;min-width:0;}}
  .pn{{font-weight:700;font-size:14px;line-height:1.3;}}
  .pm{{font-size:12px;color:var(--text-muted);margin-top:3px;}}
  .pr{{text-align:right;flex-shrink:0;}}
  .pp{{font-family:var(--mono);font-weight:600;font-size:15px;}}
  .ps{{font-size:10.5px;color:var(--text-muted);margin-top:2px;}}
  .was{{font-family:var(--mono);font-size:10.5px;color:var(--text-muted);
    text-decoration:line-through;margin-left:5px;}}
  .sale{{font-family:var(--mono);font-size:9px;color:#ffd24d;
    background:rgba(255,210,77,.12);border:1px solid #4a4021;border-radius:20px;
    padding:2px 7px;display:inline-block;margin-top:4px;}}
  .catrow{{font-family:var(--mono);font-size:10.5px;color:var(--green);
    text-transform:uppercase;letter-spacing:.07em;margin:26px 0 4px;}}
  .modelgrid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:10px;}}
  .modelcard{{background:var(--surface);border:1px solid var(--line);border-radius:9px;
    padding:14px 16px;display:block;transition:border-color .13s;}}
  .modelcard:hover{{border-color:var(--green);}}
  .modelcard .mn{{font-weight:700;font-size:14px;}}
  .modelcard .mc{{font-family:var(--mono);font-size:11px;color:var(--green);margin-top:4px;}}
</style>
</head>
<body>
<header>
  <div class="header-inner">
    <a href="index.html" class="logo"><span class="logo-mark"><span></span></span> UNCLE BUBBA'S DRONES</a>
    <nav>
      <a href="index.html">Catalog</a>
      <a href="drones.html"{dronesactive}>By Drone</a>
      <a href="guides.html">Guides</a>
      <a href="about.html">About</a>
      <a href="contact.html">Contact</a>
      <a href="disclosure.html">Disclosure</a>
    </nav>
  </div>
</header>
<main>
"""

FOOT = """</main>
<footer>
  Uncle Bubba's Drones — we compare prices, we don't sell parts.
  <nav>
    <a href="index.html">Catalog</a>
    <a href="drones.html">By Drone</a>
    <a href="guides.html">Guides</a>
    <a href="about.html">About</a>
    <a href="contact.html">Contact</a>
    <a href="disclosure.html">Affiliate Disclosure</a>
  </nav>
</footer>
</body>
</html>
"""

CAT_NAMES = {
    "DRN": "Complete Drones", "FRM": "Frames", "PRP": "Propellers",
    "MTR": "Motors", "BAT": "Batteries", "FC": "Flight Controllers",
    "RXC": "Controllers", "GMB": "Gimbal & Camera", "GGL": "Goggles",
    "ARM": "Arms & Shells", "TLS": "Tools", "ANT": "Antennas & Comms",
    "VTX": "Video Transmitters", "ACC": "Accessories",
}


def esc(t):
    return (str(t).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def write_model_page(folder, model, parts):
    slug = f"drone-{slugify(model)}.html"
    parts = sorted(parts, key=lambda p: (p["cat"], p["offers"][0]["price"]))
    cheapest = min(p["offers"][0]["price"] for p in parts)

    if model == "Universal":
        heading = "Universal parts and tools"
        desc = (f"{len(parts)} tools and accessories that work across most "
                f"drones, from ${cheapest:.2f}.")
        intro = (f'{len(parts)} items that aren\'t tied to one aircraft — '
                 f'screwdrivers, charging gear, landing pads and the like, '
                 f'from ${cheapest:.2f}. Useful whatever you fly.')
    else:
        heading = f"Parts for the {esc(model)}"
        desc = (f"{len(parts)} parts that fit the {model}, priced from "
                f"${cheapest:.2f}. Compare across retailers in one place.")
        intro = (f'{len(parts)} parts that fit the {esc(model)}, from '
                 f'${cheapest:.2f}. Every listing links straight to the '
                 f'retailer. Prices are checked periodically, not live — '
                 f'confirm before buying.')

    body = [f'<div class="eyebrow">{esc(model)}</div>',
            f'<h1>{heading}</h1>',
            f'<p>{intro}</p>']

    current = None
    body.append('<div class="parts">')
    for p in parts:
        if p["cat"] != current:
            current = p["cat"]
            body.append('</div>')
            body.append(f'<div class="catrow">{CAT_NAMES.get(current, current)}</div>')
            body.append('<div class="parts">')
        o = p["offers"][0]
        was = f'<span class="was">${o["was"]:.2f}</span>' if o.get("was") else ""
        sale = '<div class="sale">Limited Time Sale</div>' if o.get("was") else ""
        body.append(
            f'<a class="part" href="{esc(o["url"])}" target="_blank" rel="noopener sponsored">'
            f'<div class="pl"><div class="pn">{esc(p["name"])}</div>'
            f'<div class="pm">{esc(p["meta"])}</div>{sale}</div>'
            f'<div class="pr"><div class="pp">${o["price"]:.2f}{was}</div>'
            f'<div class="ps">{esc(o["source"])}</div></div></a>')
    body.append('</div>')
    body.append('<p style="font-size:13px;margin-top:28px;">'
                'Not what you were after? <a href="index.html" '
                'style="color:var(--green);text-decoration:underline;">'
                'Search the full catalog</a> or '
                '<a href="drones.html" style="color:var(--green);text-decoration:underline;">'
                'browse other drones</a>.</p>')

    page_title = ("Universal drone parts and tools" if model == "Universal"
                  else f"Parts for the {esc(model)}")
    html = HEAD.format(title=f"{page_title} — Uncle Bubba's Drones",
                       desc=esc(desc), slug=slug, dronesactive="")
    html += "\n".join(body) + "\n" + FOOT
    open(os.path.join(folder, slug), "w", encoding="utf-8").write(html)
    return slug


def write_index(folder, models):
    ordered = sorted(models.items(),
                     key=lambda kv: (kv[0] != "Universal", -len(kv[1]), kv[0]))
    body = ['<div class="eyebrow">Browse by drone</div>',
            '<h1>Find parts for your drone</h1>',
            f'<p>Pick your aircraft and see every part we list that fits it — '
            f'{len(ordered)} models covered.</p>',
            '<div class="modelgrid" style="margin-top:26px;">']
    for model, parts in ordered:
        slug = f"drone-{slugify(model)}.html"
        body.append(f'<a class="modelcard" href="{slug}">'
                    f'<div class="mn">{esc(model)}</div>'
                    f'<div class="mc">{len(parts)} part{"" if len(parts)==1 else "s"}</div></a>')
    body.append('</div>')

    html = HEAD.format(title="Find parts for your drone — Uncle Bubba's Drones",
                       desc="Browse drone parts by aircraft model. Find every "
                            "part that fits your drone in one place.",
                       slug="drones.html", dronesactive=' class="here"')
    html += "\n".join(body) + "\n" + FOOT
    open(os.path.join(folder, "drones.html"), "w", encoding="utf-8").write(html)


def write_sitemap(folder, slugs):
    pages = ["", "drones.html", "guides.html", "guide-motors.html",
             "guide-batteries.html", "guide-props.html", "about.html",
             "contact.html", "disclosure.html"] + slugs
    urls = "\n".join(
        f"  <url><loc>https://unclebubbasdrones.com/{p}</loc></url>" for p in pages)
    open(os.path.join(folder, "sitemap.xml"), "w", encoding="utf-8").write(
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{urls}\n</urlset>\n')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min", type=int, default=3,
                    help="minimum parts before a model gets a page (default 3)")
    ap.add_argument("--dir", default=".", help="folder with your site files")
    args = ap.parse_args()

    print("Uncle Bubba's Drones — model page builder")
    print("=" * 45)

    products = load_products(args.dir)
    models = group_by_model(products, args.min)
    if not models:
        sys.exit("No models had enough parts. Try --min 2.")

    slugs = []
    for model, parts in sorted(models.items(), key=lambda kv: -len(kv[1])):
        slugs.append(write_model_page(args.dir, model, parts))
        print(f"  {len(parts):4}  {model}")

    write_index(args.dir, models)
    write_sitemap(args.dir, slugs)

    print("=" * 45)
    print(f"  {len(slugs)} model pages + drones.html")
    print(f"  sitemap.xml updated with {len(slugs) + 9} pages")
    print("\n  Upload the new drone-*.html files, drones.html and sitemap.xml.")


if __name__ == "__main__":
    main()
