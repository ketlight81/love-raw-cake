#!/usr/bin/env python3
"""Build the Love Raw Cake site from its content files.

    content/cakes/*.md   one file per cake (Katya edits these in Pages CMS)
    content/blog/*.md    one file per blog post (Katya edits these in Pages CMS)
    site.yml             address, public email, draft flag (Marina only)
    templates/           page design (Marina only)

        python3 build.py          # writes index.html, blog.html, blog/*.html,
                                  # cakes-data.js, sitemap.xml, robots.txt
        python3 build.py --check  # build in memory, report problems, write nothing

Needs: pip install jinja2 pyyaml markdown pillow   (pillow is optional; it shrinks big uploads)
GitHub runs this automatically after every save in Pages CMS (.github/workflows/build.yml).
"""
import datetime, html, json, pathlib, re, sys

import markdown
import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

ROOT = pathlib.Path(__file__).resolve().parent
SECTIONS = ("cakes", "small", "friday")
UPLOADS = ROOT / "images" / "uploads"
MAX_SIDE = 2000          # px, long side, for photos uploaded through Pages CMS

problems = []


def warn(msg):
    problems.append(msg)


def read_md(path):
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?(.*)$", text, re.S)
    if not m:
        warn(f"{path.relative_to(ROOT)}: no front matter (--- block) at the top")
        return {}, text
    return (yaml.safe_load(m.group(1)) or {}), m.group(2)


def img(path):
    """Image paths are stored relative to the site root, without a leading slash,
    so they work both on mermina.github.io/love-raw-cake/ and on loverawcake.com."""
    p = (path or "").strip()
    if p.startswith("http"):
        return p
    p = p.lstrip("/")
    if p and not (ROOT / p).exists():
        warn(f"missing image file: {p}")
    return p


def num(v):
    if v in (None, ""):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        warn(f"not a number: {v!r}")
        return None
    return int(f) if f.is_integer() else f


# ---------------------------------------------------------------- cakes
def load_cakes():
    cakes = []
    for f in sorted((ROOT / "content" / "cakes").glob("*.md")):
        d, _ = read_md(f)
        if not d or d.get("show") is False:
            continue
        key = f.stem
        title = (d.get("title") or "").strip()
        if not title:
            warn(f"{f.name}: no title — skipped")
            continue
        sec = d.get("section", "cakes")
        if sec not in SECTIONS:
            warn(f"{f.name}: section must be one of {SECTIONS}, got {sec!r}")
            sec = "cakes"
        badges = []
        if d.get("vegan", True):
            badges.append(("Vegan", 0))
        if d.get("gluten_free", True):
            badges.append(("Gluten-free", 0))
        if (d.get("allergen") or "").strip():
            badges.append((d["allergen"].strip(), 1))
        if (d.get("note") or "").strip():
            badges.append((d["note"].strip(), 2))
        nut = [num(d.get(k)) for k in ("protein", "fat", "carbs", "kcal")]
        nutr = ""
        if all(v is not None for v in nut):
            nutr = (f"Per 100 g — Protein {nut[0]} g · Fat {nut[1]} g · "
                    f"Carbs {nut[2]} g · {nut[3]} kcal")
        elif any(v is not None for v in nut):
            warn(f"{f.name}: nutrition needs all four numbers (protein, fat, carbs, kcal) — not shown")
        photos = [{"src": img(p.get("image")), "cap": (p.get("caption") or "").strip()}
                  for p in (d.get("photos") or []) if p and p.get("image")]
        card_image = img(d.get("card_image")) or (photos[0]["src"] if photos else "")
        if not card_image:
            warn(f"{f.name}: no card photo")
        cakes.append({
            "key": key, "title": title, "section": sec,
            "position": num(d.get("position")) or 999,
            "card_text": (d.get("card_text") or "").strip(),
            "desc": (d.get("description") or d.get("card_text") or "").strip(),
            "ing": (d.get("ingredients") or "").strip(),
            "nutr": nutr,
            "price": num(d.get("price_per_100g")),
            "card_image": card_image,
            "card_alt": (d.get("card_alt") or title).strip(),
            "photos": photos,
            "badges": [{"label": l, "type": t, "cls": ["", " nut", " tag"][t]} for l, t in badges],
            "order_name": title + (" (small)" if sec == "small" else ""),
        })
    cakes.sort(key=lambda c: (SECTIONS.index(c["section"]), c["position"], c["title"]))
    names = [c["order_name"] for c in cakes]
    for n in set(names):
        if names.count(n) > 1:
            warn(f"two cakes with the same name in the order form: {n!r}")
    return cakes


