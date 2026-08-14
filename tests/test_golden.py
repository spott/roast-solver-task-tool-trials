import json
from pathlib import Path
import numpy as np
from roast_solver.properties import heat_capacity, conductivity, density, linearized_radiation


def test_language_neutral_property_goldens():
    fixture=json.loads(Path("fixtures/golden_properties.json").read_text())
    for row in fixture["values"]:
        t=row["temp_c"]
        assert np.isclose(heat_capacity(t),row["cp"],rtol=2e-7)
        assert np.isclose(conductivity(t),row["k"],rtol=2e-7)
        assert np.isclose(density(t),row["rho"],rtol=2e-7)


def test_language_neutral_embedded_robin_golden():
    fixture=json.loads(Path("fixtures/golden_robin.json").read_text())
    x=fixture["input"]; expected=fixture["expected"]
    hr=float(linearized_radiation(x["emissivity"],x["wall_c"],x["previous_surface_c"]))
    kk=float(conductivity(x["cell_c"]))
    q=(x["h_conv"]*x["air_c"]+hr*x["wall_c"]-(x["h_conv"]+hr)*x["cell_c"])/(1+(x["h_conv"]+hr)*.5*x["dx_m"]/kk)
    surface=x["cell_c"]+q*.5*x["dx_m"]/kk
    assert np.isclose(hr,expected["h_rad_w_m2k"],rtol=2e-12)
    assert np.isclose(q,expected["q_in_w_m2"],rtol=2e-12)
    assert np.isclose(surface,expected["surface_c"],rtol=2e-12)
