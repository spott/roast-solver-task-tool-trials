use roast_solver_web_core::{make_geometry, properties, Boundary, Core};
use std::collections::HashMap;

fn fixture() -> HashMap<&'static str, f64> {
    include_str!("../../fixtures/rust_golden.tsv")
        .lines()
        .filter(|l| !l.starts_with('#') && !l.starts_with("key") && !l.is_empty())
        .map(|l| {
            let mut p = l.split('\t');
            (p.next().unwrap(), p.next().unwrap().parse().unwrap())
        })
        .collect()
}
fn close(actual: f64, expected: f64, rtol: f64, atol: f64, label: &str) {
    let error = (actual - expected).abs();
    assert!(
        error <= atol + rtol * expected.abs(),
        "{label}: actual={actual:0.17e} expected={expected:0.17e} error={error:0.3e}"
    );
}

#[test]
fn choi_okos_properties_match_numpy() {
    let f = fixture();
    for temp in [0.0, 20.0, 70.0, 120.0] {
        let p = properties(temp);
        let prefix = format!("property.{temp}");
        close(p.rho, f[&*format!("{prefix}.rho")], 2e-13, 1e-12, "rho");
        close(p.cp, f[&*format!("{prefix}.cp")], 2e-13, 1e-12, "cp");
        close(p.k, f[&*format!("{prefix}.k")], 2e-13, 1e-14, "k");
    }
}

#[test]
fn geometry_quadrature_matches_numpy() {
    let f = fixture();
    let g = make_geometry("roast", 1.5, 10).unwrap();
    close(g.volume(), f["geometry.volume"], 2e-12, 1e-15, "volume");
    close(g.embedded_area(), f["geometry.area"], 2e-12, 1e-15, "area");
    assert_eq!(
        g.active.iter().filter(|&&x| x).count(),
        f["geometry.active"] as usize
    );
    assert_eq!(
        g.pan.iter().filter(|&&x| x).count(),
        f["geometry.pan"] as usize
    );
}

#[test]
fn full_physics_regression_and_energy_accounting() {
    let f = fixture();
    let g = make_geometry("roast", 1.5, 10).unwrap();
    let mut b = Boundary::default();
    b.oven_c = 180.0;
    b.wall_c = 180.0;
    b.h_conv = 10.0;
    b.emissivity = 0.9;
    b.covered = false;
    b.initial_moisture_kg_m2 = 0.25;
    let mut core = Core::new(g, b, 5.0);
    for step in 0..=120 {
        if [0, 30, 120].contains(&step) {
            let s = core.sample();
            let prefix = format!("simulation.{step}");
            close(
                s.coldest_c,
                f[&*format!("{prefix}.coldest")],
                3e-10,
                3e-10,
                "coldest",
            );
            close(
                s.center_c,
                f[&*format!("{prefix}.center")],
                3e-10,
                3e-10,
                "center",
            );
            close(
                s.mean_c,
                f[&*format!("{prefix}.mean")],
                3e-10,
                3e-10,
                "mean",
            );
            close(
                s.pasteurization_s,
                f[&*format!("{prefix}.pasteurization")],
                3e-10,
                1e-16,
                "pasteurization",
            );
            close(
                core.moisture_remaining_kg(),
                f[&*format!("{prefix}.moisture")],
                3e-10,
                1e-14,
                "moisture",
            );
        }
        if step < 120 {
            core.step(1.0, false)
        }
    }
    close(
        core.ledger.convection_j,
        f["ledger.convection"],
        3e-10,
        1e-8,
        "convection",
    );
    close(
        core.ledger.radiation_j,
        f["ledger.radiation"],
        3e-10,
        1e-8,
        "radiation",
    );
    close(
        core.ledger.evaporation_j,
        f["ledger.evaporation"],
        3e-10,
        1e-8,
        "evaporation",
    );
    close(
        core.ledger.net_surface_j,
        f["ledger.net"],
        3e-10,
        1e-8,
        "net",
    );
    close(
        core.ledger.discrete_enthalpy_j,
        f["ledger.enthalpy"],
        3e-10,
        1e-8,
        "enthalpy",
    );
    assert!(core.ledger.residual_j.abs() < 1e-8);
}

#[test]
fn rest_and_all_presets_smoke() {
    for preset in ["roast", "ham", "slab", "bird"] {
        let g = make_geometry(preset, 1.2, 8).unwrap();
        assert!(g.volume() > 0.0);
        let mut c = Core::new(g, Boundary::default(), 50.0);
        c.run_for(2.0, true);
        assert!(c.sample().coldest_c.is_finite());
    }
}
