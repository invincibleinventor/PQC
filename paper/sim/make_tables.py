"""Emit LaTeX table bodies (paper/tables/*.tex) and a numbers file used to
check every value quoted in the text (paper/tables/numbers.txt)."""
from __future__ import annotations

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "..", "results")
TAB = os.path.join(HERE, "..", "tables")
os.makedirs(TAB, exist_ok=True)
QS = ["0.001", "0.002", "0.005", "0.01", "0.02"]


def load(name):
    with open(os.path.join(RES, name + ".json")) as f:
        return json.load(f)


def pct(q):
    return ("%.1f" % (float(q) * 100))


def fr(x):
    """Round trips: two decimals below 10, one decimal otherwise."""
    return ("%.2f" % x) if x < 10 else ("%.1f" % x)


def tile(p):
    R, C = p
    return (r"$%d$" % C) if R == 1 else (r"$%d{\times}%d$" % (R, C))


notes = []


def reproduction():
    d = load("reproduction_N512")
    rows = []
    for q in QS:
        v = d[q]
        c, l1, ld = v["cascade"], v["lucid1d"], v["ldpc"]
        rows.append(r"%s & %.3f & %s & %.3f & %s & %.3f & %.1f \\" % (
            pct(q), c["r"], fr(c["rounds"]), l1["r"], fr(l1["rounds"]), ld["r"], ld["param"]))
        # throughput-optimal 1-D block from the pilot sweep
        best = max(v["lucid1d"]["pilot"], key=lambda x: x["r"] / x["rounds"])
        gain = (best["r"] / best["rounds"]) / (c["r"] / c["rounds"])
        notes.append("N512 Q=%s: 1-D throughput-optimal block %s r=%.3f rounds=%.2f -> gain over Cascade %.2fx"
                     % (q, best["param"], best["r"], best["rounds"], gain))
        notes.append("N512 Q=%s: casc r=%.3f+-%.3f rounds=%.2f succ=%.3f | 1d r=%.3f+-%.3f rounds=%.2f fb=%.2f C=%s | ldpc r=%.3f f=%s succ=%.3f"
                     % (q, c["r"], c["r_ci"], c["rounds"], c["success"], l1["r"], l1["r_ci"], l1["rounds"], l1["fallback"],
                        l1["param"], ld["r"], ld["param"], ld["success"]))
    open(os.path.join(TAB, "reproduction.tex"), "w").write("\n".join(rows) + "\n")


def matched(N):
    d = load("matched_N%d" % N)
    rows = []
    for q in QS:
        v = d[q]
        c, l1, l2, ld = v["cascade"], v["lucid1d"], v["lucid2d"], v["ldpc"]
        rows.append(r"%s & %.3f & %s & %.3f & %s & %s & %.3f & %s & %.3f & %.1f \\" % (
            pct(q), c["r"], fr(c["rounds"]), l1["r"], fr(l1["rounds"]), tile(l2["param"]), l2["r"], fr(l2["rounds"]),
            ld["r"], ld["param"]))
        notes.append("matched N=%d Q=%s: casc r=%.3f+-%.3f rho=%.2f k1=%s | 1d r=%.3f rho=%.2f %s | 2d r=%.3f+-%.3f rho=%.2f %s succ=%.3f fb=%.3f f=%.2f it=%.2f | ldpc r=%.3f+-%.3f f=%s succ=%.3f it=%.1f | 2d/ldpc=%.3f thr(2d)/thr(casc)=%.1f"
                     % (N, q, c["r"], c["r_ci"], c["rounds"], c["param"], l1["r"], l1["rounds"], l1["param"], l2["r"], l2["r_ci"],
                        l2["rounds"], l2["param"], l2["success"], l2["fallback"], l2["f"], l2["iters"], ld["r"], ld["r_ci"], ld["param"],
                        ld["success"], ld["iters"], l2["r"] / ld["r"], (l2["r"] / l2["rounds"]) / (c["r"] / c["rounds"])))
    open(os.path.join(TAB, "matched_N%d.tex" % N), "w").write("\n".join(rows) + "\n")


