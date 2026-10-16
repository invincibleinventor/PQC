#!/usr/bin/env bash
# Build the 6-page paper (main.pdf) and the 8-page extended copy
# (main_8page.pdf), then the flattened single-file submission copies.
set -euo pipefail
cd "$(dirname "$0")"
for doc in main main_8page; do
  pdflatex -interaction=nonstopmode -halt-on-error "$doc.tex" > /dev/null
  bibtex "$doc" > /dev/null
  pdflatex -interaction=nonstopmode -halt-on-error "$doc.tex" > /dev/null
  pdflatex -interaction=nonstopmode -halt-on-error "$doc.tex" > /dev/null
  echo "built $doc.pdf: $(pdfinfo "$doc.pdf" | awk '/Pages/{print $2}') pages"
done
python3 flatten.py
(cd submission && for doc in main main_8page; do
   pdflatex -interaction=nonstopmode -halt-on-error "$doc.tex" > /dev/null
   pdflatex -interaction=nonstopmode -halt-on-error "$doc.tex" > /dev/null
 done && rm -f ./*.aux ./*.log ./*.out && echo "submission copies compile")
