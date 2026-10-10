"""Square product-SECDED (LUCID-2D) vs single-block SECDED at equal frame size.
Error-pattern simulation (iid BSC); success = all errors removed. Preliminary: 60-200 frames/point."""
import numpy as np, sys
rng=np.random.default_rng(1)
def h(p): return 0 if p<=0 else -p*np.log2(p)-(1-p)*np.log2(1-p)
def secded_fix(E, m):
    # E: (rows, n) error matrix; decode each row: returns corrected E (residual errors)
    n=1<<m
    idx=np.arange(n)
    # syndrome of error row: positions xor, parity
    w=E.sum(1).astype(np.int64)%2
    pos=np.zeros(E.shape[0],dtype=np.int64)
    for k in range(m):
        pos ^= ((E[:, ((idx>>k)&1).astype(bool)].sum(1).astype(np.int64)%2)<<k)
    single = (w==1)
    E=E.copy()
    r=np.nonzero(single)[0]
    E[r,pos[r]]^=1   # flip -> correct if truly single, mis-correct if odd>=3
    return E
def product(Q,m,iters,frames):
    n=1<<m; ok=0; it_used=[]
    for f in range(frames):
        E=(rng.random((n,n))<Q).astype(np.uint8)
        for i in range(iters):
            if not E.any(): break
            E=secded_fix(E,m)
            E=secded_fix(E.T.copy(),m).T.copy()
        it_used.append(i+1)
        ok+= (not E.any())
    leak=(2*n*(m+1)-(m+1)**2)/n/n
    return ok/frames, leak
def single(Q,m,frames,N):
    n=1<<m; blocks=N//n; ok=0
    for f in range(frames):
        E=(rng.random((blocks,n))<Q).astype(np.uint8)
        ok+= (not secded_fix(E,m).any())
    return ok/frames,(m+1)/n
for Q in [0.001,0.002,0.005,0.01,0.02]:
    print(f"Q={Q} h={h(Q):.4f}")
    for m in [6,7,8]:
        fr=200 if m<8 else 60
        s,l=product(Q,m,8,fr)
        n=1<<m
        s1,l1=single(Q,m,fr,n*n)
        print(f"  n={n:3d} product: succ={s:.2f} leak={l:.4f} f={l/h(Q):.2f} | single-SECDED same frame {n*n}: succ={s1:.2f} leak={l1:.4f}")
