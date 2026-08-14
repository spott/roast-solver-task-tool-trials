import json
from pathlib import Path
import numpy as np
from roast_solver.solver import SolverConfig, simulate


def test_forward_model_fixture_is_explicitly_synthetic_and_regression_locked():
    fixture=json.loads(Path("fixtures/synthetic_roast_calibration.json").read_text())
    assert fixture["kind"] == "SYNTHETIC_FORWARD_MODEL_NOT_PROBE_DATA"
    case=fixture["scenarios"][0]
    result=simulate(SolverConfig(**case["config"]))
    assert np.allclose(result.times_s, case["observations"]["time_s"], atol=.01)
    assert np.allclose(result.coldest_c, case["observations"]["coldest_c"], atol=2e-4)
    assert np.allclose(result.probe_c, case["observations"]["deep_probe_c"], atol=2e-4)
