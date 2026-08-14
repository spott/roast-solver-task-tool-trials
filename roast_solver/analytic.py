"""Analytic heat-equation anchors used by the validation suite."""
from __future__ import annotations
import math
import numpy as np


def _bisect(fn, lo, hi, iterations=80):
    flo=fn(lo)
    for _ in range(iterations):
        mid=(lo+hi)/2; fm=fn(mid)
        if flo*fm <= 0: hi=mid
        else: lo=mid; flo=fm
    return (lo+hi)/2


def sphere_eigenvalues(bi, count=40):
    """Roots of 1-lambda*cot(lambda)=Bi for a convective sphere."""
    roots=[]
    fn=lambda x: 1-x/math.tan(x)-bi
    eps=1e-9
    # One root in intervals separated by cotangent poles, but Bi determines
    # which side; scan robustly rather than embedding interval assumptions.
    x_prev=eps; f_prev=fn(x_prev)
    step=math.pi/300
    x=x_prev+step
    while len(roots)<count and x < (count+3)*math.pi:
        if abs(math.sin(x)) < 1e-5:
            x += step; x_prev=x; f_prev=fn(x_prev); continue
        f=fn(x)
        if f*f_prev < 0 and not (math.floor(x/math.pi)!=math.floor(x_prev/math.pi)):
            root=_bisect(fn,x_prev,x)
            if not roots or abs(root-roots[-1])>1e-5: roots.append(root)
        x_prev=x; f_prev=f; x+=step
    return np.asarray(roots[:count])


def sphere_center_ratio(fourier_number, bi, terms=40):
    lam=sphere_eigenvalues(bi, terms)
    coeff=4*(np.sin(lam)-lam*np.cos(lam))/(2*lam-np.sin(2*lam))
    return float(np.sum(coeff*np.exp(-lam*lam*fourier_number)))


def slab_center_ratio(fourier_number, bi, terms=60):
    """Infinite slab center ratio, roots lambda*tan(lambda)=Bi."""
    roots=[]
    fn=lambda x: x*math.tan(x)-bi
    for n in range(terms):
        lo=n*math.pi+1e-9; hi=n*math.pi+math.pi/2-1e-9
        roots.append(_bisect(fn,lo,hi))
    lam=np.asarray(roots)
    coeff=4*np.sin(lam)/(2*lam+np.sin(2*lam))
    return float(np.sum(coeff*np.exp(-lam*lam*fourier_number)))
