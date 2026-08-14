use roast_solver_core::golden_box_centres;

#[test]
fn numpy_golden_dirichlet_kernel_matches() {
    let csv = include_str!("../../fixtures/web_kernel_golden.csv");
    let rows: Vec<(usize,f32)> = csv.lines().filter(|l| !l.starts_with('#') && !l.starts_with("step") && !l.is_empty())
        .map(|l| {let mut p=l.split(',');(p.next().unwrap().parse().unwrap(),p.next().unwrap().parse().unwrap())}).collect();
    let steps:Vec<usize>=rows.iter().map(|r|r.0).collect();
    let got=golden_box_centres(9,&steps);
    for ((_,want),actual) in rows.iter().zip(got) {assert!((actual-want).abs()<2e-6,"{actual} != {want}");}
}

#[test]
fn core_heats_and_tracks_lethality() {
    let mut core=roast_solver_core::Core::new(24,0,1.0,20.0,180.0,true,false,0.1);
    let before=core.coldest();
    for _ in 0..40 {core.step(5.0);}
    assert!(core.coldest()>=before);
    assert!(core.hottest()>before);
    assert!(core.min_lethality_minutes()>=0.0);
}
