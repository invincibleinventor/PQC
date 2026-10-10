"""Zero-leakage QBER estimate from the fraction of SECDED blocks with a non-zero syndrome difference,
versus the paper's 64-bit public sample."""
import numpy as np
rng=np.random.default_rng(3)
# syndrome-based QBER estimate from one 256x256 frame (rows+cols = 512 blocks of 256) vs 64-bit public sample
for Q in [0.001,0.002,0.005,0.01]:
    ests=[];samp=[]
    for _ in range(400):
        E=rng.random((256,256))<Q
        nz=np.concatenate([E.any(1),E.any(0)]).mean()   # nonzero error <=> (almost surely) nonzero syndrome diff
        ests.append(1-(1-nz)**(1/256))
        samp.append((rng.random(64)<Q).mean())
    ests=np.array(ests);samp=np.array(samp)
    print(f"Q={Q:.3f} syndrome-est mean={ests.mean():.4f} rel.sd={ests.std()/Q*100:.0f}% | 64-bit sample: rel.sd={samp.std()/Q*100:.0f}%  P(sample sees 0 errors)={np.mean(samp==0):.2f}")
