"""Generate random tiles, run the RTL testbench with Icarus Verilog, and
compare flips, convergence, scan count and cycle count with the Python model.

Usage: python3 gen_and_check.py MR MC NT SEED
"""
import os, subprocess, sys
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "sim"))
import syndrome_decoder_model as S  # noqa: E402

MR, MC, NT, SEED = (int(x) for x in sys.argv[1:5])
R, C, MAXIT = 1 << MR, 1 << MC, 8
rng = np.random.default_rng(SEED)
work = os.path.join(HERE, "work_%d_%d" % (MR, MC))
os.makedirs(work, exist_ok=True)
exp = []
with open(os.path.join(work, "vec_rows.hex"), "w") as fr, open(os.path.join(work, "vec_cols.hex"), "w") as fc:
    for t in range(NT):
        Q = [0.002, 0.01, 0.02, 0.04, 0.08][t % 5]
        E = (rng.random((R, C)) < Q).astype(np.uint8)
        dr, dc = S.initial_syndromes(E)
        for x in dr: fr.write("%x\n" % x)
        for x in dc: fc.write("%x\n" % x)
        exp.append(S.decode(dr, dc, MR, MC, MAXIT))
subprocess.run(["iverilog", "-g2005", "-o", "sim.vvp", "-P", "tb_lucid2d_dec.MR=%d" % MR, "-P", "tb_lucid2d_dec.MC=%d" % MC,
                "-P", "tb_lucid2d_dec.NT=%d" % NT, os.path.join(HERE, "tb_lucid2d_dec.v"), os.path.join(HERE, "lucid2d_dec.v")],
               cwd=work, check=True)
subprocess.run(["vvp", "-n", "sim.vvp"], cwd=work, check=True, capture_output=True)
got, cur = [], None
for line in open(os.path.join(work, "rtl_out.txt")):
    p = line.split()
    if p[0] == "T":
        cur = dict(flips=[], end=None); got.append(cur)
    elif p[0] == "F":
        cur["flips"].append((int(p[1]), int(p[2])))
    else:
        cur["end"] = tuple(int(x) for x in p[1:])
bad = 0
for t, ((fl, cv, sc, cy), g) in enumerate(zip(exp, got)):
    # RTL counts cycles from the cycle after 'start' to 'done'; one extra cycle
    # elapses for the done flag to register.
    ok = fl == g["flips"] and int(cv) == g["end"][0] and sc == g["end"][1] and g["end"][2] == cy + 1
    bad += not ok
    if not ok and bad < 4:
        print("MISMATCH test", t, "model", cv, sc, cy, len(fl), "rtl", g["end"], len(g["flips"]))
conv = sum(e[1] for e in exp)
print(f"MR={MR} MC={MC}: {NT} tiles, {bad} mismatches, {conv} converged, flips={sum(len(e[0]) for e in exp)}")
sys.exit(1 if bad else 0)
