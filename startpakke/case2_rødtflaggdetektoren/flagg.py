"""Fem startflagg og en rangering. Utvid selv.

Flaggene er klassiske signaler paa svak regnskapskvalitet. Ingen av dem beviser
noe alene - poenget er rangeringen, og at hvert flagg kan spores tilbake til
tallene som utloeste det.

Bruk:
    python flagg.py panel.csv
"""

import csv
import sys
from collections import defaultdict


def omsetning(rad):
    for t in ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax"):
        if rad.get(t):
            return float(rad[t])
    return None


def tall(rad, tag):
    v = rad.get(tag)
    return float(v) if v not in (None, "") else None


def vekst(ny, gammel):
    if ny is None or gammel in (None, 0):
        return None
    return (ny - gammel) / abs(gammel)


def flagg_for(iaar, ifjor):
    """Returner {flaggnavn: (utloest, forklaring)}."""
    f = {}

    oms_n, oms_g = omsetning(iaar), omsetning(ifjor)
    fordr_n, fordr_g = (
        tall(iaar, "AccountsReceivableNetCurrent"),
        tall(ifjor, "AccountsReceivableNetCurrent"),
    )
    res, kontant = (
        tall(iaar, "NetIncomeLoss"),
        tall(iaar, "NetCashProvidedByUsedInOperatingActivities"),
    )
    eiend_n, eiend_g = tall(iaar, "Assets"), tall(ifjor, "Assets")
    lager_n, lager_g = tall(iaar, "InventoryNet"), tall(ifjor, "InventoryNet")

    # 1. Fordringer vokser raskere enn omsetningen
    vo, vf = vekst(oms_n, oms_g), vekst(fordr_n, fordr_g)
    if vo is not None and vf is not None and vf - vo > 0.15:
        f["fordringer_vs_omsetning"] = (
            True,
            f"fordringer +{vf:.0%} mot omsetning +{vo:.0%}",
        )

    # 2. Resultat uten kontantstroem bak
    if res is not None and kontant is not None and res > 0 and kontant < res * 0.5:
        f["resultat_uten_kontantstrom"] = (
            True,
            f"resultat {res:,.0f} men kontantstroem fra drift {kontant:,.0f}",
        )

    # 3. Akkrualer: stor differanse mellom resultat og kontantstroem, skalert
    if None not in (res, kontant, eiend_n) and eiend_n:
        akk = (res - kontant) / eiend_n
        if akk > 0.10:
            f["hoye_akkrualer"] = (True, f"akkrualer {akk:.1%} av totalkapital")

    # 4. Lager vokser raskere enn omsetningen
    vl = vekst(lager_n, lager_g)
    if vo is not None and vl is not None and vl - vo > 0.20:
        f["lager_vs_omsetning"] = (True, f"lager +{vl:.0%} mot omsetning +{vo:.0%}")

    # 5. Kapitalomloepshastighet faller kraftig
    if None not in (oms_n, oms_g, eiend_n, eiend_g) and eiend_n and eiend_g:
        endring = (oms_n / eiend_n) / (oms_g / eiend_g) - 1
        if endring < -0.20:
            f["fallende_omlopshastighet"] = (
                True,
                f"omloepshastighet {endring:.0%} mot i fjor",
            )

    return f


def main(sti):
    rader = list(csv.DictReader(open(sti, encoding="utf-8")))
    per_selskap = defaultdict(dict)
    for r in rader:
        per_selskap[(r["cik"], r["navn"])][r["aar"]] = r

    treff = []
    for (cik, navn), aar in per_selskap.items():
        aarstall = sorted(aar)
        for forrige, denne in zip(aarstall, aarstall[1:]):
            f = flagg_for(aar[denne], aar[forrige])
            if f:
                treff.append((len(f), cik, navn, denne, f))

    treff.sort(reverse=True)
    print(f"{len(treff)} selskap-aar med minst ett flagg. Topp 20:\n")
    for antall, cik, navn, aar, f in treff[:20]:
        print(f"[{antall} flagg] {navn} ({cik}) {aar}")
        for navn_flagg, (_, forklaring) in f.items():
            print(f"    - {navn_flagg}: {forklaring}")
        print()

    print("NB: antall flagg er en NAIV rangering. Dette er baselinen dere skal slaa.")
    print("Vekt flaggene, eller tren en modell paa fasiten - og maal presisjon i topp 50.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    main(sys.argv[1])
