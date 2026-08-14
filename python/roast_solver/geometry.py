"""Analytic signed-distance presets and conservative sub-cell voxelization."""
from __future__ import annotations
from dataclasses import dataclass
from math import gamma
from typing import Callable
import numpy as np

Array = np.ndarray

@dataclass(frozen=True)
class Grid:
    shape: tuple[int, int, int]
    spacing: float
    origin: tuple[float, float, float]

    @classmethod
    def centered(cls, shape: tuple[int, int, int], spacing: float) -> "Grid":
        extent = np.asarray(shape)*spacing
        return cls(shape, spacing, tuple(-.5*extent + .5*spacing))

    def centers(self) -> tuple[Array, Array, Array]:
        axes = [self.origin[i] + np.arange(self.shape[i])*self.spacing for i in range(3)]
        return np.meshgrid(*axes, indexing="ij")

@dataclass
class VoxelGeometry:
    grid: Grid
    phi: Array
    volume_fraction: Array
    effective_volume_fraction: Array
    active: Array
    face_fraction: tuple[Array, Array, Array, Array, Array, Array] # -x,+x,-y,+y,-z,+z
    surface_area: Array
    normal: Array
    pan_mask: Array

    @property
    def volume(self) -> float:
        return float(np.sum(self.volume_fraction)*self.grid.spacing**3)

    @property
    def embedded_area(self) -> float:
        return float(np.sum(self.surface_area))

def superellipsoid_sdf(x, y, z, axes, exponent=2.5):
    """Smooth implicit-distance approximation (correct zero set and sign)."""
    a, b, c = axes
    p = float(exponent)
    f = ((np.abs(x/a)**p + np.abs(y/b)**p + np.abs(z/c)**p)**(1.0/p) - 1.0)
    return f*min(axes)

def sphere_sdf(radius: float) -> Callable[[Array,Array,Array],Array]:
    return lambda x,y,z: np.sqrt(x*x+y*y+z*z)-radius

def rounded_box_sdf(x, y, z, half_size, radius):
    q = np.stack((np.abs(x), np.abs(y), np.abs(z)), axis=0) - (np.asarray(half_size)-radius).reshape((3,)+(1,)*np.ndim(x))
    outside = np.sqrt(np.sum(np.maximum(q, 0.0)**2, axis=0))
    inside = np.minimum(np.maximum.reduce(q, axis=0), 0.0)
    return outside + inside - radius

def capsule_sdf(x,y,z,a,b,radius):
    pa = np.stack((x-a[0],y-a[1],z-a[2]), axis=0)
    ba = np.asarray(b)-np.asarray(a)
    h = np.clip(np.sum(pa*ba.reshape((3,)+(1,)*np.ndim(x)),axis=0)/np.dot(ba,ba),0,1)
    d = pa-ba.reshape((3,)+(1,)*np.ndim(x))*h
    return np.sqrt(np.sum(d*d,axis=0))-radius

def smooth_min(a,b,k):
    h=np.clip(.5+.5*(b-a)/k,0,1)
    return b*(1-h)+a*h-k*h*(1-h)

def smooth_max(a,b,k):
    return -smooth_min(-a,-b,k)

