r"""Vehicle routing: which route delivers service parts to the dealers
(capacitated vehicle routing problem, OR-Tools routing solver).

**Decide** $x_{ijv} \in \{0, 1\}$: van $v$ drives from stop $i$ straight to stop $j$.

$$\min \sum_{v} \sum_{i,j} d_{ij}\, x_{ijv} \qquad d_{ij} = \text{km between the stops}$$
$$\sum_{v}\sum_{i} x_{ijv} = 1 \quad \forall j \ne \text{depot} \qquad\text{(every dealer is visited once)}$$
$$\sum_i x_{ikv} = \sum_j x_{kjv} \quad \forall k, v \qquad\text{(a van that arrives also leaves)}$$
$$\sum_{j} q_j \sum_i x_{ijv} \le Q \quad \forall v \qquad\text{(the pallets on a van fit its capacity } Q)$$
plus sub-tour elimination.

An exact MIP of this grows quickly; the routing solver builds a first solution (cheapest arc)
and improves it with guided local search, keeping the capacity as a "dimension" on the route.
"""

import math

from ortools.constraint_solver import pywrapcp, routing_enums_pb2

from orlab.core import Solution

EXAMPLE = {
    # the plant's parts depot and eight dealers on a 100 x 100 km map; pallets of service parts a day
    "stops": [
        {"stop": "Plant West (depot)", "x": 50, "y": 50, "pallets": 0},
        {"stop": "Dealer Nord",        "x": 48, "y": 92, "pallets": 3},
        {"stop": "Dealer Hafen",       "x": 15, "y": 80, "pallets": 4},
        {"stop": "Dealer West",        "x": 8,  "y": 45, "pallets": 2},
        {"stop": "Dealer Süd",         "x": 30, "y": 10, "pallets": 5},
        {"stop": "Dealer Flughafen",   "x": 70, "y": 15, "pallets": 3},
        {"stop": "Dealer Ost",         "x": 92, "y": 40, "pallets": 4},
        {"stop": "Dealer Park",        "x": 85, "y": 78, "pallets": 2},
        {"stop": "Dealer Zentrum",     "x": 58, "y": 62, "pallets": 3},
    ],
    "fleet": [{"vans": 3, "pallets per van": 10}],
}


def _dist(a, b):
    return int(round(math.hypot(a["x"] - b["x"], a["y"] - b["y"])))


def explain(data):
    stops, fleet = data["stops"], data["fleet"][0]
    return {
        "decide": f"Which of the {int(fleet['vans'])} vans visits which of the {len(stops) - 1} dealers, and in what order.",
        "goal": "The fewest kilometres driven in total.",
        "limits": [f"Each van carries at most {int(fleet['pallets per van'])} pallets",
                   "Every dealer is visited exactly once; every van starts and ends at the depot",
                   "Distances are straight-line km on the map"],
    }


def solve(data):
    stops, fleet = data["stops"], data["fleet"][0]
    n_vans, cap = int(fleet["vans"]), int(fleet["pallets per van"])
    demand = [int(s["pallets"] or 0) for s in stops]
    if sum(demand) > n_vans * cap:
        return Solution("infeasible", None, f"{sum(demand)} pallets but the fleet carries {n_vans * cap}.",
                        ["Add a van or a second trip."])
    if max(demand) > cap:
        return Solution("infeasible", None, "One dealer orders more than a van carries.", ["Split the order."])
    dist = [[_dist(a, b) for b in stops] for a in stops]

    # 1. Declare the routing index manager and model (node 0 is the depot).
    manager = pywrapcp.RoutingIndexManager(len(stops), n_vans, 0)
    routing = pywrapcp.RoutingModel(manager)
    # 2.-4. Arc cost = km (the objective); the capacity constraint is a "dimension" that adds up pallets.
    transit = routing.RegisterTransitCallback(
        lambda i, j: dist[manager.IndexToNode(i)][manager.IndexToNode(j)])
    routing.SetArcCostEvaluatorOfAllVehicles(transit)
    load = routing.RegisterUnaryTransitCallback(lambda i: demand[manager.IndexToNode(i)])
    routing.AddDimensionWithVehicleCapacity(load, 0, [cap] * n_vans, True, "pallets")
    # 5. Solve: cheapest-arc first solution, then guided local search for a short while.
    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    params.time_limit.FromMilliseconds(int(data.get("ms", 800)))
    assignment = routing.SolveWithParameters(params)
    if assignment is None:
        return Solution("infeasible", None, "No routes found.", [])
    # 6. Read the routes back.
    routes, rows = [], []
    for v in range(n_vans):
        idx, path, km, pallets = routing.Start(v), [], 0, 0
        while not routing.IsEnd(idx):
            node = manager.IndexToNode(idx)
            path.append(node); pallets += demand[node]
            nxt = assignment.Value(routing.NextVar(idx))
            km += dist[node][manager.IndexToNode(nxt)]
            idx = nxt
        path.append(0)
        if len(path) > 2:
            routes.append({"van": v + 1, "path": path, "km": km, "pallets": pallets})
            rows.append({"van": f"Van {v + 1}", "route": " → ".join(stops[i]["stop"] for i in path),
                         "km": km, "pallets": pallets, "load": pallets / cap})
    total = sum(r["km"] for r in routes)
    longest = max(routes, key=lambda r: r["km"])
    bullets = [f"**{total} km** with {len(routes)} of {n_vans} vans; the longest round is "
               f"Van {longest['van']} with {longest['km']} km.",
               f"Vans carry {', '.join(f'{r['pallets']}/{cap}' for r in routes)} pallets: "
               f"{sum(demand) / (len(routes) * cap):.0%} of the capacity used.",
               "Routing solver: cheapest-arc start, then guided local search; the answer is very good, "
               "not proven optimal."]
    return Solution("feasible", float(total), f"{total} km, {len(routes)} vans.", bullets, {"routes": rows},
                    solver="Routing solver", extra={"routes": routes, "dist": dist})
