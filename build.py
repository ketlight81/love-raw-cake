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
# Interface words that differ between the English and the Icelandic page.
LANG = {
    "en": {"gluten_free": "Gluten-free", "small": " (small)",
           "nutr": "Per 100 g — Protein {0} g · Fat {1} g · Carbs {2} g · {3} kcal"},
    "is": {"gluten_free": "Glútenlaust", "small": " (lítil)",
           "nutr": "Í 100 g — Prótein {0} g · Fita {1} g · Kolvetni {2} g · {3} kcal"},
}
I18N_IS = {  # words used by site.js on the Icelandic page
    "ingredients": "Innihald:", "seeAngles": "⤢ fleiri myndir", "details": "⤢ nánar",
    "dateMsg": "Veldu dagsetningu með minnst 3 daga fyrirvara.",
    "qtySmall": "Litlar kökur: minnst 6 stykki.", "qtyWhole": "Fjöldi heilla kakna.",
}


def load_cakes(lang="en"):
    """Cakes for one language. Icelandic fields end in _is; an empty one falls back to English."""
    L = LANG[lang]

    def t(d, field):
        if lang != "en":
            v = d.get(field + "_" + lang)
            if v not in (None, "") and str(v).strip():
                return str(v).strip()
        return (d.get(field) or "").strip()

    def nfmt(v):
        return str(v).replace(".", ",") if lang == "is" else str(v)

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
            badges.append((L["gluten_free"], 0))
        if t(d, "allergen"):
            badges.append((t(d, "allergen"), 1))
        if t(d, "note"):
            badges.append((t(d, "note"), 2))
        nut = [num(d.get(k)) for k in ("protein", "fat", "carbs", "kcal")]
        nutr = ""
        if all(v is not None for v in nut):
            nutr = L["nutr"].format(*[nfmt(v) for v in nut])
        elif lang == "en" and any(v is not None for v in nut):
            warn(f"{f.name}: nutrition needs all four numbers (protein, fat, carbs, kcal) — not shown")
        photos = [{"src": img(p.get("image")), "cap": t(p, "caption")}
                  for p in (d.get("photos") or []) if p and p.get("image")]
        card_image = img(d.get("card_image")) or (photos[0]["src"] if photos else "")
        if not card_image and lang == "en":
            warn(f"{f.name}: no card photo")
        cakes.append({
            "key": key, "title": t(d, "title") or title, "section": sec,
            "position": num(d.get("position")) or 999,
            "card_text": t(d, "card_text"),
            # Icelandic page: own description, else own card text (not the English description)
            "desc": ((t(d, "description") if lang == "en" or str(d.get("description_" + lang) or "").strip()
                      else t(d, "card_text")) or t(d, "card_text")),
            "ing": t(d, "ingredients"),
            "nutr": nutr,
            "price": num(d.get("price_per_100g")),
            "card_image": card_image,
            "card_alt": t(d, "card_alt") or t(d, "title") or title,
            "photos": photos,
            "badges": [{"label": l, "type": t, "cls": ["", " nut", " tag"][t]} for l, t in badges],
            # the form always sends the English name, so Katya's emails look the same in both languages
            "order_name": title + (" (small)" if sec == "small" else ""),
            "order_label": (t(d, "title") or title) + (L["small"] if sec == "small" else ""),
        })
    cakes.sort(key=lambda c: (SECTIONS.index(c["section"]), c["position"], c["title"]))
    names = [c["order_name"] for c in cakes]
    for n in set(names if lang == "en" else []):
        if names.count(n) > 1:
            warn(f"two cakes with the same name in the order form: {n!r}")
    return cakes


