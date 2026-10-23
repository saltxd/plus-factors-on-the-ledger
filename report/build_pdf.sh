#!/bin/bash
# build_pdf.sh: render report.md as report.pdf (pandoc -> standalone HTML with report.css inline and
# the figures embedded -> headless Chrome). The references-check section at the end of report.md
# documents how each reference was verified; it stays in the markdown and is cut from the PDF here.
set -euo pipefail
DIR=$(cd "$(dirname "$0")" && pwd)
CHROME="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
sed '/BEGIN REFERENCES CHECK/,$d' "$DIR/report.md" > "$TMP/report.md"
pandoc "$TMP/report.md" \
  -f markdown-implicit_figures-tex_math_dollars-subscript-superscript \
  -t html5 -s --embed-resources --resource-path="$DIR" \
  --metadata pagetitle="Plus Factors on the Ledger" \
  --css "$DIR/report.css" -o "$TMP/report.html"
"$CHROME" --headless=new --disable-gpu --no-pdf-header-footer \
  --print-to-pdf="$DIR/report.pdf" "file://$TMP/report.html" 2>/dev/null
pdfinfo "$DIR/report.pdf" | grep -E '^Pages'
