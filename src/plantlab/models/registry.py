"""Home-page cards: one business question per model type, the OR name underneath."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Card:
    key: str
    question: str
    or_name: str
    blurb: str
    group: str
    live: bool = False
    page: str = ""           # app page file when live
    icon: str = ":material/help:"


CARDS = [
    Card("transport", "Where should I ship from?", "Transportation · transshipment (min-cost flow, LP)",
         "Warehouses, hubs and customers on a map; the cheapest way to move the goods.",
         "Networks", live=True, page="pages/transport.py", icon=":material/local_shipping:"),
    Card("shortest", "What's the cheapest way from A to B?", "Shortest route (LP + Dijkstra)",
         "Pick two places on a network; see the route, why, and Dijkstra step by step.", "Networks",
         live=True, page="pages/shortest.py", icon=":material/route:"),
    Card("maxflow", "How much can my network carry at most?", "Maximum flow + minimum cut",
         "Find the bottleneck roads that cap the whole network (the minimum cut).", "Networks",
         live=True, page="pages/maxflow.py", icon=":material/water:"),
    Card("mix", "How much of each product should I make?", "Product mix (LP, graphical method)",
         "Products, machine hours and margins; the best mix and what an extra hour is worth.",
         "Production and people", live=True, page="pages/mix.py", icon=":material/factory:"),
    Card("planning", "How much should I produce each month?", "Production planning (multi-period LP)",
         "Demand per month, capacity, stock and overtime.", "Production and people",
         icon=":material/calendar_month:"),
    Card("assignment", "Who does which job?", "Assignment (Hungarian / LP)",
         "People, jobs and how well each fits; the best match.", "Production and people",
         icon=":material/assignment_ind:"),
    Card("staffing", "How many people per shift?", "Staffing / shift scheduling (IP)",
         "Cover the need in every hour with the fewest paid shifts.", "Production and people",
         icon=":material/groups:"),
]


def card(key):
    return next(c for c in CARDS if c.key == key)