def preset_sdf(preset: str, mass_kg: float, rho: float=1060.0) -> tuple[Callable, tuple[float,float,float]]:
    """Return an SDF and conservative half-extents for a mass-scaled preset."""
    volume=mass_kg/rho
    if preset in ("roast","ham"):
        ratios = (1.35, .85, .78) if preset=="roast" else (1.15,.92,.88)
        p=2.5 if preset=="roast" else 2.2
        unit=8*np.prod(ratios)*gamma(1+1/p)**3/gamma(1+3/p)
        s=(volume/unit)**(1/3); axes=tuple(s*r for r in ratios)
        return lambda x,y,z: superellipsoid_sdf(x,y,z,axes,p), tuple(1.08*a for a in axes)
    if preset=="slab":
        ratios=np.asarray((1.7,1.15,.42)); s=(volume/(8*np.prod(ratios)))**(1/3)
        half=ratios*s; radius=.12*min(half)
        return lambda x,y,z: rounded_box_sdf(x,y,z,half,radius), tuple(1.08*half)
    if preset=="bird":
        # A body, paired leg/thigh capsules and wing stubs; subtract an internal cavity.
        ratios=np.asarray((1.05,.78,.82)); # numerical volume correction for appendages/cavity
        s=(volume/(3.55*np.prod(ratios)))**(1/3); a,b,c=ratios*s
        def bird(x,y,z):
            body=superellipsoid_sdf(x,y,z,(a,b,c),2.2)
            d=body
            for sy in (-1,1):
                d=smooth_min(d,capsule_sdf(x,y,z,(.45*a,sy*.55*b,-.15*c),(1.15*a,sy*.85*b,-.55*c),.20*a),.10*a)
                d=smooth_min(d,capsule_sdf(x,y,z,(-.1*a,sy*.72*b,.12*c),(-.55*a,sy*1.25*b,.05*c),.12*a),.08*a)
            cavity=superellipsoid_sdf(x+.18*a,y,z,(.50*a,.42*b,.48*c),2.0)
            return smooth_max(d,-cavity,.05*a)
        return bird,(1.45*a,1.45*b,1.15*c)
    raise ValueError(f"unknown preset {preset!r}")

def _sample_fraction(sdf: Callable, grid: Grid, axis: int|None, side: int=0, samples: int=3) -> Array:
    """Fraction inside at volume samples or at one cell face."""
    x0=grid.centers()
    offsets=(np.arange(samples)+.5)/samples-.5
    count=np.zeros(grid.shape,dtype=np.float64)
    total=0
    if axis is None:
        for ox in offsets:
            for oy in offsets:
                for oz in offsets:
                    count += sdf(x0[0]+ox*grid.spacing,x0[1]+oy*grid.spacing,x0[2]+oz*grid.spacing)<=0
                    total+=1
    else:
        other=[i for i in range(3) if i!=axis]
        for oa in offsets:
            for ob in offsets:
                xyz=[x0[i] for i in range(3)]
                xyz[axis]=xyz[axis]+side*.5*grid.spacing
                xyz[other[0]]=xyz[other[0]]+oa*grid.spacing
                xyz[other[1]]=xyz[other[1]]+ob*grid.spacing
                count += sdf(*xyz)<=0; total+=1
    return count/total

def voxelize(sdf: Callable, grid: Grid, samples: int=3, min_effective_fraction: float=.25) -> VoxelGeometry:
    xyz=grid.centers(); phi=sdf(*xyz)
    vf=_sample_fraction(sdf,grid,None,samples=samples)
    faces=tuple(_sample_fraction(sdf,grid,axis,side,samples) for axis in range(3) for side in (-1,1))
    active=vf>0
    eff=np.where(active,np.maximum(vf,min_effective_fraction),0.0)
    h2=grid.spacing**2
    # Outward embedded area vector follows the cut-cell divergence theorem.
    vec=np.stack(((faces[0]-faces[1])*h2,(faces[2]-faces[3])*h2,(faces[4]-faces[5])*h2),axis=-1)
    area=np.linalg.norm(vec,axis=-1)
    # A face sample can graze material even when all volume samples miss it; such
    # zero-volume fragments are excluded rather than inventing thermal mass.
    area=np.where(active,area,0.0)
    normal=np.zeros_like(vec); np.divide(vec,area[...,None],out=normal,where=area[...,None]>1e-15)
    pan=(area>0)&(normal[...,2]<-.45)
    return VoxelGeometry(grid,phi,vf,eff,active,faces,area,normal,pan)

def make_geometry(preset: str="roast", mass_kg: float=1.5, resolution: int=32, padding: float=.10, samples: int=3) -> VoxelGeometry:
    sdf, ext=preset_sdf(preset,mass_kg)
    side=2*max(ext)*(1+padding); h=side/resolution
    return voxelize(sdf,Grid.centered((resolution,)*3,h),samples=samples)
