# LUCID-BB84 conference paper (IEEE format)

This directory holds the LaTeX source of the merged LUCID-BB84 paper, together with the simulator, RTL and scripts behind every number in it.

The merged paper combines:
- the original LUCID-BB84 front end (one-way extended-Hamming syndrome lookup, Toeplitz verification and privacy amplification, Cascade fallback, golden model and RTL);
- the additions developed for this version:
  - LUCID-2D row–column iterative decoding in the syndrome domain;
  - local stall resolution;
  - a one-round second-syndrome fallback;
  - two-tier, block-level verification and privacy amplification;
  - a zero-leakage syndrome-based QBER estimator;
  - a verified and synthesized decoder core;
  - a unified re-evaluation of all schemes.

## Layout

| Path | Content |
|---|---|
| `main.tex` / `main.pdf` | 6-page conference version (`IEEEtran` v1.8b, `conference` option) |
| `main_8page.tex` / `main_8page.pdf` | 8-page extended version (adds the worked example, ablation and burst tables, and the estimator and finite-key figures) |
| `refs.bib` | References; metadata checked against Crossref |
| `figures/` | Vector figures produced by `sim/make_figures.py` |
| `tables/` | Table rows produced by `sim/make_tables.py`; `numbers.txt` lists every value quoted in the text |
| `results/` | Raw JSON results of every experiment, plus `synthesis.json` |
| `sim/lucid_sim.py` | Simulator: Cascade, LUCID 1-D / 2-D with fallback ladder, BP-LDPC, BB84 generator, finite-key bound |
| `sim/run_experiments.py` | All experiments (pilot-then-final parameter selection, fixed seeds) |
| `sim/syndrome_decoder_model.py` | Cycle-faithful model of the syndrome-domain decoder |
| `rtl/lucid2d_dec.v` | Verilog decoder core |
| `rtl/tb_lucid2d_dec.v`, `rtl/gen_and_check.py` | Testbench and RTL-vs-model check |
| `build.sh` | Builds both PDFs and the flattened `submission/` copies |
| `flatten.py` | Writes `submission/main.tex` and `submission/main_8page.tex` with the table rows inlined (single-file upload) |
| `submission/` | Single-file LaTeX source, figures, `refs.bib`, `main.bbl` and PDF, ready for Overleaf or a submission system |

## Rebuild

Requirements: Python 3 with numpy and matplotlib, a TeX Live installation that includes IEEEtran, Icarus Verilog, and Yosys with nextpnr-ecp5.

```sh
python3 sim/run_experiments.py          # roughly 40 min on 4 cores; add --quick for a smoke test
python3 sim/make_tables.py
python3 sim/make_figures.py
bash build.sh                           # pdflatex + bibtex -> main.pdf, main_8page.pdf and submission/
python3 rtl/gen_and_check.py 7 7 20 4   # RTL vs model (MR MC tiles seed)
```

## Before submission

- Authors: Fathina U, Balasubramanian TBR and K. Geetha (School of Computing, SASTRA Deemed University, Thanjavur, India). Register numbers and phone numbers are not part of an IEEE author block; enter them in the conference submission system if it asks for them.
- Check the target conference's page limit and its copyright-notice instructions. Some conferences require a notice on the first page through `\IEEEpubid`; add it only if they ask for it.
- Run the final PDF through IEEE PDF eXpress if the conference requires it.
