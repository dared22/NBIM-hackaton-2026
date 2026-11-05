"""Bygg et selskap-aar-panel fra SEC Financial Statement Data Sets.

Kilden er kvartalsvise ZIP-filer med tall hentet ut av alle innleverte regnskaper,
2009 Q1 til i dag:
    https://www.sec.gov/files/dera/data/financial-statement-data-sets/YYYYqQ.zip

Hver ZIP inneholder tabulatorseparerte filer, blant annet sub.txt (innsendinger)
og num.txt (tallverdier). Skriptet skriver ut innholdet i arkivet foerste gang,
saa dere ser filnavnene selv.

Bruk:
    python hent_fsds.py --kvartaler 2021q1 2021q2 --ut panel.csv
"""

import argparse
import collections
import csv
import io
import urllib.request
import zipfile

USER_AGENT = "Hackathon 2026 student <din.epost@skole.no>"  # <-- endre denne

BASE = "https://www.sec.gov/files/dera/data/financial-statement-data-sets"

# Tagger vi trenger for de fem startflaggene i flagg.py.
TAGGER = {
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "NetIncomeLoss",
    "NetCashProvidedByUsedInOperatingActivities",
    "AccountsReceivableNetCurrent",
    "Assets",
    "InventoryNet",
    "LiabilitiesAndStockholdersEquity",
}


def last_ned(kvartal):
    url = f"{BASE}/{kvartal}.zip"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req) as r:
        return zipfile.ZipFile(io.BytesIO(r.read()))


def les_tsv(z, navn):
    with z.open(navn) as f:
        tekst = io.TextIOWrapper(f, encoding="utf-8", errors="replace")
        return list(csv.DictReader(tekst, delimiter="\t"))


def hent_kvartal(kvartal, vis_innhold=False):
    z = last_ned(kvartal)
    if vis_innhold:
        print(f"{kvartal}: {z.namelist()}")

    # sub.txt: en rad per innsending. Vi vil ha aarsregnskapene (10-K).
    innsendinger = {
        rad["adsh"]: rad
        for rad in les_tsv(z, "sub.txt")
        if rad.get("form", "").startswith("10-K")
    }

    # num.txt: en rad per tallverdi. Filtrer paa taggene vi trenger,
    # og paa aarsperioder (qtrs == "4" for flytstoerrelser, "0" for balanse).
    ut = collections.defaultdict(dict)
    for rad in les_tsv(z, "num.txt"):
        if rad["adsh"] not in innsendinger or rad["tag"] not in TAGGER:
            continue
        if rad.get("qtrs") not in ("0", "4") or rad.get("coreg"):
            continue
        try:
            verdi = float(rad["value"])
        except (ValueError, KeyError):
            continue
        n = innsendinger[rad["adsh"]]
        nokkel = (n["cik"], n["name"], rad["ddate"][:4])
        ut[nokkel][rad["tag"]] = verdi
    return ut


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--kvartaler", nargs="+", required=True)
    p.add_argument("--ut", default="panel.csv")
    a = p.parse_args()

    samlet = {}
    for i, kvartal in enumerate(a.kvartaler):
        print(f"Laster {kvartal} ...")
        samlet.update(hent_kvartal(kvartal, vis_innhold=(i == 0)))

    kolonner = ["cik", "navn", "aar"] + sorted(TAGGER)
    with open(a.ut, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(kolonner)
        for (cik, navn, aar), verdier in sorted(samlet.items()):
            w.writerow([cik, navn, aar] + [verdier.get(t, "") for t in sorted(TAGGER)])
    print(f"Skrev {len(samlet)} selskap-aar til {a.ut}")


if __name__ == "__main__":
    main()
