"""Analytic and numerical validation helpers.

The sphere oracle follows the exact constant-property convective sphere series,
with eigenvalues ``1 - lambda*cot(lambda) = Bi``.  These fixtures validate the
embedded boundary independently of synthetic cooking scenarios.
"""
from __future__ import annotations
import math
import numpy as np
from .geometry import GridGeometry


def sphere_eigenvalues(bi: float, count=40):
    if bi <= 0: raise ValueError("Bi must be positive")
    def f(x): return 1.0-x/math.tan(x)-bi
    roots=[]
    # Scan avoids special-case root intervals above/below Bi=1.
    x0=1e-7; f0=f(x0)
    step=math.pi/600
    x=x0+step
    while len(roots)<count and x<(count+2)*math.pi:
        # Skip tan singularities and locate genuine sign changes.
        try: fx=f(x)
        except (ValueError,ZeroDivisionError): fx=float("nan")
        if math.isfinite(fx) and math.isfinite(f0) and fx*f0<0 and abs(fx-f0)<100:
            a,b=x-step,x
            for _ in range(60):
                m=(a+b)/2; fm=f(m)
                if f(a)*fm<=0:b=m
                else:a=m
            root=(a+b)/2
            if not roots or root-roots[-1]>1e-4: roots.append(root)
        x0=x; f0=fx; x+=step
    return np.asarray(roots[:count])


def sphere_center_ratio(fourier_number, bi, terms=40):
    """Exact (Tcenter-Tinf)/(Ti-Tinf) for a sphere."""
    lam=sphere_eigenvalues(bi,terms)
    coeff=4*(np.sin(lam)-lam*np.cos(lam))/(2*lam-np.sin(2*lam))
    fo=np.asarray(fourier_number)[...,None]
    return np.sum(coeff*np.exp(-lam*lam*fo),axis=-1)


def make_sphere_geometry(radius=.03,n=48):
    extent=radius*1.18; axis=np.linspace(-extent,extent,n); dx=axis[1]-axis[0]
    x,y,z=np.meshgrid(axis,axis,axis,indexing="ij")
    phi=np.sqrt(x*x+y*y+z*z)-radius; inside=phi<=0
    rr=np.sqrt(x*x+y*y+z*z)+1e-30
    normals=np.stack((x/rr,y/rr,z/rr),axis=-1).astype(np.float32)
    area=np.zeros(phi.shape)
    for ax in range(3):
        lo=[slice(None)]*3; hi=[slice(None)]*3
        lo[ax]=slice(0,-1); hi[ax]=slice(1,None); lo=tuple(lo); hi=tuple(hi)
        cross=inside[lo]!=inside[hi]
        for idx,mine in ((lo,inside[lo]),(hi,inside[hi])):
            l1=np.maximum(np.abs(normals[idx]).sum(axis=-1),.35)
            area[idx]+=(mine&cross)*dx*dx/l1
    boundary=inside&(area>0)
    pan=np.zeros_like(inside)
    return GridGeometry(phi.astype(np.float32),inside,normals,area.astype(np.float32),
                        (area/dx**2).astype(np.float32),pan,float(dx),(-extent,)*3)


def diffuse_dirichlet_box(n=24, final_s=.01, alpha=1.0):
    """M2 regression problem on unit cube; exact mode is sin(pi*x)sin(pi*y)sin(pi*z)."""
    dx=1/(n-1); a=np.linspace(0,1,n); x,y,z=np.meshgrid(a,a,a,indexing="ij")
    u=np.sin(np.pi*x)*np.sin(np.pi*y)*np.sin(np.pi*z)
    dt=.8*dx*dx/(6*alpha); steps=math.ceil(final_s/dt); dt=final_s/steps
    for _ in range(steps):
        v=u.copy()
        v[1:-1,1:-1,1:-1]=u[1:-1,1:-1,1:-1]+alpha*dt/dx**2*(
            u[2:,1:-1,1:-1]+u[:-2,1:-1,1:-1]+u[1:-1,2:,1:-1]+u[1:-1,:-2,1:-1]+
            u[1:-1,1:-1,2:]+u[1:-1,1:-1,:-2]-6*u[1:-1,1:-1,1:-1])
        u=v
    exact=np.sin(np.pi*x)*np.sin(np.pi*y)*np.sin(np.pi*z)*np.exp(-3*np.pi**2*alpha*final_s)
    return float(np.sqrt(np.mean((u-exact)**2)))
