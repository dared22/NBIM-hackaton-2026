"""Hent DEF 14A (innkalling) for moetene i en eller flere stemmefiler.

Formatet leses fra kolonnene. Disse stoettes:
  - votes.csv (fra hent_npx.py): MOT betyr stemme AGAINST eller WITHHOLD.
  - real_votes.csv og npx_votes.csv: MOT betyr against_board = 1.

For hvert moete:
  1. Koble selskapet til CIK, i denne rekkefoelgen: eksakt navn i SECs tickerliste,
     ticker (bare amerikanske selskaper), eksakt navn i SECs historiske navneliste.
     Tvetydige navn hoppes over i stedet for aa gjette.
  2. Velg siste DEF 14A levert 0-120 dager foer moetet. Dokumenter etter moetet
     brukes aldri, siden de ville vaert framtidig informasjon.
  3. Last ned dokumentet til <ut>/ og skriv resultatet til <ut>/kobling.csv.
     Bruk moete_id til aa koble tilbake til meeting_id i stemmefilen.

Utenlandske selskaper leverer sjelden DEF 14A, men noen gjoer det (for eksempel
irske og bermudiske). De proeves derfor ogsaa, og kolonnen land viser hvilke de er.

Avbrutt kjoering kan startes paa nytt. Ferdige moeter hoppes over, og rader med
status "feil" proeves igjen.

Bruk:
    python hent_def14a.py real_votes.csv npx_votes.csv --utvalg  # alle MOT + like mange uten
    python hent_def14a.py votes.csv                              # alle moeter
    python hent_def14a.py real_votes.csv --utvalg --maks 20      # rask test

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
USA = {"UNITED STATES", "USA", "US"}
MAKS_DAGER_FOER_MOETE = 120
KOLONNER = [
    "moete_id", "selskap_id", "moetedato", "utsteder", "land", "kilde", "har_mot",
    "cik", "koblet_via", "status", "leveringsdato", "accession", "url", "fil",
]

# Selskapsformer som skrives ulikt i stemmefilene og EDGAR.
SELSKAPSFORMER = {"INC", "INCORPORATED", "CORP", "CORPORATION", "CO", "COMPANY", "LTD", "LIMITED", "PLC", "LLC", "LP", "THE"}


def normaliser(navn):
    navn = navn.upper().replace("&", " AND ")
    navn = re.sub(r"\(.*?\)", " ", navn)  # landsangivelse som "NICE Ltd. (Israel)"
    navn = re.sub(r"/[A-Z]{2,3}/?$", " ", navn)  # EDGAR-suffiks som /DE/
    ord_ = re.sub(r"[^A-Z0-9 ]", " ", navn).split()
    return " ".join(o for o in ord_ if o not in SELSKAPSFORMER)


def normaliser_ticker(ticker):
    return ticker.strip().upper().replace(".", "-")


def bygg_indekser(cache_mappe):
    """Oppslag fra navn og ticker til CIK, fra SECs ticker- og navneliste."""
    aktive = hent_med_cache("https://www.sec.gov/files/company_tickers.json", cache_mappe / "company_tickers.json")
    navn, tickere = {}, {}
    for post in json.loads(aktive).values():
        navn.setdefault(normaliser(post["title"]), set()).add(int(post["cik_str"]))
        tickere[normaliser_ticker(post["ticker"])] = int(post["cik_str"])

    # Historiske navn fanger opp avnoterte og omdoepte selskaper, men er mye
    # stoeyere enn tickerlisten.
    historiske = {}
    tekst = hent_med_cache("https://www.sec.gov/Archives/edgar/cik-lookup-data.txt", cache_mappe / "cik-lookup-data.txt")
    for linje in tekst.decode("latin-1").splitlines():
        deler = linje.rstrip(":").rsplit(":", 1)
        if len(deler) == 2 and deler[1].isdigit():
            historiske.setdefault(normaliser(deler[0]), set()).add(int(deler[1]))
    return navn, tickere, historiske


def hent_med_cache(url, sti):
    if not sti.exists():
        print(f"Laster ned {url} ...")
        sti.write_bytes(hent(url))
    return sti.read_bytes()


def finn_cik(moete, navn, tickere, historiske):
    """Returner (cik, koblet_via, status). status er ok, ingen_cik eller tvetydig_navn."""
    noekkel = normaliser(moete["utsteder"])
    treff = navn.get(noekkel, set())
    if len(treff) == 1:
        return next(iter(treff)), "navn", "ok"

    # Utenlandske tickere kan vaere like amerikanske uten aa vaere samme selskap.
    if moete["land"].upper() in USA:
        cik = tickere.get(normaliser_ticker(moete["ticker"]))
        if cik:
            return cik, "ticker", "ok"

    historisk = historiske.get(noekkel, set())
    if len(historisk) == 1 and not treff:
        return next(iter(historisk)), "historisk_navn", "ok"
    if treff or historisk:
        return None, "", "tvetydig_navn"
    return None, "", "ingen_cik"


def def14a_for(cik, cache, fra, til):
    """Alle DEF 14A for et selskap: liste med (leveringsdato, accession, dokument)."""
    if cik in cache:
        return cache[cik]
    data = json.loads(hent(f"https://data.sec.gov/submissions/CIK{cik:010d}.json"))
    bolker = [data["filings"]["recent"]]
    for fil in data["filings"].get("files", []):
        if fil["filingTo"] >= fra and fil["filingFrom"] <= til:
            bolker.append(json.loads(hent(f"https://data.sec.gov/submissions/{fil['name']}")))
    filer = []
    for b in bolker:
        for form, dato, acc, dok in zip(b["form"], b["filingDate"], b["accessionNumber"], b["primaryDocument"]):
            if form == "DEF 14A":
                filer.append((dato, acc.replace("-", ""), dok))
    cache[cik] = filer
    return filer


def tidligst_levert(moetedato):
    moete = dt.date.fromisoformat(moetedato)
    return (moete - dt.timedelta(days=MAKS_DAGER_FOER_MOETE)).isoformat()


def velg_filing(filer, moetedato):
    """Siste DEF 14A levert innen vinduet foer moetet, eller None."""
    fra = tidligst_levert(moetedato)
    kandidater = [f for f in filer if fra <= f[0] <= moetedato]
    return max(kandidater) if kandidater else None


def tolk_rad(r):
    """Gjoer en rad fra et av formatene om til felles felter."""
    if "meeting_id" in r:
        return {
            "moete_id": r["meeting_id"],
            "selskap_id": r["company_id"],
            "moetedato": r["meeting_date"],
            "utsteder": r["company"],
            "ticker": r["ticker"],
            "land": r["country"],
            "har_mot": r["against_board"] in ("1", "1.0"),
        }
    return {
        "moete_id": f"{r['cusip']}_{r['moetedato']}",
        "selskap_id": r["cusip"],
        "moetedato": r["moetedato"],
        "utsteder": r["utsteder"],
        "ticker": "",
        "land": "",
        "har_mot": r["stemme"].upper() in MOT,
    }


def les_moeter(stier):
    """Ett moete per moete_id, merket med om det har en MOT-stemme."""
    moeter = {}
    for sti in stier:
        with open(sti, encoding="utf-8-sig", newline="") as f:
            leser = csv.DictReader(f)
            if not {"meeting_id", "against_board"} <= set(leser.fieldnames) and not {"cusip", "moetedato", "stemme"} <= set(leser.fieldnames):
                raise SystemExit(f"Kjenner ikke igjen formatet i {sti}. Kolonner: {leser.fieldnames}")
            for r in leser:
                rad = tolk_rad(r)
                if not rad["moetedato"]:
                    continue
                m = moeter.setdefault(rad["moete_id"], {**rad, "kilde": Path(sti).name})
                m["har_mot"] = m["har_mot"] or rad["har_mot"]
                # Samme moete kan finnes i flere filer, og bare noen har land og ticker.
                m["land"] = m["land"] or rad["land"]
                m["ticker"] = m["ticker"] or rad["ticker"]
    return moeter


def trekk_utvalg(moeter, seed=42):
    """Alle moeter med MOT-stemme, pluss like mange tilfeldige uten."""
    med_mot = sorted(k for k, m in moeter.items() if m["har_mot"])
    uten = sorted(k for k, m in moeter.items() if not m["har_mot"])
    random.Random(seed).shuffle(uten)
    return med_mot + uten[: len(med_mot)]


def les_ferdige(sti):
    """Rader fra forrige kjoering, uten de som feilet. Godtar ogsaa eldre logger."""
    if not sti.exists():
        return []
    with open(sti, encoding="utf-8", newline="") as f:
        rader = [r for r in csv.DictReader(f) if r["status"] != "feil"]
    for r in rader:
        if "cusip" in r:
            r["moete_id"] = f"{r['cusip']}_{r['moetedato']}"
            r["selskap_id"] = r["cusip"]
    return [{k: r.get(k, "") for k in KOLONNER} for r in rader]


def skriv_oppsummering(logg):
    with open(logg, encoding="utf-8", newline="") as f:
        alle = list(csv.DictReader(f))
    print(f"\nStatus per moete ({len(alle)} totalt):")
    for status in sorted({r["status"] for r in alle}):
        rader = [r for r in alle if r["status"] == status]
        mot = sum(r["har_mot"] == "1" for r in rader)
        usa = sum(r["land"].upper() in USA for r in rader)
        print(f"  {status:16s} {len(rader):5d}  (herav {mot} med MOT, {usa} fra USA)")
    print(f"Logg: {logg}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("stemmefiler", nargs="+", help="en eller flere CSV-filer med stemmer")
    p.add_argument("--ut", default="def14a")
    p.add_argument("--utvalg", action="store_true", help="alle moeter med MOT + like mange uten")
    p.add_argument("--maks", type=int, help="maks antall moeter, til testing")
    a = p.parse_args()

    ut = Path(a.ut)
    ut.mkdir(parents=True, exist_ok=True)
    moeter = les_moeter(a.stemmefiler)
    noekler = trekk_utvalg(moeter) if a.utvalg else sorted(moeter)
    if a.maks:
        # Bland, slik at en test ikke bare ser paa MOT-moeter eller tidlige datoer.
        random.Random(42).shuffle(noekler)
        noekler = noekler[: a.maks]

    logg = ut / "kobling.csv"
    ferdige = les_ferdige(logg)
    gjort = {r["moete_id"] for r in ferdige}
    gjenstaar = [k for k in noekler if k not in gjort]
    print(f"{len(moeter)} moeter i stemmefilene, {len(noekler)} valgt, {len(gjenstaar)} gjenstaar.")
    if not gjenstaar:
        skriv_oppsummering(logg)
        return

    datoer = [moeter[k]["moetedato"] for k in gjenstaar]
    fra, til = tidligst_levert(min(datoer)), max(datoer)

    navn, tickere, historiske = bygg_indekser(ut)
    cache = {}
    with open(logg, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=KOLONNER)
        w.writeheader()
        w.writerows(ferdige)
        for i, moete_id in enumerate(gjenstaar, 1):
            m = moeter[moete_id]
            rad = dict.fromkeys(KOLONNER, "")
            rad.update({k: m[k] for k in ("moete_id", "selskap_id", "moetedato", "utsteder", "land", "kilde")})
            rad["har_mot"] = int(m["har_mot"])
            cik, rad["koblet_via"], rad["status"] = finn_cik(m, navn, tickere, historiske)
            if cik:
                rad["cik"] = cik
                try:
                    valgt = velg_filing(def14a_for(cik, cache, fra, til), m["moetedato"])
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

    skriv_oppsummering(logg)


if __name__ == "__main__":
    main()
