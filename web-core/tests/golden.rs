use roast_solver_core::{properties, voxelize, Config, CoreSimulation};
use serde_json::Value;

fn golden() -> Value {
    serde_json::from_str(include_str!("../../fixtures/python_golden.json")).unwrap()
}

#[test]
fn choi_okos_matches_python_oracle() {
    let expected = golden()["properties_20c"]
        .as_array()
        .unwrap()
        .iter()
        .map(|x| x.as_f64().unwrap())
        .collect::<Vec<_>>();
    let actual = properties(20.0);
    for (a, e) in [actual.0, actual.1, actual.2].iter().zip(expected) {
        assert!((a - e).abs() / e.abs() < 2e-8, "{a} vs {e}");
    }
}

#[test]
fn geometry_and_curve_match_python_practically() {
    for scenario in golden()["scenarios"].as_array().unwrap() {
        let c = Config {
            preset: scenario["preset"].as_str().unwrap().into(),
            mass_kg: scenario["mass_kg"].as_f64().unwrap(),
            spacing_m: scenario["spacing_m"].as_f64().unwrap(),
            initial_c: scenario["initial_c"].as_f64().unwrap(),
            oven_c: scenario["oven_c"].as_f64().unwrap(),
            covered: scenario["covered"].as_bool().unwrap(),
            sample_interval_s: 300.,
            ..Config::default()
        };
        let grid = voxelize(&c);
        let shape = scenario["grid_shape"]
            .as_array()
            .unwrap()
            .iter()
            .map(|v| v.as_u64().unwrap() as usize)
            .collect::<Vec<_>>();
        assert_eq!(grid.dims, shape.as_slice());
        let ev = scenario["voxel_volume_m3"].as_f64().unwrap();
        let ea = scenario["surface_area_m2"].as_f64().unwrap();
        assert!((grid.volume() - ev).abs() < 1e-9);
        assert!(
            (grid.surface_area() - ea).abs() / ea < 5e-5,
            "area {} vs {}",
            grid.surface_area(),
            ea
        );
        let mut sim = CoreSimulation::new(c).unwrap();
        sim.run_for_test(1800.);
        let expected = scenario["curve"]
            .as_array()
            .unwrap()
            .last()
            .unwrap()
            .as_array()
            .unwrap();
        let actual = sim.samples.last().unwrap();
        for (a, i) in [
            (actual.coldest_c, 1),
            (actual.probe_c, 2),
            (actual.hottest_c, 3),
        ] {
            let e = expected[i].as_f64().unwrap() as f32;
            assert!(
                (a - e).abs() < 0.08,
                "{} temperature {} vs {}",
                scenario["preset"],
                a,
                e
            );
        }
    }
}

#[test]
fn progressive_state_finishes_roast_and_rest() {
    let c = Config {
        mass_kg: 0.3,
        spacing_m: 0.012,
        target_c: 8.,
        max_roast_s: 1800.,
        rest_s: 120.,
        ..Config::default()
    };
    let mut sim = CoreSimulation::new(c).unwrap();
    for _ in 0..100 {
        sim.advance_steps(8);
        if sim.snapshot().done {
            break;
        }
    }
    let out = sim.snapshot();
    assert!(out.done);
    assert!(out.pull_time_s.is_some());
    assert!(out.energy_relative_error < 1e-10);
}
