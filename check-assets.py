#!/usr/bin/env python3
"""
check-assets.py — make sure every file the site references is actually committed.

Scans HTML, CSS and JS for local asset references and reports any that are
missing from disk or missing from git. Run before every push:

    python3 check-assets.py

Exit code 0 = everything resolves. 1 = something is missing.

Why this exists: the site was published three times with files missing, because
each hand-rolled check looked in one place and the references lived in another.

  - styles.css and site.js were missed  — the check only looked at <img src>
  - the 8 hero images were missed       — they load via CSS background-image
  - the 22 gallery images were missed   — they live in a JS array

Nothing is scanned by hand any more. This looks everywhere.
"""

import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
ASSET_RE = re.compile(
    r"""['"(]\s*((?:\.{0,2}/)?[A-Za-z0-9._\-/]+\.(?:jpe?g|png|gif|webp|avif|svg|css|js|ico|woff2?|mp4|pdf))\s*['")]""",
    re.I,
)
SCAN_EXT = (".html", ".css", ".js")
SKIP_DIRS = {".git", "_to_delete", "node_modules", ".embed_tmp", "templates"}


def tracked_files():
    try:
        out = subprocess.run(
            ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout
        return set(out.split("\n"))
    except Exception:
        return None


def scan(tracked):
    refs = {}
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if not fn.endswith(SCAN_EXT):
                continue
            src = os.path.join(dirpath, fn)
            rel_src = os.path.relpath(src, ROOT)
            # only scan files that are part of the published site
            if tracked is not None and rel_src not in tracked:
                continue
            try:
                text = open(src, encoding="utf-8", errors="ignore").read()
            except OSError:
                continue
            for m in ASSET_RE.finditer(text):
                target = m.group(1)
                if target.startswith(("http", "//", "data:")):
                    continue
                if target.startswith("/"):          # root-absolute (404.html)
                    resolved = os.path.normpath(target.lstrip("/"))
                else:
                    resolved = os.path.normpath(
                        os.path.join(os.path.dirname(rel_src), target)
                    )
                refs.setdefault(resolved, set()).add(rel_src)
    return refs


def main():
    tracked = tracked_files()
    refs = scan(tracked)

    missing_disk, missing_git = [], []
    for target, sources in sorted(refs.items()):
        if not os.path.exists(os.path.join(ROOT, target)):
            missing_disk.append((target, sources))
        elif tracked is not None and target not in tracked:
            missing_git.append((target, sources))

    print(f"scanned {len(set().union(*refs.values())) if refs else 0} files, "
          f"{len(refs)} asset references\n")

    if missing_disk:
        print(f"❌ {len(missing_disk)} referenced file(s) DO NOT EXIST on disk:")
        for t, s in missing_disk:
            print(f"   {t}\n      referenced by: {', '.join(sorted(s))}")
        print()

    if missing_git:
        print(f"❌ {len(missing_git)} file(s) exist but are NOT COMMITTED "
              f"(they would 404 on the live site):")
        for t, s in missing_git:
            print(f"   {t}\n      referenced by: {', '.join(sorted(s))}")
        print("\n   fix:  git add " + " ".join(t for t, _ in missing_git))
        print()

    if not missing_disk and not missing_git:
        print("✅ every referenced file exists and is committed")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
