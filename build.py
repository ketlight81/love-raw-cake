#!/usr/bin/env python3
"""Build the Love Raw Cake site from its content files.

    content/cakes/<section>/*.md   one file per cake; folder = section (cakes, small, friday)
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
from jinja2 import Environment, FileSystemLoader, StrictUndefined, Undefined
from markupsafe import Markup

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
    "en": {"gluten_free": "Gluten-free", "small": " (small)", "q_open": "“", "q_close": "”",
           "nutr": "Per 100 g — Protein {0} g · Fat {1} g · Carbs {2} g · {3} kcal"},
    "is": {"gluten_free": "Glútenlaust", "small": " (lítil)", "q_open": "„", "q_close": "“",
           "nutr": "Í 100 g — Prótein {0} g · Fita {1} g · Kolvetni {2} g · {3} kcal"},
}
# ---------------------------------------------------------------- page texts
class MissingText(Undefined):
    """A text field missing from content/text/*.yml (e.g. dropped by an editor tab that was
    opened before the field existed) renders as empty and is reported — it never breaks the build."""
    def _warn(self):
        warn(f"missing text field: {self._undefined_name!r} — add it back in Pages CMS")
        return ""
    def __str__(self): return self._warn()
    def __html__(self): return self._warn()
    def __iter__(self): self._warn(); return iter(())
    def __bool__(self): return False


# ---------------------------------------------------------------- page texts
# Every visible text on the main page and the blog pages lives in content/text/*.yml
# (Katya edits it in Pages CMS). A field ending in _is is the Icelandic version;
# an empty Icelandic field falls back to the English one. List items with show: false are skipped.
TEXT_DIR = ROOT / "content" / "text"


def resolve(d, lang):
    if isinstance(d, list):
        return [resolve(x, lang) for x in d if not (isinstance(x, dict) and x.get("show") is False)]
    if not isinstance(d, dict):
        return "" if d is None else d
    out = {}
    for k, v in d.items():
        if re.search(r"_(is)$", k):
            continue
        if lang != "en":
            alt = d.get(f"{k}_{lang}")
            if alt not in (None, "") and str(alt).strip():
                v = alt
        out[k] = resolve(v, lang)
    return out


def load_text(lang):
    T = {}
    for f in sorted(TEXT_DIR.glob("*.yml")):
        key = re.sub(r"^\d+[a-z]?-", "", f.stem).replace("-", "_")
        try:
            d = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as e:
            warn(f"content/text/{f.name}: not valid ({e})")
            d = {}
        T[key] = resolve(d, lang)
    # 04b (Small Cakes tab + tile) and 04c (Friday Box tile) are separate in the editor,
    # next to their cake lists, but belong to the same page section
    for extra in ("small_cakes_tab", "friday_box_tile"):
        T.setdefault("cakes_section", {}).update(T.pop(extra, {}))
    # order rules (Page · 7): numbers used by the form and inside texts as {days} / {small_min}
    O = T.setdefault("order", {})
    rules = {"days": rule_num(O.get("min_days_ahead"), 3, 0, 60, "min_days_ahead"),
             "small_min": rule_num(O.get("small_min_pieces"), 6, 1, 200, "small_min_pieces")}
    O["min_days_ahead"], O["small_min_pieces"] = rules["days"], rules["small_min"]
    O["phone_required"] = O.get("phone_required") is not False
    O["message_required"] = O.get("message_required") is not False
    return fill(T, rules)


def rule_num(v, default, lo, hi, name):
    try:
        n = int(float(v))
        if lo <= n <= hi:
            return n
    except (TypeError, ValueError):
        pass
    if v not in (None, ""):
        warn(f"content/text/08-order.yml: {name} must be a whole number {lo}–{hi}, got {v!r} — using {default}")
    return default


def fill(x, rules):
    """Put the order-rule numbers into texts: {days} and {small_min}."""
    if isinstance(x, dict):
        return {k: fill(v, rules) for k, v in x.items()}
    if isinstance(x, list):
        return [fill(v, rules) for v in x]
    if isinstance(x, str):
        return x.replace("{days}", str(rules["days"])).replace("{small_min}", str(rules["small_min"]))
    return x


_MD = markdown.Markdown(extensions=["extra"])


def md(text, pill="info-pill"):
    """Light Markdown for one paragraph: **bold**, *italic*, [link](url).
    [[Prices & Delivery]] becomes the button that opens the prices window."""
    _MD.reset()
    h = _MD.convert(str(text or "").strip())
    h = re.sub(r"^<p>(.*)</p>$", r"\1", h, flags=re.S)
    h = h.replace("<strong>", "<b>").replace("</strong>", "</b>")
    h = re.sub(r"\[\[(.+?)\]\]", lambda m: f'<button type="button" class="{pill}" data-open-prices>{m.group(1)}</button>', h)
    return Markup(h)


def plain(text):
    """Text for Google's data: Markdown and buttons removed."""
    h = str(md(text))
    return html.unescape(re.sub(r"<[^>]+>", "", h)).strip()


def i18n(T):
    """Words site.js needs (cake pop-up, order-form hints), from the page texts."""
    U, O = T["cake_popup"], T["order"]
    return {"ingredients": U["ingredients_label"], "seeAngles": U["more_photos"], "details": U["details"],
            "dateMsg": O["date_error"], "qtySmall": O["hint_small"], "qtyWhole": O["hint_whole"]}


def blog_t(T, lang):
    M, B = T["menu_footer"], T["blog_page"]
    return {"lang": lang, "title": B["title"], "desc": B["google_description"],
            "eyebrow": B["eyebrow"], "h1": B["heading"], "lead": B["intro"],
            "read": B["read_more"], "more": B["more_coming"], "all": B["all_posts"],
            "in_en": B["in_english"], "menu": M["menu_button"], "tagline": M["footer_tagline"],
            "nav": [("about", M["menu_story"]), ("cakes", M["menu_cakes"]), ("smallcakes", M["menu_small"]),
                    ("fridaybox", M["menu_friday"]), ("events", M["menu_events"]), ("courses", M["menu_courses"])],
            "blog": M["menu_blog"], "order": M["menu_order"],
            "switch_label": "Tungumál / Language" if lang == "is" else "Language / Tungumál"}




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
    # one folder per section (content/cakes/cakes, /small, /friday) = one list each in Pages CMS
    for f in sorted((ROOT / "content" / "cakes").glob("**/*.md")):
        d, _ = read_md(f)
        if not d or d.get("show") is False:
            continue
        if f.parent.name in SECTIONS:
            d["section"] = f.parent.name
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


