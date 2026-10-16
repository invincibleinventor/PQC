"""Write submission/main.tex with the generated table rows inlined, plus the
figures, bibliography and compiled PDF, for upload to a submission system."""
import os, re, shutil
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "submission")
os.makedirs(os.path.join(OUT, "figures"), exist_ok=True)
src = open(os.path.join(HERE, "main.tex")).read()
src = re.sub(r"\\tablerows\{([^}]+)\}", lambda m: open(os.path.join(HERE, m.group(1))).read().rstrip("\n"), src)
src = re.sub(r"\\makeatletter\n% table rows generated.*?\\makeatother\n", "", src, flags=re.S)
open(os.path.join(OUT, "main.tex"), "w").write(src)
for f in os.listdir(os.path.join(HERE, "figures")):
    shutil.copy(os.path.join(HERE, "figures", f), os.path.join(OUT, "figures", f))
for f in ["refs.bib", "main.bbl", "main.pdf"]:
    shutil.copy(os.path.join(HERE, f), os.path.join(OUT, f))
print("submission package written to", OUT)
