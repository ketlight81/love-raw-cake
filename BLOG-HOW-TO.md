# Adding a blog post

Since 12 October 2026 blog posts are written in **Pages CMS** (app.pagescms.org → Блог →
add entry → Save), not by copying HTML files. Each post is one file in `content/blog/`, and
`build.py` turns it into `blog/<name>.html` and adds it to `blog.html` and `sitemap.xml`.

Katya's step-by-step guide (Russian): `outputs/12.10.2026_Pages-CMS-for-Katya.pdf` in the RawCakes project.

`blog/_TEMPLATE.html` is no longer used and can be deleted.
