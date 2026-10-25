"""Run all four plant models and print results + plain-English summaries.

    python -m plantlab.optimize [--plant path/to/plant.yaml]
"""

import argparse

from plantlab.optimize import line_balancing, parts_transport, production_mix, workforce
from plantlab.plant import load_plant


def section(n, title, result):
    bar = "=" * 78
    return f"{bar}\n{n}. {title}  [{result.status}]\n{bar}\n{result.report()}\n"


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m plantlab.optimize",
                                     description="Plan the fictional car plant with CPLEX.")
    parser.add_argument("--plant", help="plant description (default: the built-in plant.yaml)")
    args = parser.parse_args(argv)

    plant = load_plant(args.plant)
    mix = production_mix.solve_plant(plant)
    print(f"{plant['plant']['name']}: weekly plan with IBM CPLEX (docplex)\n")
    print(section(1, "Production mix (LP)", mix))
    if not mix.plan:
        return 1
    # the weekly plan drives the takt, the staffing need and Plant West's seat demand
    print(section(2, "Line balancing (IP, SALBP-1)", line_balancing.solve_plant(plant, mix.plan)))
    print(section(3, "Workforce per shift (IP)", workforce.solve_plant(plant, mix.plan)))
    print(section(4, "Parts transportation (LP)", parts_transport.solve_plant(plant, mix.plan)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
