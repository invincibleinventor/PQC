"""Unified reconciliation simulator for the LUCID-BB84 / LUCID-2D paper.

All schemes operate on the sifted error pattern e = a XOR b.  Every hint that
Alice discloses (block parity, SECDED syndrome, LDPC syndrome) is a linear
function of her string, so Bob's view of the difference between his and
Alice's hints is the same linear function of e.  Simulating e alone is
therefore exact for the bit-flip models used in the paper (assumptions A1-A3).

Schemes
  * cascade()          - Brassard-Salvail Cascade, 4 passes, back-tracking,
                         lock-step round counting (a lower bound on rounds).
  * lucid_frame()      - LUCID front-end with tiles of R x C bits.  R == 1 is
                         the original one-dimensional SECDED lookup; R > 1 is
                         LUCID-2D (iterated row/column lookup).  Optional
                         Cascade fallback, either on the whole frame (as in the
                         original design) or only on the tiles/blocks that did
                         not decode ("selective" fallback).
  * ldpc_frame()       - one-way syndrome LDPC with sum-product BP.
"""
from __future__ import annotations

import math
import numpy as np

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def h2(p: float) -> float:
    """Binary entropy in bits."""
    if p <= 0.0 or p >= 1.0:
        return 0.0
    return -p * math.log2(p) - (1.0 - p) * math.log2(1.0 - p)


def log2i(n: int) -> int:
    m = n.bit_length() - 1
    assert 1 << m == n, f"{n} is not a power of two"
    return m


def secded_leak(n: int) -> int:
    """Independent syndrome bits of an extended Hamming code of length n."""
    return log2i(n) + 1


def tile_leak(R: int, C: int) -> int:
    """Rank of the syndrome map of an R x C tile.

    R == 1: one SECDED block of length C.
    R > 1 : product of two extended Hamming codes; rows have length C,
            columns have length R.  Rank = RC - k_r k_c.
    """
    b = secded_leak(C)
    if R == 1:
        return b
    a = secded_leak(R)
    return R * b + C * a - a * b


# ---------------------------------------------------------------------------
# SECDED lookup (vectorised over many blocks)
# ---------------------------------------------------------------------------

_POS_MASK_CACHE: dict[int, np.ndarray] = {}


def _pos_masks(n: int) -> np.ndarray:
    """Boolean matrix (m, n): row k selects positions whose bit k is set."""
    if n not in _POS_MASK_CACHE:
        m = log2i(n)
        idx = np.arange(n)
        _POS_MASK_CACHE[n] = np.stack([((idx >> k) & 1).astype(bool) for k in range(m)]) if m else np.zeros((0, n), bool)
    return _POS_MASK_CACHE[n]


def secded_correct(E: np.ndarray):
    """One lookup pass over every row of E (shape (blocks, n), uint8).

    Returns (E_after, flagged) where flagged marks rows whose syndrome
    difference indicated a detected double error (even weight, non-zero).
    Rows with odd overall parity are 'corrected' at the indicated position,
    which is a mis-correction when the true weight is >= 3.
    """
    n = E.shape[1]
    masks = _pos_masks(n)
    par = (E.sum(axis=1) & 1).astype(np.int64)
    pos = np.zeros(E.shape[0], dtype=np.int64)
    for k in range(masks.shape[0]):
        pos |= ((E[:, masks[k]].sum(axis=1) & 1).astype(np.int64)) << k
    single = par == 1
    flagged = (par == 0) & (pos != 0)
    if single.any():
        r = np.nonzero(single)[0]
        E[r, pos[r]] ^= 1
    return E, flagged


def syndrome_nonzero(E: np.ndarray) -> np.ndarray:
    """True where the SECDED syndrome of a row of E is non-zero."""
    n = E.shape[1]
    masks = _pos_masks(n)
    nz = (E.sum(axis=1) & 1).astype(bool)
    for k in range(masks.shape[0]):
        nz |= (E[:, masks[k]].sum(axis=1) & 1).astype(bool)
    return nz


