"""Shared pieces of the v2 model pages (product mix, shortest route, max flow).

One state dict per page in st.session_state; every change goes through `Lab.commit()`, which bumps a
revision so widgets get fresh keys (a kept key lets the browser replay a stale value). The blocks
below are the cross-cutting features: fixes when infeasible, show the math, price of a rule,
beat the solver feedback, scenarios side by side and the manager summary.
"""

import copy
import json

import pandas as pd
import streamlit as st

from plantlab import engine
from plantlab.engine import latex, scenarios, words
from plantlab.engine.core import TOL, num, rule_words
from plantlab.models import mix, network

S = st.session_state
MODELS = {"mix": mix.MODEL, **network.MODELS}
OPS = ["ban", "exactly", "at least", "at most"]


@st.cache_data(max_entries=300, show_spinner=False)
def _solve(model, inputs_json, rules_json):
    return engine.solve(MODELS[model], json.loads(inputs_json), json.loads(rules_json))


class Lab:
    """A page's state: inputs, rules, scenarios, the guess, and the revision for widget keys."""

    def __init__(self, key, mt, fresh, fmt):
        if key not in S:
            S[key] = {"inputs": fresh(), "rules": [], "rev": 0, "solved": False, "pos": {}, "scenarios": [],
                      "delta": None, "selected": None, "guess": {}, "scored": False, "revealed": False, "step": None}
        self.key, self.mt, self.s, self.fmt = key, mt, S[key], fmt

    inputs = property(lambda self: self.s["inputs"])
    rules = property(lambda self: self.s["rules"])
    rev = property(lambda self: self.s["rev"])

    def w(self, name):
        """A widget key that is fresh after every change."""
        return f"{self.key}_{name}_{self.rev}"

    def solve(self, inputs=None, rules=None):
        inputs = self.inputs if inputs is None else inputs
        rules = self.rules if rules is None else rules
        return _solve(self.mt.key, json.dumps(inputs, sort_keys=True), json.dumps(rules, sort_keys=True))

    def work(self):
        return copy.deepcopy(self.inputs), copy.deepcopy(self.rules)

    def commit(self, inputs=None, rules=None, note=""):
        before = self.solve()
        self.s["delta"] = (note, before.objective if before.ok else None)
        if inputs is not None:
            self.s["inputs"] = inputs
        if rules is not None:
            self.s["rules"] = rules
        self.s["rev"] += 1

    def reset(self, inputs, note):
        self.commit(inputs, [], note=note)
        self.s.update(solved=False, pos={}, guess={}, scored=False, revealed=False, selected=None, step=None,
                      delta=(note, None))

    # ---------- callbacks

    def solve_now(self):
        self.s["solved"] = True

    def apply_fix(self, i):
        fix = self.solve().fixes[i]
        inputs, rules = engine.apply_fix(self.mt, self.inputs, self.rules, fix)
        self.commit(inputs, rules, note="fix: " + fix.words)

    def add_rule(self, decision, op, value, unit=""):
        _, rules = self.work()
        rules = [r for r in rules if r["decision"] != decision] + [{"decision": decision, "op": op,
                                                                    "value": float(value or 0)}]
        self.commit(rules=rules, note=rule_words(rules[-1], unit))

    def remove_rule(self, i, unit=""):
        _, rules = self.work()
        gone = rules.pop(i)
        self.commit(rules=rules, note="− " + rule_words(gone, unit))

    def save_scenario(self):
        name = (S.get(f"{self.key}_scn_name") or "").strip() or f"Scenario {len(self.s['scenarios']) + 1}"
        self.s["scenarios"] = [s for s in self.s["scenarios"] if s["name"] != name]
        self.s["scenarios"].append(scenarios.snapshot(name, self.mt, self.inputs, self.rules, self.solve()))
        S[f"{self.key}_scn_name"] = ""

    def load_scenario(self):
        s = next(s for s in self.s["scenarios"] if s["name"] == S[f"{self.key}_scn_pick"])
        self.commit(copy.deepcopy(s["inputs"]), copy.deepcopy(s["rules"]), note=f"loaded {s['name']}")
        self.s["solved"] = True

    def import_scenarios(self):
        f = S.get(f"{self.key}_scn_file")
        if f is not None:
            loaded = [s for s in scenarios.loads(f.getvalue().decode("utf-8")) if s.get("model") == self.mt.key]
            names = {s["name"] for s in loaded}
            self.s["scenarios"] = [s for s in self.s["scenarios"] if s["name"] not in names] + loaded

    # ---------- blocks

    def delta(self, result):
        note, before = self.s["delta"] or ("", None)
        if before is None or not result.ok or abs(result.objective - before) < 1e-6:
            return None, note
        return result.objective - before, note

    def answer_problems(self, result):
        """Invalid or infeasible: say why in words; infeasible -> the cheapest fixes, one click each.
        -> True when there is a plan to show."""
        if result.status == "invalid":
            st.warning("**The model is not complete yet.**  \n" + "  \n".join(f"• {p}" for p in result.problems))
            return False
        if result.status == "unbounded":
            st.error(f"**{result.message}**")
            return False
        if not result.ok:
            st.error(f"**{result.message}**")
            if result.fixes:
                st.markdown("**Cheapest fixes** (each one works on its own; apply one to see the new plan):")
                for fix in words.ordered_fixes(result)[:6]:
                    i = result.fixes.index(fix)
                    a, b = st.columns([5, 1], vertical_alignment="center")
                    a.markdown(fix.words[0].upper() + fix.words[1:] + f" → the best plan then gives "
                               f"{self.fmt(fix.objective)}")
                    b.button("Apply", key=f"{self.key}_fix_{self.rev}_{i}", on_click=self.apply_fix, args=(i,))
            return False
        return True

    def summary(self, result):
        st.markdown("**For your manager** (copy with the icon on the right):")
        st.code(self.mt.summary(self.inputs, result), language=None, wrap_lines=True)

    def math(self, result, note="", reveal=None):
        """Words ↔ formulation, row by row. `reveal` = how many limits to show (teach mode)."""
        with st.container(border=True):
            plain = self.mt.plain(self.inputs, self.rules)
            st.markdown(f"**You decide:** {plain['decide']}  \n**You want:** {plain['want']}  \n"
                        f"**You are limited by:** {plain['limited']}")
            g1, g2 = st.columns(2)
            g1.markdown("**The model in general**")
            g1.latex(self.mt.general_latex)
            g2.markdown("**With your numbers**")
            if result.status == "invalid":
                g2.caption("Complete the model first.")
                return
            objective, lims, domain = latex.formulation(engine.build(self.mt, self.inputs, self.rules), per_line=3)
            g2.latex(objective)
            for text, tex in lims[:reveal]:
                w1, w2 = st.columns([1, 2.2], vertical_alignment="center")
                w1.markdown(text)
                w2.latex(tex)
            if reveal is None or reveal >= len(lims):
                st.latex(domain)
            if note:
                st.caption(note)

    def rules_tab(self, result, keys, unit, step=1.0, what="decision"):
        st.markdown("#### Price of a rule")
        st.caption(f"Lock or ban a {what}; CPLEX re-solves and says what the rule costs you.")
        if keys:
            a, b, c, d = st.columns([2.2, 1.2, 1, 0.9], vertical_alignment="bottom")
            sel = self.s["selected"]
            pick = a.selectbox(what.capitalize(), keys, index=keys.index(sel) if sel in keys else 0, key=self.w("rule_pick"))
            op = b.selectbox("Rule", OPS, key=self.w("rule_op"))
            current = result.plan.get(pick, 0.0) if result.ok else 0.0
            value = c.number_input(unit, min_value=0.0, value=float(round(current, 2)), step=step,
                                   key=self.w("rule_val"), disabled=op == "ban")
            d.button("Add rule", on_click=self.add_rule, args=(pick, op, value, unit), type="primary",
                     key=self.w("rule_add"))
        for i, rule in enumerate(self.rules):
            a, b = st.columns([6, 1], vertical_alignment="center")
            a.markdown(rule_words(rule, unit))
            b.button("Remove", key=f"{self.key}_rule_rm_{self.rev}_{i}", on_click=self.remove_rule, args=(i, unit))
        if self.rules and self.s["solved"]:
            if result.ok:
                for line in rule_lines(result, self.fmt):
                    st.markdown(line)
            elif result.status == "infeasible":
                st.warning("With these rules no plan works; see the fixes above.")

    def guess_feedback(self, ev, result):
        if ev.violations:
            st.error(f"**Your plan gives {self.fmt(ev.objective)} but breaks {len(ev.violations)} limit(s):**  \n"
                     + "  \n".join(f"• {w}: {how} {num(round(n, 2))}" for w, n, how in ev.violations))
        else:
            st.success(f"**Your plan works and gives {self.fmt(ev.objective)}.**")
        if self.s["revealed"] and result.ok:
            if ev.gap is not None:
                if ev.gap > 1e-6:
                    rel = f" ({ev.gap / abs(result.objective):.1%})" if result.objective else ""
                    st.markdown(f"**The optimum gives {self.fmt(result.objective)}: yours is {self.fmt(ev.gap)} "
                                f"worse{rel}.**")
                else:
                    st.markdown("**You found the optimum. Well done!**")
                if ev.parts:
                    st.markdown("Where the gap comes from (sums to the gap):")
                    for text, amount in ev.parts:
                        st.markdown(f"• {text} → **{self.fmt(amount)}**")
            else:
                st.markdown(f"**The optimum gives {self.fmt(result.objective)}** and keeps every limit.")

    def reveal_buttons(self):
        a, b = st.columns(2)
        score = a.form_submit_button("Score my plan", icon=":material/scoreboard:")
        reveal = b.form_submit_button("Reveal the optimum", icon=":material/visibility:")
        return score, reveal

    def after_guess(self, score, reveal, guess):
        if score or reveal:
            self.s["guess"] = guess
            self.s["scored"] = True
            if reveal and not self.s["revealed"]:
                self.s.update(revealed=True, solved=True)
                st.rerun()

    def scenarios_tab(self, placeholder, money_sign="€"):
        st.markdown("#### Scenarios side by side")
        a, b = st.columns([3, 1], vertical_alignment="bottom")
        a.text_input("Name this scenario", key=f"{self.key}_scn_name", placeholder=placeholder)
        b.button("Save scenario", icon=":material/bookmark_add:", on_click=self.save_scenario, type="primary",
                 disabled=not self.s["solved"], key=f"{self.key}_scn_save")
        if self.s["scenarios"]:
            headers, rows = scenarios.compare(self.mt, self.s["scenarios"], money_sign)
            st.table(pd.DataFrame(rows, columns=headers).set_index(""))
            a, b, c = st.columns([2, 1, 1.4], vertical_alignment="bottom")
            a.selectbox("Scenario", [s["name"] for s in self.s["scenarios"]], key=f"{self.key}_scn_pick")
            b.button("Load into the builder", on_click=self.load_scenario, key=f"{self.key}_scn_load")
            c.download_button("Download all (JSON)", scenarios.dumps(self.s["scenarios"]),
                              file_name=f"scenarios-{self.mt.key}.json", mime="application/json",
                              icon=":material/download:", key=f"{self.key}_scn_dl")
        st.file_uploader("Load scenarios from a file", type="json", key=f"{self.key}_scn_file",
                         on_change=self.import_scenarios)

    def tabs(self, labels):
        """Tabs that keep the open one when the content above changes shape."""
        return st.tabs(labels, key=f"{self.key}_tab", on_change="rerun")


def rule_lines(result, fmt):
    """What the user's rules cost, together and one by one, with the page's own number format."""
    if not result.rule_prices or result.objective_without_rules is None:
        return []
    sign = 1 if result.sense == "min" else -1
    total = sign * (result.objective - result.objective_without_rules)
    out = ["**Your rules change nothing: the best plan already follows them.**" if abs(total) <= TOL else
           f"**Your rules {'cost' if total > 0 else 'save'} you {fmt(abs(total))} in all.**"]
    for p in result.rule_prices:
        if p.alone is None:
            alone = "impossible on its own"
        elif abs(p.alone) <= TOL:
            alone = "free on its own (the best plan does this anyway)"
        else:
            alone = f"costs {fmt(p.alone)} on its own"
        out.append(f"{p.words}: {alone}.")
    return out


def metric_delta(value, fmt):
    if value is None:
        return None
    return ("+" if value > 0 else "−") + fmt(abs(value))