def schema(cakes, site, T=None):
    base = (ROOT / "templates" / "schema-base.json").read_text(encoding="utf-8")
    base = base.replace("__SITE_URL__", site["url"]).replace("__EMAIL__", site["email"])
    data = json.loads(base)
    if T is not None:   # the FAQ in Google's data = the questions on the page, always in sync
        for node in data["@graph"]:
            if node.get("@type") == "FAQPage":
                node["mainEntity"] = [{"@type": "Question", "name": plain(q["question"]),
                                       "acceptedAnswer": {"@type": "Answer", "text": plain(q["answer"])}}
                                      for q in T["questions"]["questions"]]
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


def render_blog(env, site, posts, texts):
    """blog.html, blog/*.html (English) and is/blog.html, is/blog/*.html (Icelandic)."""
    out = {}
    list_t, post_t = env.get_template("blog.html"), env.get_template("post.html")
    for lang in ("en", "is"):
        T = blog_t(texts[lang], lang)
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
                      undefined=MissingText, keep_trailing_newline=True)
    env.filters["md"] = md
    env.filters["img"] = img
    texts = {lang: load_text(lang) for lang in ("en", "is")}
    # where order + waitlist forms send (FormSubmit). Editable by Katya in Pages CMS;
    # a NEW address must be activated once — see output/09.11.2026_Pages-CMS-and-order-email-for-Katya.md (section 10)
    oe = str(texts["en"].get("order_email", {}).get("order_email") or "").strip()
    if oe:
        if re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", oe):
            site["email"] = oe
        else:
            warn(f"content/text/14-order-email.yml: {oe!r} is not an email address — kept {site['email']}")
    page = env.get_template("index.html")
    out = {}
    # One template, two languages: index.html (English) and is/index.html (Icelandic)
    for lang, path, root, lang_cakes in (("en", "", "", cakes), ("is", "is/", "../", load_cakes("is"))):
        by_l = {s: [c for c in lang_cakes if c["section"] == s] for s in SECTIONS}
        out[path + "index.html"] = page.render(
            site=site, T=texts[lang], L=LANG[lang], lang=lang, root=root, page_path=path,
            cakes=by_l["cakes"], small=by_l["small"], friday=by_l["friday"],
            friday_text=by_l["friday"][0]["card_text"] if by_l["friday"] else "",
            schema_json=schema(cakes, site, texts["en"]) if lang == "en" else "")
        out[path + "cakes-data.js"] = cakes_js(lang_cakes, prefix=root, i18n=i18n(texts[lang]))
    out.update(render_blog(env, site, posts, texts))
    # page for wrong addresses (GitHub Pages serves 404.html automatically); both languages on one page
    out["404.html"] = env.get_template("404.html").render(E=texts["en"]["not_found"], I=texts["is"]["not_found"])

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
