export interface SolverInput {
  preset: 'roast' | 'bird' | 'slab' | 'ham';
  mass_kg: number;
  resolution: number;
  material_density: number;
  initial_c: number;
  target_c: number;
  oven_c: number;
  convection_h: number;
  emissivity: number;
  wall_c: number | null;
  covered: boolean;
  ambient_vapor_density: number;
  lewis_number: number;
  surface_water_kg_m2: number;
  pan_insulated: boolean;
  max_cook_s: number;
  rest_s: number;
  sample_interval_s: number;
  requested_dt_s: number;
  rest_ambient_c: number;
  rest_h: number;
  foil_tent: boolean;
  pasteurization_ref_c: number;
  pasteurization_z_c: number;
  denaturation_bump: boolean;
}

export interface RecordPoint {
  time_s: number;
  coldest_c: number;
  probe_c: number;
  surface_mean_c: number;
  pasteurization_equivalent_min: number;
  phase: 'cook' | 'rest';
}

export interface Energy {
  convection_j: number;
  radiation_j: number;
  evaporation_j: number;
  net_surface_j: number;
  enthalpy_change_j: number;
  relative_balance_error: number;
}

export interface SolverChunk {
  records: RecordPoint[];
  done: boolean;
  phase: 'cook' | 'rest' | 'done';
  progress: number;
  dimensions_zyx: [number, number, number];
  temperatures_c: number[];
  inside: boolean[];
  wet_fraction: number[];
  pull_time_s: number | null;
  pull_reached: boolean;
  peak_core_c: number;
  peak_time_s: number;
  carryover_c: number;
  dt_s: number;
  energy: Energy;
}

export type WorkerRequest =
  | { type: 'start'; runId: number; input: SolverInput }
  | { type: 'cancel'; runId: number };

export type WorkerResponse =
  | { type: 'ready' }
  | { type: 'chunk'; runId: number; chunk: SolverChunk }
  | { type: 'error'; runId: number; message: string };