def cakes_js(cakes):
    out = {}
    for c in cakes:
        e = {"title": c["title"], "order": c["order_name"], "desc": c["desc"],
             "badges": [[b["label"], b["type"]] for b in c["badges"]]}
        if c["ing"]:
            e["ing"] = c["ing"]
        if c["nutr"]:
            e["nutr"] = c["nutr"]
        e["photos"] = c["photos"]
        out[c["key"]] = e
    return ("/* GENERATED by build.py from content/cakes/*.md — do not edit by hand. */\n"
            "window.CAKES = " + json.dumps(out, ensure_ascii=False, indent=1) + ";\n")


def schema(cakes, site):
    base = (ROOT / "templates" / "schema-base.json").read_text(encoding="utf-8")
    base = base.replace("__SITE_URL__", site["url"]).replace("__EMAIL__", site["email"])
    data = json.loads(base)
    biz = {"@id": f"{site['url']}/#business"}
    for c in cakes:
        p = {"@type": "Product", "name": c["title"], "brand": dict(biz),
             "category": "Raw vegan gluten-free cake", "description": c["card_text"],
             "image": f"{site['url']}/{c['card_image']}"}
        if c["price"] is not None:
            offer = {
                "@type": "Offer", "priceCurrency": "ISK",
                "availability": "https://schema.org/InStock",
                "priceSpecification": {
                    "@type": "UnitPriceSpecification", "price": c["price"], "priceCurrency": "ISK",
                    "referenceQuantity": {"@type": "QuantitativeValue", "value": 100, "unitCode": "GRM"}},
                "shippingDetails": {
                    "@type": "OfferShippingDetails",
                    "shippingDestination": {"@type": "DefinedRegion", "addressCountry": "IS",
                                            "addressRegion": "Capital Region"},
                    "shippingRate": {"@type": "MonetaryAmount", "currency": "ISK", "minValue": 0, "value": 2000},
                    "freeShippingThreshold": {"@type": "MonetaryAmount", "currency": "ISK", "value": 15000}},
                "seller": dict(biz)}
            if c["section"] == "small":
                offer["eligibleQuantity"] = {"@type": "QuantitativeValue", "minValue": 600, "unitCode": "GRM"}
            p["offers"] = offer
        data["@graph"].append(p)
    return json.dumps(data, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------- blog
def load_posts():
    posts = []
    md = markdown.Markdown(extensions=["extra", "sane_lists"])
    for f in sorted((ROOT / "content" / "blog").glob("*.md")):
        d, body = read_md(f)
        if not d or d.get("show") is False:
            continue
        try:
            date = datetime.date.fromisoformat(str(d.get("date"))[:10])
        except ValueError:
            warn(f"{f.name}: date must look like 2026-10-12 — skipped")
            continue
        md.reset()
        body_html = md.convert(body.strip())
        # images/links written relative to the site root work from blog/ too
        body_html = re.sub(r'(src|href)="(?!https?:|mailto:|#|/|\.\./)([^"]+)"', r'\1="../\2"', body_html)
        body_html = re.sub(r'(src|href)="/(?!/)', r'\1="../', body_html)
        title = (d.get("title") or "").strip()
        posts.append({
            "slug": f.stem, "title": title, "date": date,
            "date_text": f"{date.day} {date.strftime('%B %Y')}",
            "excerpt": (d.get("excerpt") or "").strip(),
            "description": (d.get("description") or d.get("excerpt") or "").strip(),
            "image": img(d.get("image")), "image_alt": (d.get("image_alt") or title).strip(),
            "body_html": "\n\n  ".join(body_html.split("\n\n")),
        })
    posts.sort(key=lambda p: p["date"], reverse=True)
    return posts


# ---------------------------------------------------------------- photos
def shrink_uploads():
    """Photos uploaded through Pages CMS straight from a phone can be 5 MB+.
    Shrink anything in images/uploads/ to MAX_SIDE px on the long side."""
    try:
        from PIL import Image, ImageOps
    except ImportError:
        return
    if not UPLOADS.exists():
        return
    for f in UPLOADS.rglob("*"):
        if f.suffix.lower() not in (".jpg", ".jpeg", ".png", ".webp"):
            continue
        with Image.open(f) as im:
            if max(im.size) <= MAX_SIDE and f.stat().st_size < 1_200_000:
                continue
            im = ImageOps.exif_transpose(im)
            im.thumbnail((MAX_SIDE, MAX_SIDE))
            if f.suffix.lower() in (".jpg", ".jpeg"):
                im.convert("RGB").save(f, quality=82, optimize=True, progressive=True)
            else:
                im.save(f, optimize=True)
        print(f"  shrank {f.relative_to(ROOT)}")


# ---------------------------------------------------------------- main
def main():
    check = "--check" in sys.argv
    site = yaml.safe_load((ROOT / "site.yml").read_text(encoding="utf-8"))
    site["url"] = site["url"].rstrip("/")
    site["public_url"] = site["public_url"].rstrip("/")
    if not check:
        shrink_uploads()
    cakes = load_cakes()
    posts = load_posts()
    by = {s: [c for c in cakes if c["section"] == s] for s in SECTIONS}
    friday = by["friday"][0]["card_text"] if by["friday"] else ""

    env = Environment(loader=FileSystemLoader(ROOT / "templates"), autoescape=True,
                      undefined=StrictUndefined, keep_trailing_newline=True)
    out = {
        "index.html": env.get_template("index.html").render(
            site=site, cakes=by["cakes"], small=by["small"], friday=by["friday"],
            friday_text=friday, schema_json=schema(cakes, site)),
        "blog.html": env.get_template("blog.html").render(site=site, posts=posts),
        "cakes-data.js": cakes_js(cakes),
    }
    post_t = env.get_template("post.html")
    for p in posts:
        out[f"blog/{p['slug']}.html"] = post_t.render(site=site, p=p)

    newest = max([p["date"] for p in posts] + [datetime.date(2026, 8, 26)]).isoformat()
    urls = [("", newest, "1.0"), ("blog.html", newest, "0.7")] + \
           [(f"blog/{p['slug']}.html", p["date"].isoformat(), "0.5") for p in posts]
    out["sitemap.xml"] = ('<?xml version="1.0" encoding="UTF-8"?>\n'
                          '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' +
                          "".join(f"  <url>\n    <loc>{site['public_url']}/{u}</loc>\n"
                                  f"    <lastmod>{d}</lastmod>\n    <priority>{pr}</priority>\n  </url>\n"
                                  for u, d, pr in urls) + "</urlset>\n")
    robots = (ROOT / "templates" / "robots.txt").read_text(encoding="utf-8")
    out["robots.txt"] = robots.replace("__SITE_URL__", site["url"]).replace("__PUBLIC_URL__", site["public_url"])

    for name, text in out.items():
        if "{{" in text or "{%" in text:
            warn(f"{name}: template code left in the output")
    if not check:
        changed = 0
        for name, text in out.items():
            p = ROOT / name
            p.parent.mkdir(parents=True, exist_ok=True)
            if not p.exists() or p.read_text(encoding="utf-8") != text:
                p.write_text(text, encoding="utf-8")
                changed += 1
                print(f"  wrote {name}")
        print(f"Built {len(cakes)} cakes, {len(posts)} posts — {changed} file(s) changed.")
    else:
        print(f"Check: {len(cakes)} cakes, {len(posts)} posts.")
    for m in problems:
        print("  ⚠", m)
    return 1 if problems and check else 0


if __name__ == "__main__":
    sys.exit(main())
