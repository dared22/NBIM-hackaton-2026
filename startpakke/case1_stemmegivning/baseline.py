"""Baselinen dere maa slaa, og metrikken som faktisk betyr noe.

Baseline: stem alltid som styret anbefaler.
Den treffer typisk 90-95 % av forslagene. Accuracy er derfor ubrukelig som maal.
Det som betyr noe er om dere finner de forslagene der forvalteren stemmer MOT.

Bruk:
    python baseline.py votes.csv
"""

import csv
import sys
from collections import Counter

MOT = {"against", "mot", "withhold"}


def les(sti):
    with open(sti, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def er_mot(rad, kolonne="stemme"):
    return rad.get(kolonne, "").strip().lower() in MOT


def rapport(rader, prediksjoner=None):
    """prediksjoner: liste med True/False, True = modellen tror MOT.
    Utelates den, rapporteres baselinen (alltid FOR)."""
    faktisk = [er_mot(r) for r in rader]
    if prediksjoner is None:
        prediksjoner = [False] * len(rader)

    tp = sum(1 for p, f in zip(prediksjoner, faktisk) if p and f)
    fp = sum(1 for p, f in zip(prediksjoner, faktisk) if p and not f)
    fn = sum(1 for p, f in zip(prediksjoner, faktisk) if not p and f)
    tn = sum(1 for p, f in zip(prediksjoner, faktisk) if not p and not f)

    n = len(rader)
    presisjon = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * presisjon * recall / (presisjon + recall) if presisjon + recall else 0.0

    print(f"Antall forslag        : {n}")
    print(f"Andel MOT-stemmer     : {sum(faktisk) / n:.1%}")
    print(f"Accuracy              : {(tp + tn) / n:.1%}   <- ikke bruk denne alene")
    print(f"Presisjon paa MOT     : {presisjon:.1%}")
    print(f"Recall paa MOT        : {recall:.1%}   <- dette er tallet som teller")
    print(f"F1 paa MOT            : {f1:.1%}")
    print(f"Falske positive       : {fp}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    rader = les(sys.argv[1])
    print("Fordeling av stemmeverdier i datasettet:")
    for verdi, n in Counter(r.get("stemme", "") for r in rader).most_common(10):
        print(f"  {n:8d}  {verdi!r}")
    print()
    print("=== BASELINE: stem alltid som styret ===")
    rapport(rader)
