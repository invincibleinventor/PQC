"""Run every experiment reported in the paper and store results as JSON.

Usage:  python3 run_experiments.py [--quick]

Parameter selection (best block size, tile shape, Cascade first block, LDPC
syndrome length) is made on a pilot run; the reported numbers come from an
independent final run with fresh seeds, so the selection does not bias them.
"""
from __future__ import annotations

import json
import math
import os
import sys
import time
from multiprocessing import Pool

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lucid_sim as L  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results")
os.makedirs(OUT, exist_ok=True)
QUICK = "--quick" in sys.argv
QS = [0.001, 0.002, 0.005, 0.01, 0.02]
TAG_FRAME = 64      # original design: 64-bit tag per verification
TAG_ROUTE = 24      # proposed: short per-frame routing tag
TAG_BLOCK = 64      # proposed: one ε_cor tag per privacy-amplification block
N_PA = 1 << 20      # privacy-amplification block (bits) for amortising TAG_BLOCK
ROUND_BUDGET = 1.1  # "one-round" operating budget (mean round trips per frame)


def save(name, obj):
    with open(os.path.join(OUT, name + ".json"), "w") as f:
        json.dump(obj, f, indent=1)


def rng_for(*key):
    return np.random.default_rng(np.random.SeedSequence([20261016, *[int(k) for k in key]]))


def errors(rng, N, Q):
    return (rng.random(N) < Q).astype(np.uint8)


# ---------------------------------------------------------------------------
# frame runners (executed in worker processes)
# ---------------------------------------------------------------------------

def run_scheme(task):
    """task = (scheme, N, Q, param, frames, seed_key)"""
    scheme, N, Q, param, frames, key = task
    rng = rng_for(*key)
    out = []
    code = None
    if scheme == "ldpc":
        m = int(math.ceil(param * L.h2(Q) * N))
        code = L.LDPC(N, m, rng)
    for _ in range(frames):
        e = errors(rng, N, Q)
        if scheme == "cascade":
            e2, lk, rd = L.cascade(e, Q, rng, k1=param)
            r = dict(success=not e2.any(), leak_ec=lk, tags=1, rounds=rd, fallback_used=False, iters_mean=0.0)
        elif scheme == "lucid_frame":      # original 1-D design, whole-frame fallback
            r = L.lucid_frame(e, Q, 1, param, rng, fallback="frame")
        elif scheme == "lucid_sel":        # 1-D or 2-D tiles, selective fallback
            R, C = param
            r = L.lucid_frame(e, Q, R, C, rng, fallback="selective")
        elif scheme == "lucid_none":       # lookup only, with local stall resolution
            R, C = param
            r = L.lucid_frame(e, Q, R, C, rng, fallback="none")
        elif scheme == "lucid_none_plain":  # lookup only, no stall resolution
            R, C = param
            r = L.lucid_frame(e, Q, R, C, rng, fallback="none", stall_rounds=0)
        elif scheme == "lucid_abl":        # ablation: param = (R, C, stall_rounds, second_block)
            R, C, st, b2 = param
            r = L.lucid_frame(e, Q, R, C, rng, fallback="selective", stall_rounds=st, second_block=b2)
        elif scheme == "ldpc":
            r = L.ldpc_frame(e, Q, code)
        else:
            raise ValueError(scheme)
        out.append((bool(r["success"]), float(r["leak_ec"]), int(r["tags"]), float(r["rounds"]),
                    bool(r["fallback_used"]), float(r["iters_mean"])))
    return task, out


def summarise(N, Q, rows, tag_bits, per_bit_extra=0.0):
    a = np.array(rows, dtype=float)
    succ, leak, tags, rounds, fb, it = a.T
    ri = succ * (1.0 - L.h2(Q) - (leak + tag_bits * tags) / N - per_bit_extra)
    n = len(ri)
    return dict(r=float(ri.mean()), r_ci=float(1.96 * ri.std(ddof=1) / math.sqrt(n)) if n > 1 else 0.0,
                success=float(succ.mean()), rounds=float(rounds.mean()), fallback=float(fb.mean()),
                leak_ec_per_bit=float(leak.mean() / N), f=float(leak.mean() / N / L.h2(Q)),
                iters=float(it.mean()), frames=n)


