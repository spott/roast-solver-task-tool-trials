"""Output helpers and conservative pasteurization reporting."""
from __future__ import annotations
import numpy as np

def pasteurization_equivalent_seconds(temperatures_c,times_s,t_ref_c=70.0,z_c=7.5):
    """Trapezoidal equivalent time; defaults are illustrative, not safety advice."""
    t=np.asarray(times_s,float); temp=np.asarray(temperatures_c,float)
    if len(t)<2:return 0.0
    rate=10**((temp-t_ref_c)/z_c)
    return float(np.trapezoid(rate,t))

def doneness_bands(field):
    """Map temperatures to 0..4 visual bands (not food-safety categories)."""
    return np.digitize(field,[45,55,63,70]).astype(np.uint8)
