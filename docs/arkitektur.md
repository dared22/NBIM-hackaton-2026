# Stemmegivningsagenten: arkitektur fra A til Å

NBIM FinTech Hackathon H2026, case 1. Løsningen på grenen `main`.
Én kommando kjører alt: `python3 src/run.py` (ca. 4,5 minutter, ingen API-nøkkel).

## Diagram

```text
+--------------------------+  +-----------------------------+  +-----------------------------+
| NBIMs STEMMER            |  | NBIMs RETNINGSLINJER        |  | SELSKAPSDOKUMENTER          |
| 2019-2026, 37 land       |  | 76 regler, posisjons-       |  | SEC (USA), EDINET (Japan),  |
| historikk + fasit        |  | notater, nettsiden          |  | DART (Sør-Korea)            |
+--------------------------+  +-----------------------------+  +-----------------------------+
        |                              |                                |
        +------------------------------+--------------------------------+
        |
        v
+--------------------------------------------------------------------------------------------+
| 1. VAKT (ren kode, ingen AI)                                                               |
|    Tekst som ligner en instruks, eller som ikke ligner et forslag på en stemmeseddel,      |
|    går rett til et menneske. Det samme gjelder et dokument som henvender seg til en AI.    |
+--------------------------------------------------------------------------------------------+
        |
        v
+--------------------------------------------------------------------------------------------+
| 2. FAKTA                                                                                   |
|    AI-leser (Claude Haiku) leser innkallingen: hvem er uavhengig, leder, styreleder, ...   |
|    Fakta som en regel hviler på, må ha et sitat som kontrolleres ord for ord mot teksten.  |
|    Lønnstall hentes fra tabellene i innkallingen. Japan/Korea-fakta kommer fra Marie.      |
+--------------------------------------------------------------------------------------------+
        |
        v
+--------------------------------------------------------------------------------------------+
| 3. FEM SIGNALER PER FORSLAG                                                                |
|    a) Historikk     hvordan NBIM stemte før: i saken, selskapet, landet, forslagstypen     |
|    b) Regler        NBIMs regler i kode, anvendt på faktaene (stoler bare på regler        |
|                     NBIM faktisk har fulgt de to siste gangene)                            |
|    c) Dommer        Claude Haiku veier fakta mot regler og NBIMs praksis (styrevalg USA)   |
|    d) Jev           beslutningsmodell som leser forslaget og dokumentet (fra Marie)        |
|    e) Modell nr. 2  Maries egen modell på historikk og selskapsfakta                       |
+--------------------------------------------------------------------------------------------+
        |
        v
+-------------------------------------------+  +---------------------------------------------+
| 4a. KOMBINERT MODELL                      |  | 4b. LØNNSMODELL                             |
|     alle land, alle forslagstyper         |  |     lederlønn i USA (say-on-pay)            |
|     veier signalene med vekter            |  |     12 inndata: lønnstall, lønn mot         |
|     lært på tidligere år                  |  |     avkastning og like selskaper,           |
|     -> sannsynlighet for stemme           |  |     NBIMs stemme sist, Jevs lesning         |
|        mot styret                         |  |     -> sannsynlighet                        |
+-------------------------------------------+  +---------------------------------------------+
        |                                               |
        +-----------------------+-----------------------+
                                |
                                v
+--------------------------------------------------------------------------------------------+
| 5. RUTING: hvem avgjør?                                                                    |
|    under 5 %                  -> verktøyet følger styret selv                              |
|    høy, og noe å vise til     -> verktøyet foreslår MOT selv                               |
|       (regel med faktum, lønnstall, eller NBIMs egen mot-stemme i samme sak sist)          |
|    alt annet                  -> til et menneske, med grunnen skrevet ut                   |
|    Lesebryter: nivået på 5 % kan senkes hvis NBIM vil at et menneske skal se mer.          |
+--------------------------------------------------------------------------------------------+
        |
        v
+--------------------------------------------------------------------------------------------+
| 6. UT: én linje per forslag                                                                |
|    stemme (FOR / MOT / AVSTÅ) · sannsynlighet · hvem avgjør · begrunnelse                  |
|    · retningslinjen med ordlyd og sidetall · lenke til selskapsdokumentet                  |
|    Filer: decisions_2026.csv, headline.md, results.md. Vises i dashbordet.                 |
+--------------------------------------------------------------------------------------------+
        |
        v
+--------------------------------------------------------------------------------------------+
| 7. KONTROLL                                                                                |
|    Måles mot NBIMs faktiske stemmer i 2026, som modellen ikke er trent på.                 |
|    87 automatiske tester (bl.a. at fasiten aldri lekker inn) og 3 angrepstester.           |
+--------------------------------------------------------------------------------------------+
```

## Kort: hva skjer

