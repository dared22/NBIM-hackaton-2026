"""Hent stemmegivningsdata (SEC Form N-PX) for en forvalter.

N-PX har vaert paakrevd som strukturert XML siden foerste rapport 31.08.2024.
Hver stemmepost inneholder utsteder, CUSIP, forslagstekst ordrett fra
stemmeseddelen, kategori, stemmeretning og antall aksjer.

Bruk:
    python hent_npx.py --cik 1364742 --inspect     # se hvilke tagger filen bruker
    python hent_npx.py --cik 1364742 --ut votes.csv

CIK finner du via https://www.sec.gov/cgi-bin/browse-edgar?company=<navn>&action=getcompany
Eksempel: 1364742 = BlackRock Inc.

MERK: SEC krever en User-Agent med kontaktinfo. Sett din egen e-post nedenfor.
"""

import argparse
import collections
import csv
import io
import json
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

USER_AGENT = "Hackathon 2026 student <din.epost@skole.no>"  # <-- endre denne


def hent(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req) as r:
        return r.read()


def finn_npx_filer(cik):
    """Returner (accession, primaerdokument) for alle N-PX-innsendinger."""
    url = f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json"
    data = json.loads(hent(url))
    nylige = data["filings"]["recent"]
    treff = []
    for form, acc, doc in zip(
        nylige["form"], nylige["accessionNumber"], nylige["primaryDocument"]
    ):
        if form.startswith("N-PX"):
            treff.append((acc.replace("-", ""), doc))
    return treff


def hent_xml(cik, accession, dokument):
    base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession}"
    if dokument.lower().endswith(".xml"):
        return hent(f"{base}/{dokument}")
    # Noen innsendinger pakker XML-en i en ZIP eller har den under et annet navn.
    indeks = json.loads(hent(f"{base}/index.json"))
    for post in indeks["directory"]["item"]:
        navn = post["name"]
        if navn.lower().endswith(".xml") and "npx" in navn.lower():
            return hent(f"{base}/{navn}")
        if navn.lower().endswith(".zip"):
            z = zipfile.ZipFile(io.BytesIO(hent(f"{base}/{navn}")))
            for indre in z.namelist():
                if indre.lower().endswith(".xml"):
                    return z.read(indre)
    raise SystemExit(f"Fant ingen XML i {base}")


def inspiser(xml_bytes):
    """Skriv ut hvilke tagger som finnes og hvor mange av hver.

    Kjoer denne foerst. Skjemaet er stort, og du trenger bare 5-6 felter.
    Bruk utskriften til aa fylle inn FELTER nedenfor.
    """
    rot = ET.fromstring(xml_bytes)
    teller = collections.Counter(
        el.tag.split("}")[-1] for el in rot.iter() if el.text and el.text.strip()
    )
    for tag, n in teller.most_common(60):
        print(f"{n:8d}  {tag}")


# Fyll inn etter --inspect. Nokkel = kolonnenavn du vil ha, verdi = tagnavn i XML.
FELTER = {
    "utsteder": "issuerName",
    "cusip": "cusip",
    "moetedato": "meetingDate",
    "forslag": "voteDescription",
    "kategori": "voteCategory",
    "stemme": "voteRecord",
}


def parse(xml_bytes, felter=FELTER):
    """Plukk ut alle noder som inneholder utsteder-tagen, og les feltene under dem."""
    rot = ET.fromstring(xml_bytes)
    utsteder_tag = felter["utsteder"]
    rader = []
    for node in rot.iter():
        barn = {el.tag.split("}")[-1]: (el.text or "").strip() for el in node.iter()}
        if utsteder_tag not in barn:
            continue
        rad = {kol: barn.get(tag, "") for kol, tag in felter.items()}
        if rad["forslag"]:
            rader.append(rad)
    return rader


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--cik", required=True)
    p.add_argument("--inspect", action="store_true")
    p.add_argument("--ut", default="votes.csv")
    a = p.parse_args()

    filer = finn_npx_filer(a.cik)
    if not filer:
        raise SystemExit("Ingen N-PX-innsendinger funnet for denne CIK-en.")
    print(f"Fant {len(filer)} N-PX-innsendinger. Bruker den nyeste: {filer[0][0]}")

    xml_bytes = hent_xml(a.cik, *filer[0])
    if a.inspect:
        inspiser(xml_bytes)
        return

    rader = parse(xml_bytes)
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
