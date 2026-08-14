import numpy as np
from roast_solver import properties
from roast_solver.geometry import Grid,voxelize,sphere_sdf,preset_sdf,make_geometry

def test_lean_meat_property_ranges_and_trends():
    t=np.array([5.,50.,100.])
    rho=properties.density(t);cp=properties.heat_capacity(t);k=properties.conductivity(t)
    assert np.all((rho>1030)&(rho<1100))
    assert np.all((cp>3300)&(cp<3900))
    assert np.all((k>.43)&(k<.58))
    assert np.allclose(properties.diffusivity(t),k/(rho*cp))
    assert properties.enthalpy(20)>properties.enthalpy(10)

def test_sphere_cut_cell_volume_and_area():
    r=.04; grid=Grid.centered((32,32,32),2.5*r/32)
    g=voxelize(sphere_sdf(r),grid,samples=3)
    exact_v=4*np.pi*r**3/3; exact_a=4*np.pi*r**2
    assert abs(g.volume/exact_v-1)<.025
    assert abs(g.embedded_area/exact_a-1)<.06
    normals=g.normal[g.surface_area>0]
    assert np.allclose(np.linalg.norm(normals,axis=1),1)

def test_all_required_presets_voxelize_and_bird_has_cavity():
    for preset in ("roast","bird","slab"):
        g=make_geometry(preset,1.2,20,samples=2)
        assert g.active.any() and g.volume>0 and g.embedded_area>0
    sdf,_=preset_sdf("bird",1.2)
    # The central torso cavity is outside while body points around it remain inside.
    assert sdf(np.array(-.005),np.array(0.),np.array(0.))>0
