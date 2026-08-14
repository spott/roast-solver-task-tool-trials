from __future__ import annotations
import argparse, json
import numpy as np
from .geometry import make_geometry
from .solver import BoundaryConfig, SimulationConfig, simulate
from .validation import robin_sphere_check


def main(argv=None):
    p=argparse.ArgumentParser(description="3-D roast heat-transfer reference solver")
    p.add_argument("--preset",choices=["roast","bird","slab","ham"],default="roast")
    p.add_argument("--mass",type=float,default=1.5,help="mass in kg")
    p.add_argument("--resolution",type=int,default=32)
    p.add_argument("--oven",type=float,default=180.)
    p.add_argument("--initial",type=float,default=5.)
    p.add_argument("--target",type=float,default=60.)
    p.add_argument("--convection",action="store_true")
    p.add_argument("--covered",action="store_true")
    p.add_argument("--validate",action="store_true")
    args=p.parse_args(argv)
    if args.validate:
        print(json.dumps(robin_sphere_check(args.resolution),indent=2));return
    geom=make_geometry(args.preset,args.mass,resolution=args.resolution)
    result=simulate(geom,BoundaryConfig(args.oven,args.convection,args.covered),
                    SimulationConfig(args.initial,args.target))
    payload={"geometry":{"preset":args.preset,"cells":int(geom.inside.sum()),
                          "volume_m3":geom.volume,"surface_area_m2":geom.surface_area},
             **result.summary()}
    print(json.dumps(payload,indent=2))


if __name__ == "__main__":
    main()
