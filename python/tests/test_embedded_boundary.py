import numpy as np
from roast_solver.geometry import Grid,voxelize,sphere_sdf
from roast_solver.solver import RoastSolver,BoundaryConfig,SolverConfig
from roast_solver.analytics import robin_sphere_center_ratio

def _constant(v): return lambda t: np.zeros_like(t,dtype=float)+v

def test_embedded_robin_sphere_center_and_energy_budget():
    radius=.03;n=26;h=2.4*radius/n
    geom=voxelize(sphere_sdf(radius),Grid.centered((n,n,n),h),samples=3)
    rho,cp,k=1060.,3500.,.48; alpha=k/(rho*cp);bi=2.;hconv=bi*k/radius
    bc=BoundaryConfig(oven_c=100,wall_c=100,h_conv=hconv,emissivity=0,initial_moisture_kg_m2=0,pan_insulated=False)
    solver=RoastSolver(geom,bc,SolverConfig(initial_c=0,max_dt_s=2),(_constant(rho),_constant(cp),_constant(k)))
    fo=.10; duration=fo*radius**2/alpha
    solver.run(duration,record_every_s=duration)
    numeric=(100-solver.sample().center_c)/100
    exact=robin_sphere_center_ratio(bi,fo)
    # The 26-cell production-like diameter is comfortably below the plan's 1% target.
    assert abs(numeric-exact)<.01
    assert abs(solver.ledger.residual_j)<2e-9*max(1,abs(solver.ledger.net_surface_j))

def test_resolution_convergence_sphere():
    radius=.03;rho,cp,k=1060.,3500.,.48;alpha=k/(rho*cp);bi=1.;duration=.08*radius**2/alpha
    exact=robin_sphere_center_ratio(bi,.08); errors=[]
    for n in (14,20,28):
        geom=voxelize(sphere_sdf(radius),Grid.centered((n,)*3,2.4*radius/n),samples=2)
        s=RoastSolver(geom,BoundaryConfig(oven_c=100,h_conv=bi*k/radius,emissivity=0,initial_moisture_kg_m2=0,pan_insulated=False),SolverConfig(initial_c=0,max_dt_s=3),(_constant(rho),_constant(cp),_constant(k)))
        s.run(duration,record_every_s=duration)
        errors.append(abs((100-s.sample().center_c)/100-exact))
    assert errors[-1] < errors[0]
    assert errors[-1] < .06
