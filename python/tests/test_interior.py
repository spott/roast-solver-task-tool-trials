import numpy as np
from roast_solver.solver import solve_dirichlet_cube
from roast_solver.analytics import dirichlet_cube_mode_ratio

def _mode(n):
    x=np.linspace(0,1,n);X,Y,Z=np.meshgrid(x,x,x,indexing="ij")
    return np.sin(np.pi*X)*np.sin(np.pi*Y)*np.sin(np.pi*Z)

def test_dirichlet_eigenmode_matches_decay():
    n=19;h=1/(n-1);alpha=.01;dt=.12*h*h/alpha;steps=40
    u0=_mode(n);u=solve_dirichlet_cube(u0,alpha,h,dt,steps)
    exact=dirichlet_cube_mode_ratio(alpha,dt*steps,1.0)
    assert abs(u[n//2,n//2,n//2]-exact)<.008

def test_dirichlet_second_order_spatial_convergence():
    errors=[]
    for n in (11,21,41):
        h=1/(n-1);alpha=.01;steps=500;dt=.05/steps
        u=solve_dirichlet_cube(_mode(n),alpha,h,dt,steps)
        exact=dirichlet_cube_mode_ratio(alpha,.05,1)
        errors.append(abs(u[n//2,n//2,n//2]-exact))
    assert errors[2]<errors[1]<errors[0]
    assert errors[0]/errors[2]>10
