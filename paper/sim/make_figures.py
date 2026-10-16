"""Produce the paper's figures (vector PDF) from results/*.json."""
from __future__ import annotations

import json
import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(HERE, "..", "results")
FIG = os.path.join(HERE, "..", "figures")
os.makedirs(FIG, exist_ok=True)

plt.rcParams.update({
    "text.usetex": True,
    "text.latex.preamble": r"\usepackage{mathptmx}",
    "font.family": "serif",
    "font.size": 8,
    "axes.labelsize": 8,
    "axes.titlesize": 8,
    "legend.fontsize": 7,
    "xtick.labelsize": 7,
    "ytick.labelsize": 7,
    "axes.linewidth": 0.6,
    "grid.linewidth": 0.4,
    "grid.color": "#d9d9d6",
    "lines.linewidth": 1.2,
    "lines.markersize": 4,
    "pdf.fonttype": 42,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.02,
})

# One colour, marker and line style per scheme in every figure.
STYLE = {
    "cascade": dict(color="#2a78d6", marker="o", ls="-", label="Cascade"),
    "lucid1d": dict(color="#eb6834", marker="s", ls="--", label="LUCID (1-D)"),
    "lucid2d": dict(color="#1baf7a", marker="^", ls="-", label="LUCID-2D"),
    "ldpc": dict(color="#eda100", marker="D", ls="-.", label="BP-LDPC"),
}
INK = "#0b0b0b"
MUTED = "#52514e"
COLW = 3.5


def load(name):
    with open(os.path.join(RES, name + ".json")) as f:
        return json.load(f)


def style_axes(ax):
    ax.grid(True, which="major")
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)


def fig_success():
    d = load("success_curves")
    fig, axes = plt.subplots(1, 2, figsize=(COLW, 1.75), sharey=True)
    for ax, N, Cc in zip(axes, [16384, 65536], [128, 256]):
        def series(R, stall):
            pts = sorted((r["Q"], r["success"]) for r in d
                         if r["N"] == N and r["R"] == R and r["C"] == Cc and r.get("stall", False) == stall)
            return np.array(pts)
        a = series(1, False)
        b = series(Cc, False)
        c = series(Cc, True)
        s1, s2 = STYLE["lucid1d"], STYLE["lucid2d"]
        ax.plot(a[:, 0] * 100, a[:, 1], color=s1["color"], marker=s1["marker"], ls=s1["ls"],
                label=r"1-D, $(%d,%d)$ blocks" % (Cc, Cc - np.log2(Cc) - 1))
        ax.plot(b[:, 0] * 100, b[:, 1], color=s2["color"], marker="v", ls=":", label=r"2-D, no stall res.")
        ax.plot(c[:, 0] * 100, c[:, 1], color=s2["color"], marker=s2["marker"], ls="-", label=r"2-D + stall res.")
        ax.set_xscale("log")
        ax.set_xticks([0.05, 0.1, 0.2, 0.5, 1, 2])
        ax.set_xticklabels(["0.05", "0.1", "0.2", "0.5", "1", "2"])
        ax.set_xlabel(r"QBER (\%)")
        ax.set_title(r"$N = %d$, tile $%d\times%d$" % (N, Cc, Cc), color=INK)
        style_axes(ax)
    axes[0].set_ylabel("One-round frame success")
    axes[0].set_ylim(-0.03, 1.03)
    h, l = axes[0].get_legend_handles_labels()
    l[0] = "1-D (same row code)"
    fig.legend(h, l, loc="upper center", ncol=3, frameon=False, bbox_to_anchor=(0.53, 1.12),
               handlelength=2.2, columnspacing=1.0)
    fig.savefig(os.path.join(FIG, "fig_success.pdf"))
    plt.close(fig)


