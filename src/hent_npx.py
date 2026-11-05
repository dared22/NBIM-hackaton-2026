"""Hent stemmegivningsdata (SEC Form N-PX) for en forvalter.

N-PX har vaert paakrevd som strukturert XML siden foerste rapport 31.08.2024.
Hver stemmepost inneholder utsteder, CUSIP, forslagstekst ordrett fra
stemmeseddelen, kategori, stemmeretning og antall aksjer.

Bruk:
    python hent_npx.py --cik 1374170 --inspect     # se hvilke tagger filen bruker
    python hent_npx.py --cik 1374170 --ut votes.csv   # alle aar i en tabell
    python hent_npx.py --cik 1374170 --siste          # bare nyeste innsending

CIK finner du via https://www.sec.gov/cgi-bin/browse-edgar?company=<navn>&action=getcompany
Eksempler: 1374170 = Norges Bank (NBIM), 1364742 = BlackRock Inc.

MERK: SEC krever en User-Agent med kontaktinfo. Sett din egen e-post nedenfor.
"""

import argparse
import collections
import csv
import io
import json
import re
import time
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

USER_AGENT = "Hackathon 2026 student <iftikhar.amiri@nmbu.no>"  # <-- endre denne


def hent(url):
    time.sleep(0.2)  # SEC tillater maks 10 kall i sekundet
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req) as r:
        return r.read()


def finn_npx_filer(cik):
    """Returner (accession, innsendt_dato, skjema) for alle N-PX, eldste foerst."""
    url = f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json"
    data = json.loads(hent(url))
    nylige = data["filings"]["recent"]
    treff = []
    for form, acc, dato in zip(
        nylige["form"], nylige["accessionNumber"], nylige["filingDate"]
    ):
        if form.startswith("N-PX"):
            treff.append((acc.replace("-", ""), dato, form))
    return sorted(treff, key=lambda t: t[1])


def hent_xml(cik, accession):
    """Hent stemmetabellen. primary_doc.xml er bare forsiden, saa den hoppes over."""
    base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession}"
    indeks = json.loads(hent(f"{base}/index.json"))
    navn = [post["name"] for post in indeks["directory"]["item"]]
    for n in navn:
        if n.lower().endswith(".xml") and n.lower() != "primary_doc.xml":
            return hent(f"{base}/{n}")
    for n in navn:
        if n.lower().endswith(".zip"):
            z = zipfile.ZipFile(io.BytesIO(hent(f"{base}/{n}")))
            for indre in z.namelist():
                if indre.lower().endswith(".xml") and "primary_doc" not in indre.lower():
                    return z.read(indre)
    raise SystemExit(f"Fant ingen stemmetabell i {base}")


def lokal(el):
    """Tagnavn uten XML-navnerom."""
    return el.tag.split("}")[-1]


def inspiser(xml_bytes):
    """Skriv ut hvilke tagger som finnes og hvor mange av hver."""
    rot = ET.fromstring(xml_bytes)
    teller = collections.Counter(
        lokal(el) for el in rot.iter() if el.text and el.text.strip()
    )
    for tag, n in teller.most_common(60):
        print(f"{n:8d}  {tag}")


# Nokkel = kolonnenavn i CSV-en, verdi = tagnavn i XML.
# for_eller_mot_ledelsen sier om stemmen var FOR eller AGAINST ledelsens
# anbefaling. Det er maalvariabelen, ikke "stemme" alene.
FELTER = {
    "utsteder": "issuerName",
    "cusip": "cusip",
    "isin": "isin",
    "moetedato": "meetingDate",
    "forslag": "voteDescription",
    "kategori": "categoryType",
    "stemme": "howVoted",
    "for_eller_mot_ledelsen": "managementRecommendation",
}


def iso_dato(tekst):
    """MM/DD/YYYY -> YYYY-MM-DD, saa datoene kan sorteres."""
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", tekst)
    return f"{m[3]}-{int(m[1]):02d}-{int(m[2]):02d}" if m else tekst


def parse(xml_bytes, felter=FELTER):
    """En rad per stemme. Hvert forslag ligger i en <proxyTable>, og selve
    stemmen i en eller flere <voteRecord> under den."""
    rot = ET.fromstring(xml_bytes)
    rader = []
    for tabell in rot.iter():
        if lokal(tabell) != "proxyTable":
            continue
        felles, stemmer = {}, []
        for el in tabell.iter():
            if lokal(el) == "voteRecord":
                stemmer.append({lokal(b): (b.text or "").strip() for b in el})
            elif el.text and el.text.strip():
                felles.setdefault(lokal(el), el.text.strip())
        for stemme in stemmer or [{}]:
            verdier = {**felles, **stemme}
            rad = {kol: verdier.get(tag, "") for kol, tag in felter.items()}
            rad["moetedato"] = iso_dato(rad["moetedato"])
            if rad["forslag"]:
                rader.append(rad)
    return rader


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--cik", required=True)
    p.add_argument("--inspect", action="store_true")
    p.add_argument("--siste", action="store_true", help="bare nyeste innsending")
    p.add_argument("--ut", default="votes.csv")
    a = p.parse_args()

    filer = finn_npx_filer(a.cik)
    if not filer:
        raise SystemExit("Ingen N-PX-innsendinger funnet for denne CIK-en.")
    print(f"Fant {len(filer)} N-PX-innsendinger.")

    if a.inspect:
        inspiser(hent_xml(a.cik, filer[-1][0]))
        return

    rader = []
    for accession, innsendt, skjema in filer[-1:] if a.siste else filer:
        nye = parse(hent_xml(a.cik, accession))
        for rad in nye:
            rad.update(innsendt=innsendt, skjema=skjema, accession=accession)
        print(f"  {innsendt} {skjema}: {len(nye)} stemmeposter")
        rader.extend(nye)

    if not rader:
        raise SystemExit(
            "Ingen rader. Kjoer med --inspect og oppdater FELTER i denne filen."
        )
    with open(a.ut, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rader[0]))
        w.writeheader()
        w.writerows(rader)
    print(f"Skrev {len(rader)} stemmeposter til {a.ut}")


if __name__ == "__main__":
    main()