1. **Vakt.** Før noe annet sjekker ren kode om forslagsteksten eller selskapsdokumentet inneholder noe
   som ligner en instruks til en AI. Slike forslag går rett til et menneske.
2. **Fakta.** En AI-modell leser innkallingen og fyller ut fakta om styret og kandidatene. Den stemmer
   ikke. Lønnstall hentes fra tabellene i innkallingen.
3. **Signaler.** Fem kilder sier hver sitt om forslaget: historikken, NBIMs regler anvendt på faktaene,
   en AI-dommer, Jev og Maries modell nummer to.
4. **Modell.** En kombinert modell veier signalene sammen til én sannsynlighet for at NBIM stemmer mot
   styret. Vektene er lært på tidligere år. Lederlønn i USA har sin egen modell med lønnstall.
5. **Ruting.** Verktøyet avgjør selv bare når det er trygt: enten er risikoen under 5 %, eller så hviler
   et MOT-forslag på noe et menneske kan kontrollere. Alt annet sendes til et menneske med grunnen.
6. **Ut.** Hvert forslag får stemme, sannsynlighet, begrunnelse, sitert retningslinje og lenke til kilden.
7. **Kontroll.** Alt måles mot NBIMs faktiske stemmer i 2026, og tester passer på at fasiten ikke lekker.

## Resultat på teståret 2026

| | NBIMs stemmefil, alle land | Lederlønn USA |
|---|---|---|
| Forslag / mot styret | 1 539 / 66 | 1 200 / 114 |
| Følg alltid styret | finner 0 | finner 0 |
| Verktøyet alene sier MOT | 33, derav 26 riktige (79 %) | 93, derav 69 riktige (74 %) |
| Sendt til et menneske | 404 (26 %) | 371 (31 %) |
| Mot-stemmer foreslått eller sett | 56 av 66 (85 %) | 105 av 114 (92 %) |

Lesebryteren på stemmefilen: senkes nivået fra 5 % til 3 %, leser et menneske 610 forslag (40 %), og
64 av 66 mot-stemmer blir foreslått eller sett.

## AI-modeller i løsningen

| Modell | Hva den gjør | Avgjør den en stemme? |
|---|---|---|
| Claude Haiku (leser) | Leser innkallingen og fyller ut fakta med sitat | Nei, reglene anvendes i kode |
| Claude Haiku (dommer) | Veier fakta mot NBIMs regler og praksis for styrevalg i USA | Nei, én inndata til modellen |
| Jev (Typesafe) | Leser forslag og dokument (Maries løype), og lønnstall mot lønnsreglene | Nei, én inndata til modellen |
| Microsoft Decision-1 | Peker ut hvilken del av retningslinjene et forslag hører under | Nei, brukes til siteringen |

Alle svar er lagret i repoet. Det trengs ingen API-nøkkel for å kjøre, teste eller vise løsningen.
En nøkkel (`OPENROUTER_API_KEY` i `.env`) trengs bare for å spørre modellene om nye forslag.

## Hvor i koden

| Del | Fil |
|---|---|
| Alt i én kommando | `src/run.py` |
| Vakt og angrepstester | `src/agent/robustness.py`, `paraphrase_test.py`, `reader_injection_test.py` |
| AI-leser | `src/agent/fetch_board_facts.py` |
| Regler på fakta og på ordlyd | `src/agent/board_rules.py`, `proposal_rules.py` |
| Dommer | `src/agent/judge.py` |
| Jev-svar fra Marie | `data/evidence/jev_pipeline/` |
| Kombinert modell og lesebryter | `src/agent/combined_model.py` |
| Lønnsmodell og Jev på lønnstall | `src/agent/pay_model.py`, `jev_pay.py` |
| Ruting | `src/agent/routing.py` og `src/run.py` |
| Dashbord | `src/dashboard.py` (bygget av Marie, tilpasset `main`) |
| Tester | `tests/test_agent.py` (87) |
| Resultater | `data/outputs/headline.md`, `results.md`, `decisions_2026.csv` |
| Full beskrivelse | `docs/model-card.md` |

## Begrensninger å kunne svare på

- **2026 er kjørt flere ganger** under utviklingen: fire ganger for den kombinerte modellen og seks for
  lønnsmodellen. Det står i modellkortet.
- **Nytt møte:** `main` kjører på stemmefilen. Jev-svar for helt nye forslag må lages i Maries løype.
- **Fakta fra AI-leseren finnes bare for styrevalg i USA** (214 møter). Andre land bruker historikk,
  ordlydsregler og Maries Japan/Korea-fakta.
- **10 av 66 mot-stemmer slippes gjennom** på stemmefilen med standardnivået på 5 %.
- **Et falskt dokument blir trodd.** Vakten stopper instrukser, ikke et selskap som skriver usant.
