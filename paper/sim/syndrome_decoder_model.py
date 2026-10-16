"""Cycle-faithful Python model of the syndrome-domain LUCID-2D decoder.

The decoder never touches the key bits.  It keeps the row-syndrome
differences d_row[i] (MC+1 bits) and column-syndrome differences d_col[j]
(MR+1 bits) of one R x C tile.  Correcting bit (i, j) XORs h_C(j) into
d_row[i] and h_R(i) into d_col[j], where h_n(x) = (1 << log2 n) | x is the
SECDED column of position x.  The model mirrors rtl/lucid2d_dec.v exactly:
one row (row pass) or one column (column pass) per clock cycle, a scan is a
row pass followed by a column pass, the decoder stops after the first scan
that makes no correction, and at most MAXIT + 1 scans are run.
"""
from __future__ import annotations

import numpy as np


def initial_syndromes(E: np.ndarray):
    """Row and column syndrome differences of error tile E (R x C)."""
    R, C = E.shape
    mr, mc = R.bit_length() - 1, C.bit_length() - 1
    drow = np.zeros(R, dtype=np.int64)
    dcol = np.zeros(C, dtype=np.int64)
    for i, j in zip(*np.nonzero(E)):
        drow[i] ^= (1 << mc) | int(j)
        dcol[j] ^= (1 << mr) | int(i)
    return drow, dcol


def decode(drow, dcol, mr: int, mc: int, maxit: int):
    """Returns (flips, converged, scans, cycles); flips is a list of (i, j)."""
    drow = list(int(x) for x in drow)
    dcol = list(int(x) for x in dcol)
    R, C = 1 << mr, 1 << mc
    flips = []
    scans = 0
    cycles = 0
    converged = False
    while True:
        flipped = False
        nonzero = False
        for i in range(R):
            d = drow[i]
            cycles += 1
            if d:
                nonzero = True
            if d >> mc & 1:
                j = d & (C - 1)
                drow[i] = 0
                dcol[j] ^= (1 << mr) | i
                flips.append((i, j))
                flipped = True
        for j in range(C):
            d = dcol[j]
            cycles += 1
            if d:
                nonzero = True
            if d >> mr & 1:
                i = d & (R - 1)
                dcol[j] = 0
                drow[i] ^= (1 << mc) | j
                flips.append((i, j))
                flipped = True
        scans += 1
        if not flipped:
            converged = not nonzero
            break
        if scans == maxit + 1:
            converged = False
            break
    return flips, converged, scans, cycles


def residual(E: np.ndarray, flips) -> np.ndarray:
    F = E.copy()
    for i, j in flips:
        F[i, j] ^= 1
    return F