def _iterate(T: np.ndarray, iters: int):
    """Iterated row/column SECDED lookup on a stack of tiles.

    T: (tiles, R, C) uint8 error patterns; modified in place.
    Returns (converged, iterations_used) per tile.  A tile is 'converged'
    when all of its row and column syndrome differences are zero, which Bob
    can observe without any extra communication.
    """
    nt, R, C = T.shape
    if R == 1:
        flat = T.reshape(nt, C)
        secded_correct(flat)
        conv = ~syndrome_nonzero(flat)
        return conv, np.ones(nt, dtype=np.int64)
    used = np.zeros(nt, dtype=np.int64)
    active = np.ones(nt, dtype=bool)
    for it in range(iters):
        idx = np.nonzero(active)[0]
        if idx.size == 0:
            break
        sub = T[idx]
        rows = sub.reshape(-1, C)
        secded_correct(rows)
        sub = rows.reshape(idx.size, R, C)
        cols = np.ascontiguousarray(sub.transpose(0, 2, 1)).reshape(-1, R)
        secded_correct(cols)
        sub = cols.reshape(idx.size, C, R).transpose(0, 2, 1)
        T[idx] = sub
        used[idx] += 1
        # stopping rule: all row and column syndromes match
        rnz = syndrome_nonzero(np.ascontiguousarray(sub).reshape(-1, C)).reshape(idx.size, R).any(axis=1)
        cnz = syndrome_nonzero(np.ascontiguousarray(sub.transpose(0, 2, 1)).reshape(-1, R)).reshape(idx.size, C).any(axis=1)
        done = ~(rnz | cnz)
        active[idx[done]] = False
    conv = ~active
    return conv, used


def nonzero_lines(tile: np.ndarray):
    """Indices of rows and columns of one tile whose syndrome is non-zero."""
    rn = np.nonzero(syndrome_nonzero(tile))[0]
    cn = np.nonzero(syndrome_nonzero(np.ascontiguousarray(tile.T)))[0]
    return rn, cn


def decode_tiles(T: np.ndarray, iters: int, stall_rounds: int = 0, max_cand: int = 16):
    """Iterated row/column lookup, optionally followed by local stall resolution.

    Stall resolution (no communication): for a tile that did not converge,
    Bob flips every intersection of a non-zero row and a non-zero column
    (when there are at most max_cand intersections) and iterates again.
    A 2x2 'rectangle' of errors, the dominant stall pattern of a product of
    SECDED codes, is removed exactly by one such step.
    """
    conv, used = _iterate(T, iters)
    if T.shape[1] == 1 or stall_rounds == 0:
        return conv, used
    for _ in range(stall_rounds):
        bad = np.nonzero(~conv)[0]
        if bad.size == 0:
            break
        for t in bad:
            rn, cn = nonzero_lines(T[t])
            if 0 < rn.size * cn.size <= max_cand:
                T[t][np.ix_(rn, cn)] ^= 1
        sub = T[bad]
        c2, u2 = _iterate(sub, iters)
        T[bad] = sub
        conv[bad] = c2
        used[bad] += u2
    return conv, used


# ---------------------------------------------------------------------------
# Cascade
# ---------------------------------------------------------------------------