def ablation():
    d = load("ablation")
    rows = []
    cases = []
    for r in d:
        key = (r["Q"], r["R"], r["C"])
        if key not in cases:
            cases.append(key)
    for (Q, R, C) in cases:
        v = {(r["stall"], r["second"]): r for r in d if (r["Q"], r["R"], r["C"]) == (Q, R, C)}
        cells = [fr(v[k]["rounds"]) for k in [(0, 0), (2, 0), (0, 16), (2, 16)]]
        rspan = max(v[k]["r"] for k in v) - min(v[k]["r"] for k in v)
        notes.append("ablation r-span Q=%s %dx%d: %.4f" % (Q, R, C, rspan))
        rows.append(r"%s & %s & %.3f & %s \\" % (pct(Q), tile((R, C)), v[(2, 16)]["r"], " & ".join(cells)))
        notes.append("ablation Q=%s %dx%d: " % (Q, R, C) + "; ".join(
            "st%d b%d r=%.3f rho=%.2f fb=%.3f" % (k[0], k[1], v[k]["r"], v[k]["rounds"], v[k]["fallback"])
            for k in [(0, 0), (2, 0), (0, 16), (2, 16)]))
    open(os.path.join(TAB, "ablation.tex"), "w").write("\n".join(rows) + "\n")


def burst():
    d = load("burst")
    rows = []
    for Q in [0.002, 0.005]:
        for Lb in [1, 8, 32, 128]:
            a = [r for r in d if r["Q"] == Q and r["L"] == Lb and not r["interleave"]][0]
            b = [r for r in d if r["Q"] == Q and r["L"] == Lb and r["interleave"]][0]
            notes.append("burst Q=%s L=%d tile %dx%d: row-major r=%.3f rho=%.2f fb=%.3f | interleaved r=%.3f rho=%.2f fb=%.3f"
                         % (Q, Lb, a["R"], a["C"], a["r"], a["rounds"], a["fallback"], b["r"], b["rounds"], b["fallback"]))
            rows.append(r"%s & %d & %.2f & %s & %.2f & %s \\" % (pct(Q), Lb, a["fallback"], fr(a["rounds"]),
                                                                   b["fallback"], fr(b["rounds"])))
    open(os.path.join(TAB, "burst.tex"), "w").write("\n".join(rows) + "\n")


def misc():
    for r in load("bb84_validation"):
        notes.append("bb84 e=%s p=%s sim=%.4f theory=%.4f" % (r["e"], r["p"], r["sim"], r["theory"]))
    cl = load("closed_loop")["summary"]
    for k, v in cl.items():
        notes.append("closed-loop %s r=%.4f rho=%.3f" % (k, v["r"], v["rounds"]))
    est = load("estimator")
    for r in est:
        notes.append("estimator Q=%s W=%d %s relRMSE=%.4f bias=%.4f p0=%.3f" % (r["Q"], r["W"], r["method"], r["rel_rmse"], r["bias"], r["p_zero"]))
    for r in load("finite_key"):
        if r["n"] in (512, 2 ** 16, 2 ** 20, 2 ** 24, 2 ** 26):
            notes.append("finite Q=%s %s n=%d frac=%.4f asym=%s" % (r["Q"], r["scheme"], r["n"], r["frac"], r["asym"]))
    for r in load("success_curves"):
        notes.append("success N=%d %dx%d stall=%s Q=%s succ=%.4f it=%.2f" % (r["N"], r["R"], r["C"], r.get("stall"), r["Q"], r["success"], r["iters"]))


if __name__ == "__main__":
    reproduction()
    matched(65536)
    matched(16384)
    ablation()
    burst()
    misc()
    open(os.path.join(TAB, "numbers.txt"), "w").write("\n".join(notes) + "\n")
    print("\n".join(notes))
