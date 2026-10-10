"""Rectangular LUCID-2D shapes: success, leakage, efficiency f, iterations, and secret fraction
r = (1 - h(Q) - leak - 64/N) * success, compared with the LUCID paper Table V (N=512).
Preliminary: 120 frames per configuration."""
import numpy as np
rng=np.random.default_rng(7)
def h(p): return -p*np.log2(p)-(1-p)*np.log2(1-p)
def fix(E,m):
    n=1<<m; idx=np.arange(n)
    w=E.sum(1).astype(np.int64)%2
    pos=np.zeros(E.shape[0],dtype=np.int64)
    for k in range(m):
        pos ^= (E[:, ((idx>>k)&1).astype(bool)].sum(1).astype(np.int64)%2)<<k
    r=np.nonzero(w==1)[0]; E=E.copy(); E[r,pos[r]]^=1; return E
def run(Q,mr,mc,frames,iters=10):
    R,C=1<<mr,1<<mc; ok=0; its=[]
    for _ in range(frames):
        E=(rng.random((R,C))<Q).astype(np.uint8); i=0
        while E.any() and i<iters:
            E=fix(E,mc); E=fix(E.T.copy(),mr).T.copy(); i+=1
        ok+=not E.any(); its.append(i)
    leak=(R*(mc+1)+C*(mr+1)-(mc+1)*(mr+1))/(R*C)
    return ok/frames,leak,np.mean(its),max(its)
paper={0.001:(0.83,0.79,0.77),0.002:(0.82,0.77,0.76),0.005:(0.75,0.68,0.67),0.01:(0.66,0.50,0.55)}
TAG=64
for Q in [0.001,0.002,0.005,0.01]:
    best=None; rows=[]
    for mr in range(5,10):
        for mc in range(mr,11):
            if (1<<mr)*(1<<mc)>2**18: continue
            s,l,mi,ma=run(Q,mr,mc,120)
            N=(1<<mr)*(1<<mc)
            r=(1-h(Q)-l-TAG/N)*s
            rows.append((r,mr,mc,s,l,mi,ma,N))
    rows.sort(reverse=True)
    print(f"\nQ={Q*100:.1f}% h={h(Q):.4f}  paper N=512 (Cascade,LUCID,LDPC)={paper[Q]}  ideal-LDPC f=1.15 long frame r={1-h(Q)-1.15*h(Q):.3f}")
    for r,mr,mc,s,l,mi,ma,N in rows[:4]:
        print(f"  {1<<mr}x{1<<mc} N={N:6d} succ={s:.2f} leak={l:.4f} f={l/h(Q):.2f} iters avg={mi:.1f} max={ma} r={r:.3f}")
