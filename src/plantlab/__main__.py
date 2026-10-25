"""Command line for the whole lab.

    python -m plantlab plan        the four CPLEX models (same as python -m plantlab.optimize)
    python -m plantlab fit         input analysis: fitted time distributions + KS test
    python -m plantlab simulate    simulate the LP's weekly plan: KPIs with 95% CIs, bottleneck
    python -m plantlab loop        paper vs reality for the base plan and 3 what-if scenarios

Options for fit / simulate / loop: --plant PATH, --reps N, --seed S.
After `uv pip install -e .` the same commands run as `plantlab plan`, `plantlab loop`, ...
"""

import argparse

from plantlab import loop
from plantlab.optimize import __main__ as optimize_cli
from plantlab.optimize import production_mix
from plantlab.plant import load_plant
from plantlab.simulate.experiment import run_experiment
from plantlab.simulate.fitting import fit_plant

BAR = "=" * 78


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m plantlab",
                                     description="Plan the fictional car plant with CPLEX, "
                                                 "then stress-test the plan with SimPy.")
    parser.add_argument("command", choices=["plan", "fit", "simulate", "loop"])
    parser.add_argument("--plant", help="plant description (default: the built-in plant.yaml)")
    parser.add_argument("--reps", type=int, help="replications (default: plant.yaml)")
    parser.add_argument("--seed", type=int, help="random seed (default: plant.yaml)")
    args = parser.parse_args(argv)

    if args.command == "plan":
        return optimize_cli.main(["--plant", args.plant] if args.plant else [])

    plant = load_plant(args.plant)
    name = plant["plant"]["name"]
    if args.command == "fit":
        print(f"{BAR}\n{name}: input analysis (scipy.stats, KS test)\n{BAR}")
        print(fit_plant(plant, args.seed).report())
        return 0

    sim_kwargs = {"reps": args.reps, "seed": args.seed}
    if args.command == "simulate":
        mix = production_mix.solve_plant(plant)
        if not mix.plan:
            print(mix.summary)
            return 1
        plan = " + ".join(f"{x:,.0f} {plant['products'][p]['name']}s" for p, x in mix.plan.items())
        print(f"{BAR}\n{name}: simulating the LP's weekly plan ({plan}) with SimPy\n{BAR}")
        print(run_experiment(plant, mix.plan, fits=fit_plant(plant, args.seed), **sim_kwargs).report())
        return 0

    print(f"{BAR}\n{name}: paper (CPLEX plan) vs reality (SimPy), base plan + what-ifs\n{BAR}\n")
    print(loop.run_loop(plant, **sim_kwargs).report())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
