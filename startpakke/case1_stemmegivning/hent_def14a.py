"""Hent DEF 14A (innkalling) for moetene i votes.csv.

For hvert moete (cusip + moetedato):
  1. Koble selskapsnavn til CIK. Bare eksakt treff etter normalisering av navnet.
     Tvetydige navn hoppes over i stedet for aa gjette.
  2. Velg siste DEF 14A levert 0-120 dager foer moetet. Dokumenter etter moetet
     brukes aldri, siden de ville vaert framtidig informasjon.
  3. Last ned dokumentet til <ut>/ og skriv resultatet til <ut>/kobling.csv.

Avbrutt kjoering kan startes paa nytt. Ferdige moeter hoppes over, og rader med
status "feil" proeves igjen.

Bruk:
    python hent_def14a.py votes.csv --utvalg          # alle MOT + like mange FOR
    python hent_def14a.py votes.csv                   # alle moeter
    python hent_def14a.py votes.csv --utvalg --maks 20  # rask test

User-Agent settes i hent_npx.py.
"""

import argparse
import csv
import datetime as dt
import json
import random
import re
import urllib.error
from pathlib import Path

from hent_npx import hent

MOT = {"AGAINST", "WITHHOLD"}
MAKS_DAGER_FOER_MOETE = 120
KOLONNER = ["cusip", "moetedato", "utsteder", "har_mot", "cik", "status", "leveringsdato", "accession", "url", "fil"]

# Selskapsformer som skrives ulikt i N-PX og EDGAR.
SELSKAPSFORMER = {"INC", "INCORPORATED", "CORP", "CORPORATION", "CO", "COMPANY", "LTD", "LIMITED", "PLC", "LLC", "LP", "THE"}


def normaliser(navn):
    navn = navn.upper().replace("&", " AND ")
    navn = re.sub(r"/[A-Z]{2,3}/?$", " ", navn)  # EDGAR-suffiks som /DE/
    ord_ = re.sub(r"[^A-Z0-9 ]", " ", navn).split()
    return " ".join(o for o in ord_ if o not in SELSKAPSFORMER)


def bygg_navneindeks(cache_mappe):
    """Normalisert navn -> sett med CIK-er, fra SECs ticker- og navneliste."""
    aktive = hent_med_cache("https://www.sec.gov/files/company_tickers.json", cache_mappe / "company_tickers.json")
    indeks = {}
    for post in json.loads(aktive).values():
        indeks.setdefault(normaliser(post["title"]), set()).add(int(post["cik_str"]))

    # Historiske navn fanger opp avnoterte og omdoepte selskaper. Brukes bare
    # naar tickerlisten ikke har navnet, siden den er mye stoeyere.
    historiske = {}
    tekst = hent_med_cache("https://www.sec.gov/Archives/edgar/cik-lookup-data.txt", cache_mappe / "cik-lookup-data.txt")
    for linje in tekst.decode("latin-1").splitlines():
        deler = linje.rstrip(":").rsplit(":", 1)
        if len(deler) == 2 and deler[1].isdigit():
            historiske.setdefault(normaliser(deler[0]), set()).add(int(deler[1]))
    return indeks, historiske


def hent_med_cache(url, sti):
    if not sti.exists():
        print(f"Laster ned {url} ...")
        sti.write_bytes(hent(url))
    return sti.read_bytes()


def finn_cik(navn, indeks, historiske):
    """Returner (cik, status). status er ok, ingen_cik eller tvetydig_navn."""
    noekkel = normaliser(navn)
    for kilde in (indeks, historiske):
        treff = kilde.get(noekkel, set())
        if len(treff) == 1:
            return next(iter(treff)), "ok"
        if treff:
            return None, "tvetydig_navn"
    return None, "ingen_cik"


def def14a_for(cik, cache):
    """Alle DEF 14A for et selskap: liste med (leveringsdato, accession, dokument)."""
    if cik in cache:
        return cache[cik]
    data = json.loads(hent(f"https://data.sec.gov/submissions/CIK{cik:010d}.json"))
    bolker = [data["filings"]["recent"]]
    for fil in data["filings"].get("files", []):
        if fil["filingTo"] >= "2023-01-01":  # votes.csv starter i 2023
            bolker.append(json.loads(hent(f"https://data.sec.gov/submissions/{fil['name']}")))
    filer = []
    for b in bolker:
        for form, dato, acc, dok in zip(b["form"], b["filingDate"], b["accessionNumber"], b["primaryDocument"]):
            if form == "DEF 14A":
                filer.append((dato, acc.replace("-", ""), dok))
    cache[cik] = filer
    return filer