def cakes_js(cakes, prefix="", i18n=None):
    out = {}
    for c in cakes:
        e = {"title": c["title"], "order": c["order_name"], "desc": c["desc"],
             "badges": [[b["label"], b["type"]] for b in c["badges"]]}
        if c["ing"]:
            e["ing"] = c["ing"]
        if c["nutr"]:
            e["nutr"] = c["nutr"]
        e["photos"] = [{"src": prefix + p["src"] if not p["src"].startswith("http") else p["src"],
                        "cap": p["cap"]} for p in c["photos"]]
        out[c["key"]] = e
    js = ("/* GENERATED by build.py from content/cakes/*.md — do not edit by hand. */\n"
          "window.CAKES = " + json.dumps(out, ensure_ascii=False, indent=1) + ";\n")
    if i18n:
        js += "window.I18N = " + json.dumps(i18n, ensure_ascii=False, indent=1) + ";\n"
    return js


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
MONTHS_IS = ["janúar", "febrúar", "mars", "apríl", "maí", "júní", "júlí", "ágúst",
             "september", "október", "nóvember", "desember"]

# Words on the blog pages, per language
BLOG_T = {
    "en": {"lang": "en", "title": "Blog — Love Raw Cake",
           "desc": "Notes on raw cakes, ingredients and the small things behind them — from Katya at Love Raw Cake in Reykjavík.",
           "eyebrow": "Blog", "h1": "Notes from the kitchen.",
           "lead": "Recipes, ingredients and the thinking behind the cakes — written by Katya.",
           "read": "Read the post →", "more": "More posts coming soon.", "all": "← All posts",
           "in_en": "", "menu": "Menu", "tagline": "Healthy raw cakes, handmade with love in Reykjavík.",
           "nav": [("about", "My story"), ("cakes", "Cakes"), ("smallcakes", "Small Cakes"),
                   ("fridaybox", "Friday Box"), ("events", "Events"), ("courses", "Courses")],
           "blog": "Blog", "order": "Order a cake", "switch_label": "Language / Tungumál"},
    "is": {"lang": "is", "title": "Blogg — Love Raw Cake",
           "desc": "Hugleiðingar um hrákökur, hráefni og smáatriðin á bak við þær — frá Katyu hjá Love Raw Cake í Reykjavík.",
           "eyebrow": "Blogg", "h1": "Úr eldhúsinu.",
           "lead": "Uppskriftir, hráefni og hugsunin á bak við kökurnar — Katya skrifar.",
           "read": "Lesa færsluna →", "more": "Fleiri færslur væntanlegar.", "all": "← Allar færslur",
           "in_en": "Á ensku", "menu": "Valmynd", "tagline": "Hollar hrákökur, handgerðar af ást í Reykjavík.",
           "nav": [("about", "Sagan mín"), ("cakes", "Kökur"), ("smallcakes", "Litlar kökur"),
                   ("fridaybox", "Föstudagsbox"), ("events", "Viðburðir"), ("courses", "Námskeið")],
           "blog": "Blogg", "order": "Panta köku", "switch_label": "Tungumál / Language"},
}


def load_posts():
    """Every visible post, with its English text and (if written) its Icelandic text.
    A post counts as translated when it has both an Icelandic title and Icelandic text."""
    posts = []
    md = markdown.Markdown(extensions=["extra", "sane_lists"])

    def to_html(text):
        md.reset()
        return md.convert((text or "").strip())

    for f in sorted((ROOT / "content" / "blog").glob("*.md")):
        d, body = read_md(f)
        if not d or d.get("show") is False:
            continue
        try:
            date = datetime.date.fromisoformat(str(d.get("date"))[:10])
        except ValueError:
            warn(f"{f.name}: date must look like 2026-10-12 — skipped")
            continue
        g = lambda k: str(d.get(k) or "").strip()
        title = g("title")
        p = {"slug": f.stem, "date": date, "image": img(d.get("image")),
             "en": {"title": title,
                    "date_text": f"{date.day} {date.strftime('%B %Y')}",
                    "excerpt": g("excerpt"),
                    "description": g("description") or g("excerpt"),
                    "image_alt": g("image_alt") or title,
                    "body": to_html(body)}}
        if g("title_is") and g("body_is"):
            p["is"] = {"title": g("title_is"),
                       "date_text": f"{date.day}. {MONTHS_IS[date.month - 1]} {date.year}",
                       "excerpt": g("excerpt_is") or g("excerpt"),
                       "description": g("description_is") or g("excerpt_is") or g("description") or g("excerpt"),
                       "image_alt": g("image_alt_is") or g("title_is"),
                       "body": to_html(d.get("body_is"))}
        elif g("title_is") or g("body_is"):
            warn(f"{f.name}: Icelandic version needs both Icelandic title and Icelandic text — shown in English on the Icelandic blog")
        posts.append(p)
    posts.sort(key=lambda p: p["date"], reverse=True)
    return posts


