"""Rebuild cities.csv from GeoNames (CC BY 4.0, https://www.geonames.org).

    curl -LO https://download.geonames.org/export/dump/cities15000.zip && unzip cities15000.zip
    python src/plantlab/geo/make_cities.py cities15000.txt

Keeps every town of 15,000+ people in Germany, Austria, Switzerland, Luxembourg and Jordan,
European cities of 50,000+ and the rest of the world from 150,000. German spellings with
umlauts (München, Köln) are kept as search names.
"""

import csv
import sys
from pathlib import Path

HOME = {"DE", "AT", "CH", "LU", "JO"}
EUROPE = {"AL", "AD", "BE", "BA", "BG", "BY", "CY", "CZ", "DK", "EE", "ES", "FI", "FR", "GB", "GR",
          "HR", "HU", "IE", "IS", "IT", "LI", "LT", "LV", "MC", "MD", "ME", "MK", "MT", "NL", "NO",
          "PL", "PT", "RO", "RS", "SE", "SI", "SK", "SM", "TR", "UA", "XK"}
UMLAUTS = set("äöüßÄÖÜ")


def keep(country, population):
    if country in HOME:
        return True
    return population >= (50_000 if country in EUROPE else 150_000)


def main(source):
    rows = []
    with open(source, encoding="utf-8") as f:
        for line in f:
            c = line.rstrip("\n").split("\t")
            name, alternates, lat, lon, country, population = c[1], c[3], c[4], c[5], c[8], int(c[14] or 0)
            if not keep(country, population):
                continue
            alt = sorted({a for a in alternates.split(",") if country in HOME and UMLAUTS & set(a)
                          and len(a) <= 30 and a != name})
            rows.append([name, country, round(float(lat), 4), round(float(lon), 4), population, "|".join(alt)])
    rows.sort(key=lambda r: -r[4])
    out = Path(__file__).with_name("cities.csv")
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["name", "country", "lat", "lon", "population", "alt"])
        w.writerows(rows)
    print(f"{len(rows)} cities -> {out}")


if __name__ == "__main__":
    main(sys.argv[1])
