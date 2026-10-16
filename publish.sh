#!/bin/bash
# Publish the Love Raw Cake site in one go.
#   ./publish.sh "what I changed"
# Pulls Katya's latest saves, rebuilds, checks, shows you the page, then pushes.
set -e
cd "$(dirname "$0")"
MSG="${1:-Update site}"

echo "1/5  Getting the latest version from GitHub…"
git pull --rebase --autostash

echo "2/5  Building the pages…"
python3 build.py

echo "3/5  Checking every photo and file is in place…"
python3 check-assets.py || { echo; echo "Something is missing — see above. Nothing was published."; exit 1; }

echo "4/5  Opening the page so you can check it…"
open index.html
read -p "Looks right? Press Enter to publish, or Ctrl+C to stop. " _

echo "5/5  Publishing…"
git add -u
git add content templates is 2>/dev/null || true
[ -d images/uploads ] && git add images/uploads
if git diff --cached --quiet; then
  echo "Nothing changed — nothing to publish."
else
  git commit -m "$MSG"
  git push origin main
  echo; echo "Done. The live site updates in 1–2 minutes (hard-refresh with ⌘⇧R)."
fi
