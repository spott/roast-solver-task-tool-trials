import numpy as np
from roast_solver.properties import food_properties, radiation_coefficient, vapor_mass_fraction


def test_lean_meat_properties_are_physical_and_temperature_dependent():
    rho, cp, k, alpha = food_properties(np.array([5., 60., 100.]))
    assert np.all((rho > 1000) & (rho < 1080))
    assert np.all((cp > 3300) & (cp < 3800))
    assert np.all((k > .45) & (k < .65))
    assert np.all((alpha > 1.2e-7) & (alpha < 1.8e-7))
    assert alpha[-1] > alpha[0]


def test_radiation_and_humidity_helpers():
    assert 10 < radiation_coefficient(60, 180, .9) < 20
    assert vapor_mass_fraction(60.) > vapor_mass_fraction(20.)