def fix_links(body_html, up):
    """Links/images written relative to the site root work from a post page `up` folders deep."""
    body_html = re.sub(r'(src|href)="(?!https?:|mailto:|tel:|#|/|\.\./)([^"]+)"', r'\1="' + up + r'\2"', body_html)
    body_html = re.sub(r'(src|href)="/(?!/)', r'\1="' + up, body_html)
    return "\n\n  ".join(body_html.split("\n\n"))


def render_blog(env, site, posts):
    """blog.html, blog/*.html (English) and is/blog.html, is/blog/*.html (Icelandic)."""
    out = {}
    list_t, post_t = env.get_template("blog.html"), env.get_template("post.html")
    for lang in ("en", "is"):
        T = BLOG_T[lang]
        is_ = lang == "is"
        # paths seen from the blog list page
        r = "../" if is_ else ""
        cards = []
        for p in posts:
            v = p.get(lang) or p["en"]
            own = lang in p
            href = f"blog/{p['slug']}.html" if own else f"../blog/{p['slug']}.html"
            cards.append({"href": href, "image": r + p["image"] if p["image"] else "", "v": v,
                          "in_en": "" if own else T["in_en"]})
        out[("is/" if is_ else "") + "blog.html"] = list_t.render(
            site=site, T=T, r=r, home="index.html", cards=cards,
            switch={"en": "../blog.html", "is": None} if is_ else {"en": None, "is": "is/blog.html"},
            canonical=site["url"] + ("/is/blog.html" if is_ else "/blog.html"),
            alt_en=site["url"] + "/blog.html", alt_is=site["url"] + "/is/blog.html")
        for p in posts:
            if lang not in p:
                continue
            v = p[lang]
            r = "../../" if is_ else "../"
            if is_:
                switch = {"en": f"../../blog/{p['slug']}.html", "is": None}
            else:
                switch = {"en": None, "is": f"../is/blog/{p['slug']}.html" if "is" in p else "../is/blog.html"}
            out[("is/" if is_ else "") + f"blog/{p['slug']}.html"] = post_t.render(
                site=site, T=T, r=r, home="../index.html", v=v,
                image=r + p["image"] if p["image"] else "", body=fix_links(v["body"], r),
                switch=switch,
                canonical=site["url"] + ("/is" if is_ else "") + f"/blog/{p['slug']}.html",
                alt_en=site["url"] + f"/blog/{p['slug']}.html",
                alt_is=(site["url"] + f"/is/blog/{p['slug']}.html") if "is" in p else "")
    return out


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
            friday_text=friday, schema_json=schema(cakes, site), root="", lang="en"),
        "cakes-data.js": cakes_js(cakes),
    }
    # Icelandic main page → is/index.html (+ its own cake data with Icelandic texts)
    cakes_is = load_cakes("is")
    by_is = {s: [c for c in cakes_is if c["section"] == s] for s in SECTIONS}
    out["is/index.html"] = env.get_template("index.is.html").render(
        site=site, cakes=by_is["cakes"], small=by_is["small"], friday=by_is["friday"],
        friday_text=by_is["friday"][0]["card_text"] if by_is["friday"] else "",
        schema_json="", root="../", lang="is")
    out["is/cakes-data.js"] = cakes_js(cakes_is, prefix="../", i18n=I18N_IS)
    out.update(render_blog(env, site, posts))

    newest = max([p["date"] for p in posts] + [datetime.date(2026, 8, 26)]).isoformat()
    urls = [("", newest, "1.0"), ("is/", newest, "0.9"), ("blog.html", newest, "0.7"),
            ("is/blog.html", newest, "0.6")] + \
           [(f"blog/{p['slug']}.html", p["date"].isoformat(), "0.5") for p in posts] + \
           [(f"is/blog/{p['slug']}.html", p["date"].isoformat(), "0.5") for p in posts if "is" in p]
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
