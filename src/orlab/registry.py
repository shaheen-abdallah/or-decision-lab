"""The catalogue: one car plant, nine decisions, grouped like the OR-Tools guides."""

from orlab.core import Problem

FAMILIES = ["Linear optimization", "Network flows", "Assignment", "Integer optimization",
            "Scheduling", "Routing", "Simulation"]

PROBLEMS = [
    Problem("product_mix", "How many Sedans and SUVs should we build this week?",
            "Linear optimization", "Product mix (linear program)", "GLOP",
            "Cars per week are continuous enough to round; a linear program also gives the value "
            "of one more hour at every station (dual values).",
            icon=":material/factory:", live=True, sense="max"),
    Problem("min_cost_flow", "Which supplier ships seat sets to which plant?",
            "Network flows", "Transportation problem (minimum-cost flow)", "SimpleMinCostFlow",
            "Suppliers and plants form a network; the min-cost-flow solver finds the cheapest "
            "shipping plan in integers without a general LP.",
            icon=":material/local_shipping:", live=True),
    Problem("assignment", "Which operator should run which station?",
            "Assignment", "Assignment problem", "LinearSumAssignment",
            "One operator per station, one station per operator: a dedicated assignment solver.",
            icon=":material/assignment_ind:", live=True),
    Problem("line_balancing", "How few stations does the trim line need?",
            "Integer optimization", "Assembly line balancing (SALBP-1, MIP)", "SCIP",
            "Which task goes to which station is a yes/no choice with precedence rules: "
            "a mixed-integer program.",
            icon=":material/conveyor_belt:", live=True, unit="stations"),
    Problem("knapsack", "Which improvement projects fit this year's budget?",
            "Integer optimization", "Knapsack", "KnapsackSolver",
            "Pick projects with the most gain under one budget: the classic knapsack.",
            icon=":material/inventory:", live=True, sense="max", unit="€/week"),
    Problem("shift_scheduling", "Who works which shift next week?",
            "Scheduling", "Employee shift scheduling", "CP-SAT",
            "Coverage, rest and fairness rules are logical constraints on yes/no decisions: "
            "constraint programming handles them directly.",
            icon=":material/groups:"),
    Problem("job_shop", "In what order should batches go through the paint shop?",
            "Scheduling", "Job shop scheduling (makespan)", "CP-SAT",
            "Interval variables and no-overlap constraints are built into CP-SAT.",
            icon=":material/calendar_view_week:"),
    Problem("vehicle_routing", "Which route delivers parts to the dealers?",
            "Routing", "Capacitated vehicle routing", "Routing solver",
            "OR-Tools' routing library handles vehicle capacity and many stops with local search.",
            icon=":material/route:"),
    Problem("simulation", "Does the plan survive real-world variability?",
            "Simulation", "Discrete-event simulation (SimPy)", "SimPy",
            "Random station times, breakdowns and rework are not an optimisation: simulate them.",
            icon=":material/monitoring:"),
]


def problem(key):
    return next(p for p in PROBLEMS if p.key == key)