def velg_filing(filer, moetedato):
    """Siste DEF 14A levert innen vinduet foer moetet, eller None."""
    moete = dt.date.fromisoformat(moetedato)
    fra = (moete - dt.timedelta(days=MAKS_DAGER_FOER_MOETE)).isoformat()
    kandidater = [f for f in filer if fra <= f[0] <= moetedato]
    return max(kandidater) if kandidater else None


def les_moeter(sti):
    """Ett moete per (cusip, moetedato), merket med om det har en MOT-stemme."""
    moeter = {}
    with open(sti, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if not r["moetedato"]:
                continue
            m = moeter.setdefault((r["cusip"], r["moetedato"]), {"utsteder": r["utsteder"], "har_mot": False})
            m["har_mot"] = m["har_mot"] or r["stemme"].upper() in MOT
    return moeter


def trekk_utvalg(moeter, seed=42):
    """Alle moeter med MOT-stemme, pluss like mange tilfeldige uten."""
    med_mot = [k for k, m in moeter.items() if m["har_mot"]]
    uten = sorted(k for k, m in moeter.items() if not m["har_mot"])
    random.Random(seed).shuffle(uten)
    return med_mot + uten[: len(med_mot)]


def les_ferdige(sti):
    """Rader fra forrige kjoering, uten de som feilet."""
    if not sti.exists():
        return []
    with open(sti, encoding="utf-8", newline="") as f:
        return [r for r in csv.DictReader(f) if r["status"] != "feil"]


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("votes")
    p.add_argument("--ut", default="def14a")
    p.add_argument("--utvalg", action="store_true", help="alle moeter med MOT + like mange uten")
    p.add_argument("--maks", type=int, help="maks antall moeter, til testing")
    a = p.parse_args()

    ut = Path(a.ut)
    ut.mkdir(parents=True, exist_ok=True)
    moeter = les_moeter(a.votes)
    noekler = trekk_utvalg(moeter) if a.utvalg else sorted(moeter)
    if a.maks:
        # Bland, slik at en test ikke bare ser paa MOT-moeter eller tidlige datoer.
        random.Random(42).shuffle(noekler)
        noekler = noekler[: a.maks]

    logg = ut / "kobling.csv"
    ferdige = les_ferdige(logg)
    gjort = {(r["cusip"], r["moetedato"]) for r in ferdige}
    gjenstaar = [k for k in noekler if k not in gjort]
    print(f"{len(moeter)} moeter i {a.votes}, {len(noekler)} valgt, {len(gjenstaar)} gjenstaar.")

    indeks, historiske = bygg_navneindeks(ut)
    cache = {}
    with open(logg, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=KOLONNER)
        w.writeheader()
        w.writerows(ferdige)
        for i, (cusip, dato) in enumerate(gjenstaar, 1):
            m = moeter[(cusip, dato)]
            rad = dict.fromkeys(KOLONNER, "")
            rad.update(cusip=cusip, moetedato=dato, utsteder=m["utsteder"], har_mot=int(m["har_mot"]))
            cik, rad["status"] = finn_cik(m["utsteder"], indeks, historiske)
            if cik:
                rad["cik"] = cik
                try:
                    valgt = velg_filing(def14a_for(cik, cache), dato)
                    if not valgt:
                        rad["status"] = "ingen_def14a"
                    else:
                        lev, acc, dok = valgt
                        url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{dok}"
                        fil = ut / f"{cik}_{lev}{Path(dok).suffix or '.htm'}"
                        if not fil.exists():
                            fil.write_bytes(hent(url))
                        rad.update(leveringsdato=lev, accession=acc, url=url, fil=fil.name)
                except (urllib.error.URLError, TimeoutError) as e:
                    rad["status"] = "feil"
                    print(f"  feil for {m['utsteder']}: {e}")
            w.writerow(rad)
            f.flush()
            if i % 100 == 0:
                print(f"  {i}/{len(gjenstaar)}")

    with open(logg, encoding="utf-8", newline="") as f:
        alle = list(csv.DictReader(f))
    print("\nStatus per moete:")
    for status in sorted({r["status"] for r in alle}):
        rader = [r for r in alle if r["status"] == status]
        mot = sum(r["har_mot"] == "1" for r in rader)
        print(f"  {status:16s} {len(rader):5d}  (herav {mot} med MOT)")
    print(f"Logg: {logg}")


if __name__ == "__main__":
    main()
