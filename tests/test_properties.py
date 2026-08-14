import numpy as np
from roast_solver.properties import meat_properties, thermal_diffusivity


def test_property_ranges_and_temperature_dependence():
    rho, cp, k = meat_properties(np.array([0, 20, 60, 100], dtype=float))
    assert np.all((rho > 1000) & (rho < 1150))
    assert np.all((cp > 3000) & (cp < 4000))
    assert np.all((k > .4) & (k < .65))
    assert np.all((thermal_diffusivity(np.array([20,60])) > 1e-7) &
                  (thermal_diffusivity(np.array([20,60])) < 1.7e-7))
