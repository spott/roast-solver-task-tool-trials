"""Numerical validation helpers (analytic sphere, energy, convergence)."""
from __future__ import annotations
import numpy as np
from .analytic import sphere_center_ratio, slab_center_ratio
from .geometry import Grid, Geometry
from .properties import food_properties
from .solver import BoundaryConfig, step, stable_timestep


def sphere_geometry(radius=.03, resolution=40, padding=3):
    h=2*radius/resolution; n=resolution+2*padding
    grid=Grid((n,n,n),h,(-n*h/2,)*3)
    z,y,x=grid.coordinates(); phi=np.sqrt(x*x+y*y+z*z)-radius; inside=phi<=0
    gz,gy,gx=np.gradient(phi,h); mag=np.sqrt(gx*gx+gy*gy+gz*gz)+1e-15
    normals=np.stack((gx/mag,gy/mag,gz/mag),axis=-1)
    l1=np.abs(normals).sum(axis=-1).clip(.25); area=np.zeros_like(phi)
    for axis in range(3):
        s0=[slice(None)]*3;s1=[slice(None)]*3;s0[axis]=slice(None,-1);s1[axis]=slice(1,None)
        a,b=tuple(s0),tuple(s1); cross=inside[a]!=inside[b]
        aa=area[a]; m=cross&inside[a]; aa[m]+=h*h/l1[a][m];area[a]=aa
        bb=area[b]; m=cross&inside[b]; bb[m]+=h*h/l1[b][m];area[b]=bb
    return Geometry(grid,phi.astype('f4'),inside,normals.astype('f4'),area.astype('f4'),
                    np.zeros_like(inside),"sphere",4/3*np.pi*radius**3)


def slab_geometry(half_thickness=.015, cells_through=16, lateral_cells=4, padding=2):
    """Infinite-slab surrogate: periodic/unmodeled lateral area is insulated."""
    h=2*half_thickness/cells_through; nz=cells_through+2*padding
    grid=Grid((nz,lateral_cells,lateral_cells),h,
              (-lateral_cells*h/2,-lateral_cells*h/2,-nz*h/2))
    z,_,_=grid.coordinates(); phi=np.abs(z)-half_thickness; inside=phi<=0
    normals=np.zeros(phi.shape+(3,),dtype='f4');normals[...,2]=np.where(z>=0,1.,-1.)
    area=np.zeros_like(phi,dtype='f4'); ids=np.where(inside[:,0,0])[0]
    area[ids[0],:,:]=h*h;area[ids[-1],:,:]=h*h
    return Geometry(grid,phi.astype('f4'),inside,normals,area,np.zeros_like(inside),
                    "infinite-slab",2*half_thickness*(lateral_cells*h)**2)


def robin_slab_check(cells_through=16, bi=.5, fourier=.2):
    """Production 3-D kernel against the exact infinite-slab Robin series."""
    half=.015;initial=20.;bath=21.;geom=slab_geometry(half,cells_through)
    _,_,k,alpha=food_properties(initial);hcoef=bi*k/half
    bc=BoundaryConfig(oven_c=bath,h_still=hcoef,h_fan=hcoef,emissivity=0.,
                      moisture_capacity=0.,pan_insulated=False)
    temp=np.full(geom.inside.shape,np.nan,dtype='f4');temp[geom.inside]=initial
    moisture=np.zeros_like(temp);dt=stable_timestep(geom,initial,.65)
    duration=fourier*half**2/alpha;t=0.
    while t<duration:
        d=min(dt,duration-t);temp,_=step(temp,geom,bc,moisture,d);t+=d
    center=(temp.shape[0]//2,temp.shape[1]//2,temp.shape[2]//2)
    numeric=(float(temp[center])-bath)/(initial-bath);exact=slab_center_ratio(fourier,bi)
    return {"numeric_ratio":numeric,"exact_ratio":exact,
            "relative_error":abs(numeric-exact)/exact}


def robin_sphere_check(resolution=40, bi=.5, fourier=.2):
    # A 1 C forcing keeps the temperature-dependent coefficients effectively
    # constant, isolating the embedded Robin discretization from property-model
    # variation while retaining the production step implementation.
    radius=.03; initial=20.; oven=21.
    geom=sphere_geometry(radius,resolution)
    rho,cp,k,alpha=food_properties(initial)
    h=bi*k/radius
    bc=BoundaryConfig(oven_c=oven,h_still=h,h_fan=h,emissivity=0.,moisture_capacity=0.,pan_insulated=False)
    temp=np.full(geom.inside.shape,np.nan,dtype='f4');temp[geom.inside]=initial
    moisture=np.zeros_like(temp); dt=stable_timestep(geom,temp[geom.inside],.65)
    duration=fourier*radius**2/alpha;t=0
    energy_in=energy_change=0.
    while t<duration:
        d=min(dt,duration-t);temp,e=step(temp,geom,bc,moisture,d);t+=d
        energy_in+=e['boundary_j'];energy_change+=e['sensible_j']
    center=tuple(s//2 for s in temp.shape)
    numeric=(float(temp[center])-oven)/(initial-oven)
    exact=sphere_center_ratio(fourier,bi)
    return {"numeric_ratio":numeric,"exact_ratio":exact,
            "relative_error":abs(numeric-exact)/exact,
            "energy_residual_fraction":abs(energy_in-energy_change)/abs(energy_in),
            "area_relative_error":abs(geom.surface_area-4*np.pi*radius**2)/(4*np.pi*radius**2)}
