# Love Raw Cake

Website for **Love Raw Cake** — raw, vegan, gluten-free cakes handmade in
Reykjavík by Katya.

🔗 **Live site:** https://mermina.github.io/love-raw-cake/
📷 **Instagram:** [@love.raw.cake](https://instagram.com/love.raw.cake)

---

## How this was built

It started with a conversation, not a brief. In June 2026 I sat down with Katya
to understand not only what she wanted on a page, but where she wants the
business to be in a few years' time.

Several parts of this site exist because of that conversation rather than
because I proposed them:

- **Courses** — she wants to teach raw baking, and in time to give other people
  work rather than bake alone
- **The blog** — her customers ask the same questions about raw food and
  fermentation, and she would rather answer them properly once
- **The Friday Box** — her own idea for a recurring weekly order
- **No shopping cart** — deliberately. She wants to speak to the person who is
  ordering, so the site sends her an enquiry instead of taking a payment

Everything on the page is hers: her photographs, her ingredient lists, and her
measured nutrition figures where she has them — and no figures where she
hasn't.

## How this site is built to be found

A website that people like is not automatically a website machines can read.
Alongside the design, this site carries **structured data** — a machine-readable
description of the business and every cake, written in
[schema.org](https://schema.org/) vocabulary.

- **`LocalBusiness` / `Bakery`** — who Katya is, where she bakes, since when
- **A `Product` node per cake** — every cake, with its description, photograph and
  category, all pointing back to one business identity
- **`Offer` with `UnitPriceSpecification`** — 1,100 ISK *per 100 g*, not a flat
  price, because that is what she actually charges. Plus the 600 g minimum on
  small cakes and the delivery terms
- **`FAQPage`** — the five questions customers ask most
- **`robots.txt`** explicitly welcoming GPTBot, Google-Extended, ClaudeBot and
  PerplexityBot, and **`sitemap.xml`** so nothing is missed

The rule followed throughout: **only assert what is true.** A placeholder phone
number was removed rather than left in place, and the Friday Box carries no price
because it isn't sold by weight. Structured data is a set of promises made to
machines on the client's behalf — a missing field costs nothing, a wrong one
costs trust.

Full write-up: [`FOUNDABILITY-guide.md`](../docs/FOUNDABILITY-guide.md)

## About the site

A static site — HTML, CSS and a little JavaScript, built with AI assistance (Claude). It covers
Katya's story, the full cake range with ingredients and nutrition, small cakes and the Friday Box,
catering for events, and the courses to come.

Since October 2026 the content is separate from the design, so Katya can edit cakes, photos and
blog posts herself in **[Pages CMS](https://pagescms.org)** without touching code.

## Structure

```
content/cakes/*.md      one file per cake      ← Katya edits these in Pages CMS
content/blog/*.md       one file per post      ← Katya edits these in Pages CMS
images/uploads/         photos uploaded through Pages CMS (shrunk to 2000 px by build.py)
site.yml                address, public email, draft flag
templates/              page design: index.html, blog.html, post.html, schema, robots
build.py                content + templates → the files below
.pages.yml              what Katya sees in the editor
.github/workflows/      runs build.py after every save and commits the result

index.html · blog.html · blog/*.html · cakes-data.js · sitemap.xml · robots.txt
                        GENERATED — never edit these by hand, edits are overwritten
styles.css · site.js    styling and behaviour (edit directly)
images/images_20.08.2026/  original photo set (card / gallery / hero crops)
```

## How to update

**Katya:** app.pagescms.org → change → Save. The site updates in 1–2 minutes.

**Marina (design):**

```bash
git pull                       # always first — Katya's saves change the repo
# edit templates/, styles.css or site.js
python3 build.py               # regenerate the pages
python3 check-assets.py        # must print ✅
git add -A && git commit -m "…" && git push origin main
```

Needs once: `pip3 install jinja2 pyyaml markdown pillow`.

Image naming: `<cake>_main` is the master; `_card` (4:3), `_gal` (1:1) and
`_hero` are the web-sized crops cut from it.

Note that hero images are loaded from `styles.css` via `background-image`, so a
check that only looks at `src` and `href` in the HTML will miss them.

## Built with

HTML, CSS and JavaScript, a small Python build script and Pages CMS, hosted on GitHub Pages.
Built with AI assistance.

---

*Built with [Claude](https://claude.ai/code).*