def cascade_k1_candidates(N, Q):
    base = math.ceil(0.73 / Q)
    c = {base // 2, base, base * 2, N // 8, N // 16, N // 32}
    return sorted(k for k in c if 4 <= k <= max(4, N // 4))


def tile_candidates(N, two_d=True):
    cands = []
    for C in [8, 16, 32, 64, 128, 256, 512, 1024]:
        if C <= N and N % C == 0:
            cands.append((1, C))
    if two_d:
        for R in [8, 16, 32, 64, 128, 256, 512]:
            for C in [16, 32, 64, 128, 256, 512, 1024]:
                if C >= R and R * C <= N and N % (R * C) == 0:
                    cands.append((R, C))
    return cands


def best_of(pool, scheme, N, Q, params, frames_pilot, frames_final, tag_bits, extra, key, objective="r"):
    """Pick the parameter maximising `objective` on a pilot run, then re-run.

    objective 'r'   : asymptotic secret fraction per sifted bit;
    objective 'r1'  : best secret fraction among parameters whose mean number
                      of round trips is at most ROUND_BUDGET;
    objective 'eff' : secret fraction per public-channel round trip, which is
                      proportional to secret bits per second when the
                      round-trip time dominates (compute time ignored).
    """
    tasks = [(scheme, N, Q, p, frames_pilot, (*key, 1, i)) for i, p in enumerate(params)]
    res = pool.map(run_scheme, tasks)
    pilot = []
    for (t, rows) in res:
        s = summarise(N, Q, rows, tag_bits, extra)
        if objective == "r":
            score = s["r"]
        elif objective == "r1":  # best r within a one-round budget
            score = s["r"] if s["rounds"] <= ROUND_BUDGET else -1.0 + s["r"] / s["rounds"]
        else:
            score = s["r"] / s["rounds"]
        pilot.append((score, t[3], s))
    pilot.sort(key=lambda x: -x[0])
    best_param = pilot[0][1]
    # final independent run, split across workers
    chunks = 4
    per = max(1, frames_final // chunks)
    tasks = [(scheme, N, Q, best_param, per, (*key, 2, j)) for j in range(chunks)]
    rows = []
    for _, rr in pool.map(run_scheme, tasks):
        rows += rr
    s = summarise(N, Q, rows, tag_bits, extra)
    s["param"] = best_param
    s["pilot"] = [dict(param=p, r=x["r"], rounds=x["rounds"], success=x["success"], fallback=x["fallback"])
                  for _, p, x in pilot]
    return s


# ---------------------------------------------------------------------------
# experiments
# ---------------------------------------------------------------------------

def exp_bb84_validation():
    rng = rng_for(1)
    grid = [(0.0, 0.0), (0.02, 0.0), (0.04, 0.3), (0.08, 0.5), (0.0, 1.0)]
    rows = []
    for e, p in grid:
        sim = L.bb84_qber(300_000, e, p, rng)
        rows.append(dict(e=e, p=p, sim=sim, theory=e + p / 4 - e * p / 2))
    save("bb84_validation", rows)


def exp_reproduction(pool):
    """N = 512, original frame-local accounting (64-bit tag per verification)."""
    N = 512
    fp, ff = (40, 200) if QUICK else (200, 2000)
    out = {}
    for qi, Q in enumerate(QS):
        cas = best_of(pool, "cascade", N, Q, cascade_k1_candidates(N, Q), fp, ff, TAG_FRAME, 0, (10, qi))
        luc = best_of(pool, "lucid_frame", N, Q, [8, 16, 32, 64, 128, 256], fp, ff, TAG_FRAME, 0, (11, qi))
        ldp = best_of(pool, "ldpc", N, Q, [1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0], fp // 2, ff // 2, TAG_FRAME, 0, (12, qi))
        out[str(Q)] = dict(cascade=cas, lucid1d=luc, ldpc=ldp)
        print("repro", Q, {k: round(v["r"], 3) for k, v in out[str(Q)].items()}, flush=True)
    save("reproduction_N512", out)


def exp_success_curves(pool):
    """Lookup-only frame success, 1-D vs 2-D with the same component code."""
    qgrid = [0.0005, 0.001, 0.002, 0.003, 0.005, 0.0075, 0.01, 0.015, 0.02]
    frames = 300 if QUICK else 2000
    configs = [(4096, (1, 64)), (4096, (64, 64)), (16384, (1, 128)), (16384, (128, 128)),
               (65536, (1, 256)), (65536, (256, 256))]
    tasks = []
    for ci, (N, p) in enumerate(configs):
        for qi, Q in enumerate(qgrid):
            tasks.append(("lucid_none_plain", N, Q, p, frames, (20, ci, qi)))
            if p[0] > 1:
                tasks.append(("lucid_none", N, Q, p, frames, (21, ci, qi)))
    res = pool.map(run_scheme, tasks)
    out = []
    for t, rows in res:
        s = summarise(t[1], t[2], rows, 0, 0)
        out.append(dict(N=t[1], Q=t[2], R=t[3][0], C=t[3][1], stall=(t[0] == "lucid_none"),
                        success=s["success"], frames=s["frames"], iters=s["iters"]))
    save("success_curves", out)


def exp_matched(pool, N):
    """All schemes at the same frame size, block-level accounting."""
    extra = TAG_BLOCK / N_PA
    fp, ff = (30, 120) if QUICK else (80, 400)
    out = {}
    for qi, Q in enumerate(QS):
        key = (30 + N.bit_length(), qi)
        cas = best_of(pool, "cascade", N, Q, cascade_k1_candidates(N, Q), max(10, fp // 4), max(40, ff // 4),
                      TAG_ROUTE, extra, (*key, 0), "eff")
        l1 = best_of(pool, "lucid_sel", N, Q, tile_candidates(N, two_d=False), fp, ff, TAG_ROUTE, extra,
                     (*key, 1), "r1")
        l2 = best_of(pool, "lucid_sel", N, Q, [c for c in tile_candidates(N) if c[0] > 1], fp, ff,
                     TAG_ROUTE, extra, (*key, 2), "r1")
        ldp = best_of(pool, "ldpc", N, Q, [1.2, 1.4, 1.6, 2.0, 2.5, 3.0, 4.0], max(10, fp // 4), max(40, ff // 4),
                      TAG_ROUTE, extra, (*key, 3), "r")
        out[str(Q)] = dict(cascade=cas, lucid1d=l1, lucid2d=l2, ldpc=ldp)
        print("matched", N, Q, {k: (round(v["r"], 3), round(v["rounds"], 2), v["param"]) for k, v in out[str(Q)].items()},
              flush=True)
    save(f"matched_N{N}", out)


def exp_estimator():
    """Relative error of QBER estimators versus observation window."""
    rng = rng_for(40)
    trials = 100 if QUICK else 400
    windows = [2 ** k for k in range(14, 21, 2)]  # sifted bits observed
    out = []
    for Q in [0.001, 0.002, 0.005, 0.01]:
        for W in windows:
            est_syn1, est_syn2, est_smp = [], [], []
            for _ in range(trials):
                E = (rng.random(W) < Q).astype(np.uint8)
                # 1-D: blocks of 128
                nz = L.syndrome_nonzero(E.reshape(-1, 128)).mean()
                est_syn1.append(1 - (1 - nz) ** (1 / 128))
                # 2-D: 128 x 128 tiles, rows and columns pooled (method of moments)
                T = E.reshape(-1, 128, 128)
                nr = L.syndrome_nonzero(T.reshape(-1, 128)).mean()
                nc = L.syndrome_nonzero(np.ascontiguousarray(T.transpose(0, 2, 1)).reshape(-1, 128)).mean()
                p = 0.5 * (nr + nc)
                est_syn2.append(1 - (1 - p) ** (1 / 128))
                # public sample: 64 sample bits per 512 key bits (the original design)
                k = W // 8
                est_smp.append(float((rng.random(k) < Q).mean()))
            for name, v in [("syndrome_1d", est_syn1), ("syndrome_2d", est_syn2), ("sample", est_smp)]:
                v = np.array(v)
                out.append(dict(Q=Q, W=W, method=name, bias=float(v.mean() / Q - 1),
                                rel_rmse=float(np.sqrt(np.mean((v - Q) ** 2)) / Q),
                                p_zero=float(np.mean(v == 0))))
    save("estimator", out)


def exp_closed_loop(pool, matched):
    """Closed-loop shape selection with a drifting QBER (N = 65536)."""
    N = 65536
    table = {float(q): tuple(v["lucid2d"]["param"]) for q, v in matched.items()}
    qs = sorted(table)

    def choose(qhat):
        # nearest operating point in log-QBER
        return table[min(qs, key=lambda q: abs(math.log(q) - math.log(max(qhat, 1e-5))))]

    frames = 120 if QUICK else 600
    rng = rng_for(50)
    qtrace = 10 ** (math.log10(0.001) + (math.log10(0.01) - math.log10(0.001)) *
                    0.5 * (1 - np.cos(2 * np.pi * np.arange(frames) / frames)))
    res = {"oracle": [], "syndrome": [], "fixed": [], "sample": []}
    est = 0.002
    fixed = table[0.002]
    for i, Q in enumerate(qtrace):
        e = errors(rng, N, Q)
        for mode in res:
            if mode == "oracle":
                R, C = choose(Q)
            elif mode == "syndrome":
                R, C = choose(est)
            elif mode == "sample":
                R, C = choose(est_s if i else 0.002)
            else:
                R, C = fixed
            r = L.lucid_frame(e.copy(), Q, R, C, rng, fallback="selective")
            ri = r["success"] * (1 - L.h2(Q) - (r["leak_ec"] + TAG_ROUTE * r["tags"]) / N - TAG_BLOCK / N_PA)
            if mode == "sample":
                ri = ri * 512 / 576  # 64 sample bits per 512 key bits are sacrificed
            res[mode].append((float(Q), float(ri), float(r["rounds"])))
        # update estimates for the next frame
        T = e.reshape(-1, 128, 128)
        nr = L.syndrome_nonzero(T.reshape(-1, 128)).mean()
        nc = L.syndrome_nonzero(np.ascontiguousarray(T.transpose(0, 2, 1)).reshape(-1, 128)).mean()
        qh = 1 - (1 - 0.5 * (nr + nc)) ** (1 / 128)
        est = 0.5 * est + 0.5 * qh
        est_s = float((rng.random(N // 8) < Q).mean())
    summ = {m: dict(r=float(np.mean([x[1] for x in v])), rounds=float(np.mean([x[2] for x in v]))) for m, v in res.items()}
    save("closed_loop", dict(summary=summ, trace=res))
    print("closed loop", summ, flush=True)


def exp_finite_key(matched):
    """Finite-key secret fraction versus privacy-amplification block size."""
    out = []
    ns = [2 ** k for k in range(9, 27)]
    for Q in [0.002, 0.005, 0.01]:
        mq = matched[str(Q)]
        for scheme in ["cascade", "lucid1d", "lucid2d", "ldpc"]:
            s = mq[scheme]
            leak_rate = s["leak_ec_per_bit"]  # EC leakage per key bit (successful frames dominate)
            route_rate = TAG_ROUTE * 1.0 / 65536
            for n in ns:
                best = 0.0
                for frac in [0.005, 0.01, 0.02, 0.05, 0.1, 0.2]:
                    k = max(16, int(frac * n))
                    ell = L.finite_key_length(n, k, Q, leak_rate * n, route_rate * n + TAG_BLOCK)
                    best = max(best, s["success"] * ell / (n + k))
                out.append(dict(Q=Q, scheme=scheme, n=n, frac=best, asym=s["r"]))
        # original per-frame pipeline: n = 512 with a 64-bit sample, PA per frame
        out.append(dict(Q=Q, scheme="per_frame_512", n=512,
                        frac=L.finite_key_length(512, 64, Q, 0.0625 * 512, 64) / 576, asym=None))
    save("finite_key", out)


def ge_errors(rng, N, Q, L_burst, pb=0.25):
    """Gilbert-Elliott errors: no errors in G, error prob pb in B; mean burst L."""
    if L_burst <= 1:
        return errors(rng, N, Q)
    pi = Q / pb
    q_bg = 1.0 / L_burst
    q_gb = q_bg * pi / (1 - pi)
    state = np.zeros(N, dtype=bool)
    pos = 0
    cur = rng.random() < pi
    while pos < N:  # alternate geometric sojourns in G and B
        run = int(rng.geometric(q_bg if cur else q_gb))
        if cur:
            state[pos:pos + run] = True
        pos += run
        cur = not cur
    return ((rng.random(N) < pb) & state).astype(np.uint8)


def run_burst(task):
    Q, Lb, R, C, interleave, frames, key = task
    rng = rng_for(*key)
    N = 65536
    perm = rng_for(999).permutation(N)  # public interleaver
    rows = []
    for _ in range(frames):
        e = ge_errors(rng, N, Q, Lb)
        if interleave:
            e = e[perm]
        r = L.lucid_frame(e, Q, R, C, rng, fallback="selective")
        rows.append((bool(r["success"]), float(r["leak_ec"]), int(r["tags"]), float(r["rounds"]),
                     bool(r["fallback_used"]), float(r["iters_mean"])))
    return task, rows


def exp_burst(pool, matched):
    frames = 30 if QUICK else 150
    tasks = []
    for qi, Q in enumerate([0.002, 0.005]):
        R, C = matched[str(Q)]["lucid2d"]["param"]
        for li, Lb in enumerate([1, 8, 32, 128]):
            for il in [False, True]:
                tasks.append((Q, Lb, R, C, il, frames, (60, qi, li, int(il))))
    out = []
    for t, rows in pool.map(run_burst, tasks):
        s = summarise(65536, t[0], rows, TAG_ROUTE, TAG_BLOCK / N_PA)
        out.append(dict(Q=t[0], L=t[1], R=t[2], C=t[3], interleave=t[4], **s))
        print("burst", t[:5], round(s["r"], 3), round(s["fallback"], 3), flush=True)
    save("burst", out)


def exp_ablation(pool):
    """Contribution of stall resolution and the second syndrome message."""
    N = 65536
    extra = TAG_BLOCK / N_PA
    frames = 40 if QUICK else 300
    cases = [(0.002, 256, 256), (0.005, 64, 128), (0.005, 128, 128), (0.01, 32, 64), (0.01, 64, 64)]
    tasks = []
    for ci, (Q, R, C) in enumerate(cases):
        for vi, (st, b2) in enumerate([(0, 0), (2, 0), (0, 16), (2, 16)]):
            tasks.append(("lucid_abl", N, Q, (R, C, st, b2), frames, (80, ci, vi)))
    out = []
    for t, rows in pool.map(run_scheme, tasks):
        s = summarise(N, t[2], rows, TAG_ROUTE, extra)
        R, C, st, b2 = t[3]
        out.append(dict(Q=t[2], R=R, C=C, stall=st, second=b2, **s))
    save("ablation", out)
    print("ablation done", flush=True)


def exp_pareto(pool):
    """Secret fraction versus mean round trips for every configuration."""
    N = 65536
    extra = TAG_BLOCK / N_PA
    out = []
    for qi, Q in enumerate([0.002, 0.005]):
        tasks = []
        for i, p in enumerate(cascade_k1_candidates(N, Q)):
            tasks.append(("cascade", N, Q, p, 30 if QUICK else 60, (70, qi, 0, i)))
        for i, p in enumerate(tile_candidates(N)):
            tasks.append(("lucid_sel", N, Q, p, 40 if QUICK else 200, (70, qi, 1, i)))
        for i, p in enumerate([1.2, 1.4, 1.6, 2.0, 2.5, 3.0, 4.0]):
            tasks.append(("ldpc", N, Q, p, 20 if QUICK else 60, (70, qi, 2, i)))
        for t, rows in pool.map(run_scheme, tasks):
            s = summarise(N, Q, rows, TAG_ROUTE, extra)
            fam = t[0] if t[0] != "lucid_sel" else ("lucid2d" if t[3][0] > 1 else "lucid1d")
            out.append(dict(Q=Q, scheme=fam, param=t[3], r=s["r"], rounds=s["rounds"], success=s["success"],
                            fallback=s["fallback"], f=s["f"], iters=s["iters"]))
        print("pareto", Q, len(out), flush=True)
    save("pareto_N65536", out)


def main():
    t0 = time.time()
    only = [a for a in sys.argv[1:] if not a.startswith("--")]
    run = (lambda name: not only or name in only)
    if run("bb84"):
        exp_bb84_validation()
    if run("estimator"):
        exp_estimator()
    with Pool(os.cpu_count()) as pool:
        if run("success"):
            exp_success_curves(pool)
        if run("repro"):
            exp_reproduction(pool)
        if run("matched"):
            exp_matched(pool, 65536)
            exp_matched(pool, 16384)
        if run("pareto"):
            exp_pareto(pool)
        if run("ablation"):
            exp_ablation(pool)
        with open(os.path.join(OUT, "matched_N65536.json")) as f:
            matched = json.load(f)
        if run("finite"):
            exp_finite_key(matched)
        if run("closed"):
            exp_closed_loop(pool, matched)
        if run("burst"):
            exp_burst(pool, matched)
    print("done in %.0f s" % (time.time() - t0))


if __name__ == "__main__":
    main()
