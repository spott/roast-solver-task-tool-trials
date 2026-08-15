use roast_core::{Config, Simulation};

#[test]
fn wasm_core_tracks_numpy_scenario_matrix() {
    let fixture = include_str!("../../fixtures/wasm_golden.csv");
    for line in fixture
        .lines()
        .filter(|line| !line.is_empty() && !line.starts_with('#'))
        .skip(1)
    {
        let c: Vec<&str> = line.split(',').collect();
        let parse = |i: usize| c[i].parse::<f32>().unwrap();
        let mut simulation = Simulation::new(Config {
            preset: c[1].parse().unwrap(),
            mass_kg: parse(2),
            oven_c: parse(3),
            initial_c: parse(4),
            target_c: 200.0,
            convection: c[5] == "1",
            covered: c[6] == "1",
            n: c[7].parse().unwrap(),
            max_cook_s: parse(8),
            rest_s: 0.0,
        });
        while simulation.phase != 2 {
            simulation.step_many(1000);
        }
        let checks = [
            ("coldest", simulation.coldest(), parse(9), 0.20),
            ("probe", simulation.probe_temperature(), parse(10), 0.20),
            ("hottest", simulation.hottest(), parse(11), 0.20),
            (
                "pasteurization",
                simulation.pasteurization_minutes,
                parse(12),
                3e-6,
            ),
            ("evaporation", simulation.evaporated_kg, parse(13), 2e-6),
        ];
        for (quantity, actual, expected, tolerance) in checks {
            assert!(
                (actual - expected).abs() <= tolerance,
                "{} {}: Rust {} vs NumPy {} (tol {})",
                c[0],
                quantity,
                actual,
                expected,
                tolerance
            );
        }
    }
}