def cascade(e: np.ndarray, Q: float, rng: np.random.Generator, passes: int = 4,
            k1: int | None = None):
    """Brassard-Salvail Cascade on error pattern e (modified copy returned).

    Pass-1 block size k1 defaults to ceil(0.73 / Q) (true QBER), capped at
    N/8 so that short frames keep several blocks; it doubles every pass.  All binary searches that can
    proceed in parallel do so; a 'round' is one parity request/response.
    Returns (e_after, leaked_bits, rounds).
    """
    e = e.copy()
    N = e.size
    if N == 0:
        return e, 0, 0
    if k1 is None:
        k1 = min(math.ceil(0.73 / max(Q, 1e-6)), N // 8)
    k1 = int(min(N, max(2, k1)))
    perms, inv, sizes, nblocks, bpar = [], [], [], [], []
    leak = 0
    rounds = 0
    for p in range(passes):
        perm = np.arange(N) if p == 0 else rng.permutation(N)
        k = min(N, k1 << p)
        perms.append(perm)
        iv = np.empty(N, dtype=np.int64)
        iv[perm] = np.arange(N)
        inv.append(iv)
        sizes.append(k)
        nb = math.ceil(N / k)
        nblocks.append(nb)
        ep = e[perm]
        pad = nb * k - N
        if pad:
            ep = np.concatenate([ep, np.zeros(pad, dtype=e.dtype)])
        bpar.append((ep.reshape(nb, k).sum(axis=1) & 1).astype(np.int64))
        leak += nb  # block parities of this pass
        rounds += 1
        # searches keyed by (pass, block) -> [lo, hi) in permuted order
        searches: dict[tuple[int, int], list[int]] = {}
        while True:
            # (re)start searches for every odd block in passes 0..p
            new = {}
            for q in range(p + 1):
                odd = np.nonzero(bpar[q])[0]
                for j in odd:
                    key = (q, int(j))
                    lo0 = int(j) * sizes[q]
                    hi0 = min(N, lo0 + sizes[q])
                    st = searches.get(key)
                    if st is not None:
                        lo, hi = st
                        if (e[perms[q][lo:hi]].sum() & 1) == 1:
                            new[key] = st
                            continue
                    new[key] = [lo0, hi0]
            searches = new
            if not searches:
                break
            rounds += 1
            for key, st in list(searches.items()):
                q, j = key
                lo, hi = st
                if bpar[q][j] == 0:
                    del searches[key]
                    continue
                if (e[perms[q][lo:hi]].sum() & 1) == 0:
                    continue  # stale; restarted next round
                if hi - lo == 1:
                    bit = int(perms[q][lo])
                else:
                    mid = (lo + hi) // 2
                    leak += 1
                    if e[perms[q][lo:mid]].sum() & 1:
                        hi = mid
                    else:
                        lo = mid
                    st[0], st[1] = lo, hi
                    if hi - lo > 1:
                        continue
                    bit = int(perms[q][lo])
                # correct the located bit and update all block parities
                e[bit] ^= 1
                for r_ in range(p + 1):
                    bpar[r_][inv[r_][bit] // sizes[r_]] ^= 1
                del searches[key]
    return e, leak, rounds


# ---------------------------------------------------------------------------
# LUCID front-end (1-D and 2-D tiles) with optional Cascade fallback
# ---------------------------------------------------------------------------

def _suspect_mask(cur, conv, R, C):
    """Bits Bob can locate as possibly wrong: whole flagged blocks (1-D) or the
    union of non-zero rows and columns of every unconverged tile (2-D)."""
    N = cur.size
    nt = N // (R * C)
    T3 = cur.reshape(nt, R, C)
    mask = np.zeros((nt, R, C), dtype=bool)
    for b in np.nonzero(~conv)[0]:
        if R == 1:
            mask[b] = True
        else:
            rn, cn = nonzero_lines(T3[b])
            mask[b, rn, :] = True
            mask[b, :, cn] = True
    return mask.reshape(N)


def _selective_fallback(cur, conv, Q, R, C, iters, stall_rounds, rng, b2):
    """Fallback for tiles Bob saw fail.

    Step 1 (one round trip): Bob names the failed tiles; Alice sends SECDED
    syndromes of length-b2 blocks over the suspect bits, taken in a public
    pseudo-random order.  Bob corrects, then re-runs the tile decoder.
    Step 2 (only if tiles still fail): Cascade on the remaining suspect bits.
    Returns (cur, leak, rounds, tags).
    """
    N = cur.size
    nt = N // (R * C)
    cur = cur.copy()
    leak = rounds = tags = 0
    if b2:
        idx = np.nonzero(_suspect_mask(cur, conv, R, C))[0]
        idx = idx[rng.permutation(idx.size)]
        nb = -(-idx.size // b2)
        pad = np.zeros(nb * b2, dtype=cur.dtype)
        pad[:idx.size] = cur[idx]
        B = pad.reshape(nb, b2)
        secded_correct(B)
        cur[idx] = B.reshape(-1)[:idx.size]
        leak += nb * secded_leak(b2)
        rounds += 1
        T = cur.reshape(nt, R, C)
        conv, _ = decode_tiles(T, iters, stall_rounds)
        cur = T.reshape(N)
        if conv.all():
            return cur, leak, rounds, tags
    flat = _suspect_mask(cur, conv, R, C)
    sub, l2, r2 = cascade(cur[flat], Q, rng)
    cur[flat] = sub
    return cur, leak + l2, rounds + r2, tags + 1


def lucid_frame(e: np.ndarray, Q: float, R: int, C: int, rng: np.random.Generator,
                iters: int = 8, fallback: str = "selective", stall_rounds: int = 2,
                second_block: int = 16):
    """Process one frame with LUCID tiles of R x C bits.

    fallback: 'none'      - lookup only;
              'frame'     - original design: any failure -> Cascade on frame;
              'selective' - local stall resolution, then (one round trip) a
                            second syndrome message over the suspect bits of
                            the tiles Bob saw fail, then Cascade on what is
                            left; if the frame tag still fails, Cascade on the
                            whole frame.
    Returns dict(success, leak_ec, tags, rounds, fallback_used, iters_mean).
    The verification tags themselves are accounted by the caller.
    """
    N = e.size
    t = R * C
    assert N % t == 0
    nt = N // t
    T = e.reshape(nt, R, C).copy()
    conv, used = decode_tiles(T, iters, stall_rounds)
    leak = nt * tile_leak(R, C)
    rounds = 1
    tags = 1
    cur = T.reshape(N)
    fb = False
    if fallback == "none":
        ok = not cur.any()
        return dict(success=ok, leak_ec=leak, tags=tags, rounds=rounds, fallback_used=False,
                    iters_mean=float(used.mean()))
    # Verification accounting: one tag travels with the syndromes; every
    # Cascade invocation is followed by a fresh tag.
    bad_seen = not conv.all()
    if fallback == "frame":
        if bad_seen or cur.any():
            fb = True
            cur, l2, r2 = cascade(cur, Q, rng)
            leak += l2
            rounds += r2
            tags += 1
    else:  # selective
        if bad_seen:
            fb = True
            cur, l2, r2, t2 = _selective_fallback(cur, conv, Q, R, C, iters, stall_rounds, rng, second_block)
            leak += l2
            rounds += r2
            tags += t2
        if cur.any():  # frame tag fails -> whole-frame Cascade
            fb = True
            cur, l2, r2 = cascade(cur, Q, rng)
            leak += l2
            rounds += r2
            tags += 1
    return dict(success=not cur.any(), leak_ec=leak, tags=tags, rounds=rounds, fallback_used=fb,
                iters_mean=float(used.mean()))


# ---------------------------------------------------------------------------
# LDPC (syndrome mode, sum-product BP)
# ---------------------------------------------------------------------------

class LDPC:
    """Random LDPC code, variable degree 3, distinct checks per column,
    check degrees as equal as possible (no other optimisation)."""

    def __init__(self, N: int, m: int, rng: np.random.Generator, dv: int = 3):
        self.N, self.m = N, m
        E = N * dv
        sockets = np.arange(E) % m
        rng.shuffle(sockets)
        cols = sockets.reshape(N, dv)
        # repair repeated checks inside a column by swapping sockets
        for _ in range(200):
            s = np.sort(cols, axis=1)
            dup = np.nonzero((s[:, 1:] == s[:, :-1]).any(axis=1))[0]
            if dup.size == 0:
                break
            for v in dup:
                w = rng.integers(N)
                i, j = rng.integers(dv), rng.integers(dv)
                cols[v, i], cols[w, j] = cols[w, j], cols[v, i]
        var = np.repeat(np.arange(N), dv)
        chk = cols.reshape(-1)
        order = np.argsort(chk, kind="stable")
        self.var = var[order]
        self.chk = chk[order]
        self.starts = np.r_[0, np.nonzero(np.diff(self.chk))[0] + 1]
        self.deg = np.diff(np.r_[self.starts, self.chk.size])

    def syndrome(self, x: np.ndarray) -> np.ndarray:
        return (np.add.reduceat(x[self.var].astype(np.int64), self.starts) & 1)

    def decode(self, s: np.ndarray, Q: float, max_iter: int = 100):
        """Decode the error pattern with syndrome s.  Returns (x_hat, iterations)."""
        L0 = math.log((1 - Q) / Q)
        msg = np.full(self.var.size, L0)
        sflip = s[np.repeat(np.arange(self.starts.size), self.deg)]
        x = np.zeros(self.N, dtype=np.uint8)
        for it in range(1, max_iter + 1):
            a = np.clip(np.abs(msg), 1e-12, 60.0)
            ph = -np.log(np.tanh(a / 2.0))
            S = np.add.reduceat(ph, self.starts)
            sg = (msg < 0).astype(np.int64)
            P = (np.add.reduceat(sg, self.starts) & 1)
            Se = np.repeat(S, self.deg) - ph
            Pe = (np.repeat(P, self.deg) + sg + sflip) & 1
            mag = -np.log(np.tanh(np.clip(Se, 1e-12, 60.0) / 2.0))
            c2v = np.where(Pe == 1, -mag, mag)
            Lv = L0 + np.bincount(self.var, weights=c2v, minlength=self.N)
            x = (Lv < 0).astype(np.uint8)
            if np.array_equal(self.syndrome(x), s):
                return x, it
            msg = Lv[self.var] - c2v
        return x, max_iter


def ldpc_frame(e: np.ndarray, Q: float, code: LDPC, max_iter: int = 100):
    s = code.syndrome(e)
    x, it = code.decode(s, Q, max_iter)
    return dict(success=bool(np.array_equal(x, e)), leak_ec=code.m, tags=1, rounds=1,
                fallback_used=False, iters_mean=float(it))


# ---------------------------------------------------------------------------
# BB84 photon-level frame generator (used to validate the QBER model)
# ---------------------------------------------------------------------------

def bb84_qber(n_qubits: int, e: float, p: float, rng: np.random.Generator) -> float:
    """Simulate BB84 with intercept-resend on a fraction p and channel flips e."""
    a = rng.integers(0, 2, n_qubits)
    ab = rng.integers(0, 2, n_qubits)
    bb = rng.integers(0, 2, n_qubits)
    eve = rng.random(n_qubits) < p
    eb = rng.integers(0, 2, n_qubits)
    # state reaching Bob: (bit, basis)
    eve_bit = np.where(eb == ab, a, rng.integers(0, 2, n_qubits))
    sbit = np.where(eve, eve_bit, a)
    sbas = np.where(eve, eb, ab)
    bob = np.where(bb == sbas, sbit, rng.integers(0, 2, n_qubits))
    bob ^= (rng.random(n_qubits) < e).astype(bob.dtype)
    keep = ab == bb
    return float(np.mean(a[keep] != bob[keep]))


# ---------------------------------------------------------------------------
# Finite-key length (simplified Serfling-type bound, assumption A5)
# ---------------------------------------------------------------------------

def serfling_mu(n: int, k: int, eps: float) -> float:
    return math.sqrt((n + k) * (k + 1) * math.log(1.0 / eps) / (2.0 * n * k * k))


def finite_key_length(n: int, k: int, Q: float, leak_ec: float, leak_ver: float,
                      eps_pe: float = 1e-10, eps_pa: float = 1e-10) -> float:
    e_ph = min(0.5, Q + serfling_mu(n, k, eps_pe))
    ell = n * (1.0 - h2(e_ph)) - leak_ec - leak_ver - 2.0 * math.log2(1.0 / eps_pa)
    return max(0.0, ell)
