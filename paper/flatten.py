"""Write submission/main.tex (6 pages) and submission/main_8page.tex with the
generated table rows inlined, plus figures, bibliography files and PDFs."""
import os, re, shutil
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "submission")
os.makedirs(os.path.join(OUT, "figures"), exist_ok=True)
for doc in ["main", "main_8page"]:
    src = open(os.path.join(HERE, doc + ".tex")).read()
    src = re.sub(r"\\tablerows\{([^}]+)\}", lambda m: open(os.path.join(HERE, m.group(1))).read().rstrip("\n"), src)
    src = re.sub(r"\\makeatletter\n% table rows generated.*?\\makeatother\n", "", src, flags=re.S)
    open(os.path.join(OUT, doc + ".tex"), "w").write(src)
    for ext in [".bbl", ".pdf"]:
        shutil.copy(os.path.join(HERE, doc + ext), os.path.join(OUT, doc + ext))
for f in os.listdir(os.path.join(HERE, "figures")):
    shutil.copy(os.path.join(HERE, "figures", f), os.path.join(OUT, "figures", f))
shutil.copy(os.path.join(HERE, "refs.bib"), os.path.join(OUT, "refs.bib"))
print("submission package written to", OUT)
