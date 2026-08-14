from __future__ import annotations
import argparse,json
import numpy as np
from .geometry import make_geometry
from .solver import RoastSolver,BoundaryConfig,SolverConfig

def main():
    p=argparse.ArgumentParser(description="Run the NumPy Roast Solver reference")
    p.add_argument("--preset",choices=["roast","bird","slab","ham"],default="roast")
    p.add_argument("--mass",type=float,default=1.0);p.add_argument("--resolution",type=int,default=24)
    p.add_argument("--oven",type=float,default=180);p.add_argument("--initial",type=float,default=5)
    p.add_argument("--target",type=float,default=55);p.add_argument("--max-hours",type=float,default=6)
    p.add_argument("--rest-minutes",type=float,default=30);p.add_argument("--fan",action="store_true")
    p.add_argument("--covered",action="store_true")
    args=p.parse_args()
    geom=make_geometry(args.preset,args.mass,args.resolution)
    solver=RoastSolver(geom,BoundaryConfig(oven_c=args.oven,h_conv=20 if args.fan else 10,covered=args.covered),SolverConfig(initial_c=args.initial))
    result=solver.run_to_target(args.target,args.max_hours*3600,args.rest_minutes*60)
    def sample(s):return vars(s)
    payload={"preset":args.preset,"voxel_volume_m3":geom.volume,"pull_time_s":result["pull_time_s"],
             "pull":sample(result["pull"]),"peak":sample(result["peak"]),"carryover_c":result["carryover_c"],
             "pasteurization_equivalent_s":result["pasteurization"],"energy_ledger_J":vars(solver.ledger),
             "curve":[sample(s) for s in result["roast"]+result["rest"]],
             "central_slice_C":np.nan_to_num(solver.temperature[:,:,solver.temperature.shape[2]//2],nan=-999).round(3).tolist()}
    print(json.dumps(payload))
if __name__=="__main__":main()