def fig_pareto():
    d = load("pareto_N65536")
    fig, axes = plt.subplots(1, 2, figsize=(COLW, 1.9), sharey=False)
    for ax, Q in zip(axes, [0.002, 0.005]):
        for fam in ["cascade", "lucid1d", "lucid2d", "ldpc"]:
            pts = np.array([(r["rounds"], r["r"]) for r in d if r["Q"] == Q and r["scheme"] == fam])
            if fam == "ldpc":  # all LDPC points have exactly one round; offset for visibility
                pts[:, 0] *= 0.82
            s = STYLE[fam]
            ax.scatter(pts[:, 0], pts[:, 1], s=12, marker=s["marker"], facecolor=s["color"],
                       edgecolor="white", linewidth=0.4, label=s["label"], zorder=3)
        ax.set_xscale("log")
        ax.set_xlabel("Mean round trips per frame")
        ax.set_title(r"QBER $= %.1f\%%$" % (Q * 100))
        ax.set_ylim(0.3, 1.0)
        style_axes(ax)
    axes[0].set_ylabel(r"Secret fraction $r$")
    h, l = axes[0].get_legend_handles_labels()
    fig.legend(h, l, loc="upper center", ncol=4, frameon=False, bbox_to_anchor=(0.53, 1.08),
               handletextpad=0.2, columnspacing=0.9)
    fig.tight_layout(w_pad=0.6)
    fig.savefig(os.path.join(FIG, "fig_pareto.pdf"))
    plt.close(fig)


def fig_estimator():
    d = load("estimator")
    fig, ax = plt.subplots(figsize=(COLW, 1.75))
    for Q, ls, mk in [(0.002, "-", "o"), (0.01, "--", "s")]:
        for meth, col, lab in [("syndrome_2d", "#2a78d6", "syndrome meter"), ("sample", "#eb6834", "public sample")]:
            pts = np.array(sorted((r["W"], r["rel_rmse"]) for r in d if r["Q"] == Q and r["method"] == meth))
            ax.plot(pts[:, 0], pts[:, 1], color=col, ls=ls, marker=mk,
                    label=r"%s, QBER $%.1f\%%$" % (lab, Q * 100))
    ax.set_xscale("log", base=2)
    ax.set_yscale("log")
    ax.set_yticks([0.01, 0.02, 0.05, 0.1, 0.2, 0.5])
    ax.set_yticklabels(["0.01", "0.02", "0.05", "0.1", "0.2", "0.5"])
    ax.yaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
    ax.set_ylim(0.01, 0.7)
    ax.set_xlabel(r"Sifted bits observed")
    ax.set_ylabel("Relative RMSE of QBER")
    style_axes(ax)
    ax.legend(frameon=False, ncol=2, loc="lower center", bbox_to_anchor=(0.5, 1.0), columnspacing=1.0,
              handlelength=2.4)
    fig.savefig(os.path.join(FIG, "fig_estimator.pdf"))
    plt.close(fig)


def fig_finite():
    d = load("finite_key")
    fig, axes = plt.subplots(1, 2, figsize=(COLW, 1.85), sharey=True)
    for ax, Q in zip(axes, [0.002, 0.01]):
        for fam in ["cascade", "lucid1d", "lucid2d", "ldpc"]:
            pts = np.array(sorted((r["n"], r["frac"]) for r in d if r["Q"] == Q and r["scheme"] == fam))
            s = STYLE[fam]
            ax.plot(pts[:, 0], pts[:, 1], color=s["color"], ls=s["ls"], marker=s["marker"], markevery=3,
                    label=s["label"])
        pf = [r for r in d if r["Q"] == Q and r["scheme"] == "per_frame_512"][0]
        ax.scatter([512], [pf["frac"]], marker="x", color=INK, s=18, zorder=4, label="per-frame PA ($n=512$)")
        ax.set_xscale("log", base=2)
        ax.set_xticks([2 ** 10, 2 ** 14, 2 ** 18, 2 ** 22, 2 ** 26])
        ax.set_xlabel(r"PA block size $n$ (bits)")
        ax.set_title(r"QBER $= %.1f\%%$" % (Q * 100))
        style_axes(ax)
    axes[0].set_ylabel("Finite-key secret fraction")
    h, l = axes[0].get_legend_handles_labels()
    fig.legend(h, l, loc="upper center", ncol=3, frameon=False, bbox_to_anchor=(0.53, 1.14),
               handlelength=2.2, columnspacing=0.8)
    fig.tight_layout(w_pad=0.5)
    fig.savefig(os.path.join(FIG, "fig_finite.pdf"))
    plt.close(fig)


if __name__ == "__main__":
    fig_success()
    fig_pareto()
    fig_estimator()
    fig_finite()
    print("figures written to", os.path.abspath(FIG))
