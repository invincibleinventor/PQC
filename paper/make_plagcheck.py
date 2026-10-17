"""Write main_plagcheck.tex: the 6-page paper without citations, the reference
list or any graphics (figure captions are kept as text), for a similarity
check of the authors' own prose."""
import os, re
HERE = os.path.dirname(os.path.abspath(__file__))
s = open(os.path.join(HERE, "main.tex")).read()
# two sentences use a citation as a noun; reword them so they stay complete
s = s.replace(r"following the structure of \cite{tomamichel2012}, not its exact composable statement",
              r"following the structure of established finite-key analyses, not their exact composable statement")
s = s.replace(r"a composable decoy-state analysis \cite{lim2014} following \cite{tsurumaru2025} is needed",
              r"a composable decoy-state analysis that also accounts for verification in the secrecy definition is needed")
s = re.sub(r"\s*~?\\cite\{[^}]*\}", "", s)                       # citations
s = re.sub(r"\\begin\{tikzpicture\}.*?\\end\{tikzpicture\}\n?", "", s, flags=re.S)  # drawn diagram
s = re.sub(r"\\includegraphics(\[[^\]]*\])?\{[^}]*\}\n?", "", s)    # plotted figures
s = re.sub(r"% balance the columns of the last page\n\\IEEEtriggeratref\{\d+\}\n", "", s)
s = re.sub(r"\\bibliographystyle\{[^}]*\}\n\\bibliography\{[^}]*\}\n", "", s)
assert "\\cite" not in s and "\\includegraphics" not in s and "tikzpicture}" not in s.split("\\begin{document}")[1]
open(os.path.join(HERE, "main_plagcheck.tex"), "w").write(s)
print("wrote main_plagcheck.tex")
