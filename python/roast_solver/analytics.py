"""Analytic regression anchors used by validation tests."""
from __future__ import annotations
import math
import numpy as np

def robin_sphere_eigenvalues(bi: float,count: int=30) -> np.ndarray:
    """Roots of 1-lambda*cot(lambda)=Bi by safeguarded bisection."""
    roots=[]
    def f(x): return 1-x/math.tan(x)-bi
    # One root in intervals separated by n*pi; scan avoids special Bi cases.
    xprev=1e-8; fprev=f(xprev)
    step=math.pi/200
    x=xprev+step
    while len(roots)<count and x<count*math.pi+math.pi:
        if abs(math.sin(x))<1e-5:
            xprev=x+1e-5; fprev=f(xprev); x=xprev+step; continue
        fx=f(x)
        if fx*fprev<0:
            lo,hi=xprev,x
            for _ in range(60):
                mid=.5*(lo+hi); fm=f(mid)
                if fm*f(lo)<=0: hi=mid
                else: lo=mid
            root=.5*(lo+hi)
            # Poles can look like sign changes; retain roots satisfying equation.
            if abs(math.sin(root))>1e-5 and (not roots or root-roots[-1]>1e-3): roots.append(root)
        xprev=x;fprev=fx;x+=step
    return np.asarray(roots)

def robin_sphere_center_ratio(bi: float,fourier: float,terms: int=40) -> float:
    lam=robin_sphere_eigenvalues(bi,terms)
    coeff=4*(np.sin(lam)-lam*np.cos(lam))/(2*lam-np.sin(2*lam))
    return float(np.sum(coeff*np.exp(-lam*lam*fourier)))

def dirichlet_cube_mode_ratio(alpha: float,time_s: float,length: float) -> float:
    return math.exp(-3*math.pi**2*alpha*time_s/length**2)
