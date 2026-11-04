"""Load the plant description (plant.yaml) and derive the numbers the models share."""

from pathlib import Path

import yaml

DEFAULT_PLANT = Path(__file__).with_name("plant.yaml")


def load_plant(path=None):
    with open(path or DEFAULT_PLANT, encoding="utf-8") as f:
        return yaml.safe_load(f)


def shifts_per_week(plant):
    return plant["plant"]["days_per_week"] * len(plant["plant"]["shifts"])


def minutes_per_day(plant):
    """Working minutes per day (07:00-23:00 = 960)."""
    return sum(s["hours"] * 60 for s in plant["plant"]["shifts"].values())


def minutes_per_week(plant):
    return plant["plant"]["days_per_week"] * minutes_per_day(plant)


def available_minutes_per_unit(plant):
    """Minutes one station unit really runs per week (all shifts x availability)."""
    return minutes_per_week(plant) * plant["plant"]["availability"]
