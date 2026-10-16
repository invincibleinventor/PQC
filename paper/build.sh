#!/usr/bin/env bash
# Build main.pdf (run from the paper directory).
set -euo pipefail
cd "$(dirname "$0")"
pdflatex -interaction=nonstopmode -halt-on-error main.tex > /dev/null
bibtex main > /dev/null
pdflatex -interaction=nonstopmode -halt-on-error main.tex > /dev/null
pdflatex -interaction=nonstopmode -halt-on-error main.tex > /dev/null
echo "built $(pdfinfo main.pdf | awk '/Pages/{print $2}') pages"
python3 flatten.py
(cd submission && pdflatex -interaction=nonstopmode -halt-on-error main.tex > /dev/null && pdflatex -interaction=nonstopmode -halt-on-error main.tex > /dev/null && rm -f main.aux main.log main.out && echo "submission copy compiles")
