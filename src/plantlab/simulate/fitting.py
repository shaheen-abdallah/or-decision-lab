"""Input analysis: fit probability distributions to observed times (what Arena's Input Analyzer does).

The plant has no real data, so `time_study()` invents the observations: 200 timed cars per
station and model (lognormal around the standard time with the station's cv) and the repair
time of 100 breakdowns per station (exponential around the MTTR). The fitter does not know
those families; it tries five candidates and keeps the best:

    for each candidate F in {Normal, Exponential, Gamma, Lognormal, Weibull}:
        estimate the parameters by maximum likelihood (location fixed at 0, times are > 0)
        D = max_x |F(x) - empirical CDF(x)|        Kolmogorov-Smirnov statistic
    best = candidate with the smallest D

The KS p-value says whether the data contradicts the fitted distribution (p < 0.05: reject).
Because the parameters come from the same data, the p-values are optimistic (Lilliefors);
Arena's Input Analyzer has the same caveat. The simulation draws from the best fits.
"""

import json
from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from scipy import stats

from plantlab.optimize.report import table

CANDIDATES = {
    "Normal": (stats.norm, {}),
    "Exponential": (stats.expon, {"floc": 0}),
    "Gamma": (stats.gamma, {"floc": 0}),
    "Lognormal": (stats.lognorm, {"floc": 0}),
    "Weibull": (stats.weibull_min, {"floc": 0}),
}


@dataclass
class Fit:
    family: str
    dist: object          # frozen scipy distribution, used by the simulation
    ks: float             # KS statistic D
    p_value: float
    n: int
    sample_mean: float

    def describe(self):
        return f"{self.family}(mean {self.dist.mean():.2f}, sd {self.dist.std():.2f})"


def fit_one(samples, family):
    dist, fixed = CANDIDATES[family]
    frozen = dist(*dist.fit(samples, **fixed))
    ks = stats.kstest(samples, frozen.cdf)
    return Fit(family, frozen, ks.statistic, ks.pvalue, len(samples), float(np.mean(samples)))


def fit_best(samples):
    """All five candidates, best (smallest KS statistic) first."""
    return sorted((fit_one(samples, f) for f in CANDIDATES), key=lambda f: f.ks)


def lognormal(rng, mean, cv, n):
    sigma = np.sqrt(np.log(1 + cv ** 2))
    return rng.lognormal(np.log(mean) - sigma ** 2 / 2, sigma, n)


def time_study(plant, seed=None):
    """Invented observations: {(station, model): station minutes, (station, 'repair'): repair minutes}."""
    sim = plant["simulation"]
    seed = sim["seed"] if seed is None else seed
    n = sim["time_study_samples"]
    rng = np.random.default_rng(seed)
    samples = {}
    for st in plant["stations"]:
        s, var = st["id"], sim["stations"][st["id"]]
        for p, minutes in st["minutes"].items():
            if minutes > 0:
                samples[s, p] = lognormal(rng, minutes, var["cv"], n)
        samples[s, "repair"] = rng.exponential(var["mttr"], n // 2)
    bay = sim["rework"]["bay"]
    samples[bay["id"], sim["rework"]["product"]] = lognormal(rng, bay["minutes"], bay["cv"], n)
    return samples


@dataclass
class FitResult:
    fits: dict            # key -> best Fit
    standard: dict        # key -> standard minutes from plant.yaml (None for repairs)
    summary: str = ""

    def dist(self, key):
        return self.fits[key].dist

    def report(self):
        rows = [[f"{s} / {what}", "-" if self.standard[s, what] is None else f"{self.standard[s, what]:.1f}",
                 f"{f.sample_mean:.2f}", f.describe(), f"{f.ks:.3f}", f"{f.p_value:.2f}"]
                for (s, what), f in self.fits.items()]
        return (table(["Station / time", "Standard", "Observed mean", "Best fit", "KS D", "p"], rows)
                + "\n\n" + self.summary)


@lru_cache(maxsize=16)
def _fit_cached(key):
    plant, seed = json.loads(key)
    samples = time_study(plant, seed)
    standard = {}
    for st in plant["stations"]:
        for p, minutes in st["minutes"].items():
            standard[st["id"], p] = minutes
        standard[st["id"], "repair"] = None
    bay = plant["simulation"]["rework"]["bay"]
    standard[bay["id"], plant["simulation"]["rework"]["product"]] = bay["minutes"]
    fits = {k: fit_best(v)[0] for k, v in samples.items()}
    families = {}
    for f in fits.values():
        families[f.family] = families.get(f.family, 0) + 1
    rejected = [f"{s} / {w}" for (s, w), f in fits.items() if f.p_value < 0.05]
    summary = (f"Fitted {len(fits)} time distributions from invented time studies "
               f"({plant['simulation']['time_study_samples']} cars per station and model). Best fits: "
               + ", ".join(f"{k} {v}x" for k, v in sorted(families.items(), key=lambda kv: -kv[1])) + ". "
               + ("No fit is rejected by the KS test (all p >= 0.05)."
                  if not rejected else "KS test rejects: " + ", ".join(rejected) + "."))
    return FitResult(fits, standard, summary)


def fit_plant(plant, seed=None):
    """Best fit for every station time and repair time of the plant (cached: scenarios reuse it)."""
    sim = plant["simulation"]
    seed = sim["seed"] if seed is None else seed
    # only what the time study depends on, so a scenario with bigger buffers reuses the fits
    relevant = {
        "stations": [{"id": s["id"], "minutes": s["minutes"]} for s in plant["stations"]],
        "simulation": {"stations": {k: {"cv": v["cv"], "mttr": v["mttr"]} for k, v in sim["stations"].items()},
                       "rework": {"product": sim["rework"]["product"], "bay": sim["rework"]["bay"]},
                       "time_study_samples": sim["time_study_samples"]},
    }
    return _fit_cached(json.dumps([relevant, seed], sort_keys=True))
