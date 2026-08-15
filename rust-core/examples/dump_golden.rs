use roast_core::{Config, Simulation};

fn main() {
    for (name, preset, convection, covered) in [
        ("roast-still-open", 0, false, false),
        ("slab-fan-covered", 2, true, true),
        ("bird-fan-open", 1, true, false),
    ] {
        let mut simulation = Simulation::new(Config {
            preset,
            mass_kg: 0.6,
            oven_c: 170.0,
            initial_c: 10.0,
            target_c: 200.0,
            convection,
            covered,
            n: 21,
            max_cook_s: 1800.0,
            rest_s: 0.0,
        });
        while simulation.phase != 2 {
            simulation.step_many(1000);
        }
        println!(
            "{name},{:.6},{:.6},{:.6},{:.9},{:.9}",
            simulation.coldest(),
            simulation.probe_temperature(),
            simulation.hottest(),
            simulation.pasteurization_minutes,
            simulation.evaporated_kg
        );
    }
}
