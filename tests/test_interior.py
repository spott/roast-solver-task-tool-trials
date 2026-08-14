import numpy as np
import pytest
from roast_solver.solver import dirichlet_box_step


def _mode_error(n):
    length=1.; h=length/(n-1); alpha=.01; dt=.12*h*h/(6*alpha)
    x=np.linspace(0,length,n); z,y,x3=np.meshgrid(x,x,x,indexing='ij')
    t=np.sin(np.pi*x3)*np.sin(np.pi*y)*np.sin(np.pi*z)
    duration=.04; steps=round(duration/dt);dt=duration/steps
    for _ in range(steps): t=dirichlet_box_step(t,alpha,h,dt)
    exact=np.exp(-3*np.pi*np.pi*alpha*duration)*np.sin(np.pi*x3)*np.sin(np.pi*y)*np.sin(np.pi*z)
    return np.sqrt(np.mean((t-exact)**2))


def test_dirichlet_box_converges_second_order():
    coarse=_mode_error(11); fine=_mode_error(21)
    assert fine < coarse/3.2


def test_dirichlet_stability_guard():
    with pytest.raises(ValueError):
        dirichlet_box_step(np.zeros((4,4,4)),1.,1.,.17)
