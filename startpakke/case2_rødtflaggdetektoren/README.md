# Case 4 – Rødt flagg-detektoren: startpakke

## Hva dere har fått

| Fil | Hva den gjør |
|---|---|
| `hent_fsds.py` | Bygger et selskap-år-panel fra SEC Financial Statement Data Sets. |
| `flagg.py` | Fem klassiske regnskapsflagg og en naiv rangering – baselinen dere skal slå. |

Bare Python 3 sitt standardbibliotek. Skriptene er skrevet mot kildenes dokumenterte
format, men ikke kjørt mot live endepunkt av arrangøren. Første kjøring skriver ut
innholdet i ZIP-arkivet, så dere ser filnavnene selv.

## Kom i gang

```bash
# 1. Sett din egen e-post i USER_AGENT i hent_fsds.py (SEC krever det)
# 2. Start smått – ett år først, så utvid
python hent_fsds.py --kvartaler 2021q1 2021q2 2021q3 2021q4 --ut panel.csv
# 3. Se baselinen
python flagg.py panel.csv
```

Hvert kvartalsarkiv er 50–80 MB. Fem år er 20 nedlastinger – start med to kvartaler
og få hele kjeden til å virke før dere skalerer.

## Fasit – les dette før dere begynner

Dette er den delen som kan spise hele hackathonet hvis dere ikke er disiplinerte.

**Primær fasit: SEC sine håndhevingssaker (AAER).** 3 340 saker tilbake til 1965,
tilgjengelig som HTML-tabell og RSS-feed på
`https://www.sec.gov/enforcement-litigation/accounting-auditing-enforcement-releases`.
Problemet er ikke å hente listen – det er å koble respondentens navn til en CIK og
videre til regnskapsdata. Navnene er fritekst, ofte personer heller enn selskaper.

**Arrangøren deler ut en ferdig CSV med 40–80 saker koblet til CIK.** Bruk den. Ikke
bygg koblingen selv med mindre dere har tid til overs.

**To svakere fasitsignaler dere kan hente maskinelt fra EDGAR alene:**

- **Endringsmelding (10-K/A).** Et selskap som leverer om årsregnskapet har som regel
  hatt et problem. Finnes i `sub.txt` sitt `form`-felt, eller via submissions-API-et.
- **Revisorbytte (8-K punkt 4.01).** Ikke i seg selv et rødt flagg, men brukbart som
  svakt signal. Finnes via EDGAR full-text search.

Begge er støyende. Bruk dem til å utvide treningsgrunnlaget, ikke til å måle
sluttresultatet.

## Krav til leveransen

Ut over de felles reglene:

- **Baseline skal oppgis.** `flagg.py` rangerer på antall flagg. Slå den, og vis med
  hvor mye.
- **Metrikken er presisjon i topp 50, ikke AUC.** Et screeningverktøy brukes ved at
  noen leser toppen av listen. Rapporter også hvor mange falske positive en analytiker
  må gjennom per reelle treff.
- **30-sekundskravet.** Hvert flagg skal peke på tallet eller setningen som utløste
  det. En analytiker skal kunne overprøve flagget uten å åpne koden.
- **Motstandstesten:** konstruer et selskap som treffer flaggene uten å ha gjort noe
  galt – for eksempel et selskap i rask, ærlig vekst. Hvor høyt havner det i
  rangeringen? Rapporter svaret.

## Fallgruver

- **Tidslekkasje.** Håndhevingssaken kommer ofte år etter regnskapet. Bruk bare
  informasjon som var tilgjengelig på rapporteringstidspunktet.
- **Overlevelsesskjevhet.** Selskaper som gikk under mangler i senere kvartaler.
- **Sektoreffekter.** Høye akkrualer er normalt i noen bransjer. Sammenlign innenfor
  sektor, ikke på tvers.
- **Bare fem flagg er ikke nok.** De er et startpunkt. Legg til tekstsignaler –
  endringer i noter og risikofaktorer år over år er der den interessante informasjonen
  ligger, og der ingen har gjort jobben for dere.
