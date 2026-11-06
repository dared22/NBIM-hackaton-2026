# Stemmegivningsagenten: NBIM FinTech Hackathon 2026, case 1

Agenten foreslår hvordan NBIM bør stemme på hvert forslag på en generalforsamling: **FOR**, **MOT** eller **AVSTÅ**.

For hvert forslag:

- **Begrunnelse:** den viser til retningslinjen som avgjør, med retningslinjens egne ord og sidetall, fakta fra selskapets dokumenter og NBIMs tidligere stemmer.
- **Sannsynlighet:** den gir sannsynligheten for at NBIM stemmer mot styret, og et bånd som sier hvem som avgjør.
- **Manuell vurdering:** usikre forslag sendes til en person. Agenten foreslår bare; den avgir aldri en stemme.

Systemet måles på presisjon og recall for «NBIM stemmer mot styret», mot baselinene «følg alltid styret» og «samme som sist i dette selskapet». Det er også testet mot instruksjoner som er skjult i forslagsteksten og i selskapets dokumenter (prompt injection).

Denne grenen (`main`) og grenen `marie` er to systemer for samme case. Den kombinerte modellen her bruker lagrede svar fra Maries pipeline (Jev og hennes andre modell) som input. Maries pipeline selv, med terminaldemoen og fanen «Ny saksliste», ligger bare på `marie`.

Et diagram over hele løypa står i [`docs/arkitektur.md`](docs/arkitektur.md). Full beskrivelse av metode, resultater og begrensninger står i [`docs/model-card.md`](docs/model-card.md). An English version of this page is in [`README.en.md`](README.en.md).

---

## 1. Kom i gang og kjør

Kjør alt fra rotmappen i repoet. Pipelinen og testene trenger bare Pythons standardbibliotek: ingen pakker, ingen API-nøkkel og ingen internettforbindelse. Modellsvar og SEC-tall ligger lagret i repoet.

```bash
python3 src/run.py                        # alt, ca. fem minutter
python3 src/run.py --quick                # bare beslutninger, hovedtall og dashbordfiler: under ett minutt
python3 -m unittest discover -s tests     # 87 tester, blant dem lekkasjesjekker og fire ende-til-ende-angrep
```

`src/run.py` skriver til `data/outputs/`:

| Fil | Innhold |
|---|---|
| `decisions_2026.csv` | Én rad per forslag i 2026: foreslått stemme, sannsynlighet, bånd, hvem som avgjør, grunner, retningslinje med egne ord og sidetall, lenke til kilden, og hva NBIM faktisk stemte |
| `headline.md` | Hovedtallene på én side |
| `results.md` | Hele utskriften fra alle evalueringsskriptene |
| `dashboard/predictions_main.csv`, `predictions_main_pay.csv` | Dataene til dashbordet |

### Dashbord (Streamlit, på norsk)

```bash
python3 src/run.py                 # lager data/outputs/dashboard/predictions_main*.csv
pip install -r requirements.txt    # streamlit og pandas, bare for dashbordet
streamlit run src/dashboard.py
```

Dashbordet er Maries side fra grenen `marie`, tilpasset denne grenens to beslutningsfiler. Det har to faner:

- **Oversikt:** alle beslutninger med grunner, sitert retningslinje, sannsynlighet, lenke til selskapets dokument og NBIMs faktiske stemme. Du velger mellom to datasett: NBIMs stemmefil for 2026 (kombinert modell) og de amerikanske lønnsstemmene (lønnsmodellen). Du kan filtrere på rute og styrets anbefaling, og bla med Forrige og Neste (også piltastene).
- **Om modellen:** forklaring av modellen og tallene.

Fanen «Ny saksliste» finnes bare på grenen `marie`, fordi den kjører Maries pipeline.

### Historikkmodellen alene

```bash
python3 src/benchmark/model.py --data data/dirty/real_votes.csv
PYTHONPATH=src python3 -m unittest discover -s src/benchmark -p 'test_model.py'
```

Den skriver `src/benchmark/prediksjoner_2026.csv`. Modellen spår om NBIM er **uenig med styret**. Filen inneholder også de faktiske stemmene, så den skal bare brukes til evaluering, aldri som input.

---

## 2. API-nøkler og ny henting av data

**Ingen nøkkel trengs** for `run.py`, testene eller dashbordet. Alle modellsvar ligger i `src/agent/cache/`.

For å spørre modellene om nye forslag, legg `OPENROUTER_API_KEY=...` i en `.env`-fil i rotmappen. `.env` ligger i `.gitignore` og skal aldri committes. Nøkkelen brukes av `rule_check.py`, `judge.py`, `jev_pay.py`, `fetch_board_facts.py`, `fetch_pay_structure.py` og `reader_injection_test.py` når et svar ikke ligger i cachen.

For å bygge SEC-dataene på nytt (ca. en time, krever internett), kjør disse i `src/agent/` i denne rekkefølgen: `fetch_ceo_pay.py`, `fetch_director_roles.py`, `link_companies.py`, `fetch_proxy_pay.py`, `fetch_company_size.py`, `fetch_proxy_text.py`. SEC krever en kontaktadresse i User-Agent. Den leses fra `USER_AGENT` i `startpakke/case1_stemmegivning/hent_npx.py`; bytt den til din egen adresse før du henter.

---

## 3. Slik virker modellen

### Arkitektur

```
Forslag (fra NBIMs stemmefil eller N-PX)
   │
   ├─ 1. Vern: instruksjonslignende tekst, ord ingen tidligere stemmeseddel har brukt,
   │       og proxyer som henvender seg til en automatisk leser sender forslaget til en person
   │
   ├─ 2. Sannsynlighet for at NBIM stemmer mot styret:
   │      • Lønnsstemmer i USA:       pay_model.py       historikk + selskapsfakta fra proxy og SEC (+ Jev som input)
   │      • Styrevalg i USA:          board_rules.py     NBIMs skrevne regler på fakta lest fra proxyen (med sitat)
   │                                                     og SEC-rolledata; en regel virker alene først når NBIM
   │                                                     har fulgt den på to møter på rad
   │      • Tittelen avgjør:          proposal_rules.py  NBIMs regler på forslagets tittel
   │      • Alle andre forslag:       benchmark/model.py bare stemmehistorikk
   │      • NBIMs stemmefil samlet:   combined_model.py  historikkmodellen, mains regler, Jev og Maries andre
   │                                                     modell, vektet med en logistisk regresjon tilpasset på tidligere år
   │
   ├─ 3. Bånd: under 5 % følger agenten styret; over modellens terskel foreslår den mot styret;
   │       imellom avgjør en person
   ├─ 4. Lite informasjon: mangler lønnstall, ukjent selskap, ingen anbefaling fra styret eller
   │       tall som ser feil ut går alltid til en person
   └─ 5. Avstå: der NBIMs tidligere stemmer mot styret i et marked ble avgitt som avståelser,
           skrives forslaget som AVSTÅ
```

NBIMs faktiske stemme kobles på helt til slutt, bare for å regne ut resultatene.

### Valg vi har tatt, og hvorfor

- **Tidssplitt uten lekkasje:** hvert testår tilpasses bare på tidligere år. Proxyer er levert 21–90 dager før møtet, og en test feiler hvis en er levert på eller etter møtedagen. Feltene `nbim_vote`, `nbim_vote_raw`, `against_board`, `rationale_text`, `rationale_section` og `position_paper` fra samme rad går aldri inn i beslutningen.
- **Ingen KI-modell avgir en stemme:** en språkmodell leser dokumentene og returnerer fakta med sitater som sjekkes mot teksten. Jev og en dommermodell gir hver en sannsynlighet som den kombinerte modellen veier sammen med resten.
- **Regler i kode der det går:** NBIMs regler for styrevalg og for forslag der tittelen avgjør er skrevet som kode. Da er de sporbare og kan testes.
- **Agenten handler alene bare med støtte:** et forslag mot styret uten person skjer bare når en regel, et fakta eller NBIMs egen forrige stemme på saken støtter det.

### Skript i `src/agent/`

| Skript | Hva det viser | Resultat på 2026 |
|---|---|---|
| `benchmark/model.py` | Fil A, `real_votes.csv`: alle forslagstyper, 37 land, 1 539 forslag, 66 mot styret. Bare stemmehistorikk | 24 treff og 14 falske alarmer ved 38 flagg; «samme som sist» har 22 og 16 |
| `pay_model.py` | Fil B, Norges Banks N-PX: 1 200 lønnsstemmer i USA, 114 mot styret. Historikk og selskapsfakta fra proxyen | 72 treff og 25 falske alarmer ved 97 flagg; «samme som i fjor» har 42 og 55 |
| `combined_model.py` | Fil A. Én score fra mains historikkmodell og regler pluss Jev og Maries andre modell. Tilpasset på tidligere år, designet på 2022–2025 | 2022–2025: 241 av 401 MOT blant de øverste 10 % (historikkmodellen 220, Maries pipeline 219). 2026: 26 riktige av 36 automatiske forslag, 56 av 66 MOT foreslått eller sett av en person |
| `judge.py` | Styrevalg i USA: en KI-modell får fakta fra proxyen, NBIMs regler og hvor ofte NBIM har fulgt dem, uten navn, og gir en sannsynlighet | Når den sier 50 % eller mer, har den rett 30 av 43 ganger (2021–2025) |
| `country_rules.py` | Styrevalg i Japan og Sør-Korea, med fakta fra EDINET og OpenDART eksportert fra grenen `marie` | I Japan stemte NBIM mot 27 av 141 toppledere og ingen av 739 andre kandidater (til 2025) |
| `policy_watch.py` | Sammenligner NBIMs nettside med retningslinjene fra 2025, regel for regel | 75 av 76 regler er ordrett like. Regel 1.3.1 (styreleder som også er CEO) er mildnet fra «will not» til «may not», og der endret NBIMs stemmer seg i 2026 (0 av 5 mot, etter 28 av 28) |
| `fetch_board_facts.py`, `board_rules.py` | En KI-modell leser hver proxy og registrerer fakta med sjekkede sitater; koden bruker ni av NBIMs regler | Proxy funnet for 98 % av kandidatene. Agenten handler alene på 45 kandidater og har rett på 39 (87 %); «samme som sist» har rett på 36 av 73 |
| `board_reader_check.py` | En sterkere modell leste 16 møter på nytt | Samme svar på 98,2 % av 1 469 fakta |
| `director_rules.py` | NBIMs regler (styreleder som også er CEO; mer enn fem styrer) på SEC-rolledata, uten trening og uten KI | 38 treff og 12 falske alarmer ved 50 flagg; «samme som sist» har 36 og 37 ved 73 |
| `proposal_rules.py` | Forslag der tittelen faller inn under en regel («other business», proxy access, uavhengig styreleder, giftpille …) | NBIM stemte som regelen sier på 79 av 79; 27 av dem er førstegangssaker «samme som sist» ikke kan flagge |
| `position_papers_test.py` | Gir NBIMs tolv posisjonsnotater noe ekstra? | Siteringer ja: samme notat som NBIM på 28 av 31. Prediksjon nei: falske alarmer går fra 6 til 71 |
| `jev_pay.py` | Jev vurderer hver lønnsstemmes tall mot NBIMs lønnsregler; sannsynligheten er lønnsmodellens tolvte input | Agenten alene: 93 flagg, 69 riktige (74 %); 105 av 114 MOT foreslått eller sett |
| `routing.py` | Er sikkerheten ærlig, og hva koster et lavere nivå for manuell vurdering? | Under 5 % tar agenten feil ca. 2 % av gangene |
| `robustness.py`, `paraphrase_test.py`, `reader_injection_test.py` | Instruksjoner skjult i forslagsteksten og i proxyen | Se avsnitt 4 |
| `history_model.py`, `rule_check.py`, `pay_structure_test.py`, `pay_overlap.py`, `data_audit.py` | Eksperimenter som ikke ble tatt i bruk, overlapp mellom filene og datarevisjon | Se `data/outputs/results.md` |
| `export_for_dashboard.py` | Skriver beslutningene i kolonneformatet til dashbordet | `data/outputs/dashboard/predictions_main.csv` |

Mer om hvert skript står i [docs/model-card.md](docs/model-card.md). Den opprinnelige planen står i [docs/case1-architecture.md](docs/case1-architecture.md).

---

## 4. Statistikk

Alle tall er på teståret 2026, på NBIMs faktiske stemmer. Målet er «NBIM stemte mot styret». De to testfilene er separate og summeres ikke. Kilde: [data/outputs/headline.md](data/outputs/headline.md).

### NBIMs stemmefil, alle land: 1 539 forslag, 66 mot styret

| Metode | Sier mot | Riktig | Feil | Presisjon | Recall |
|---|---:|---:|---:|---:|---:|
| Følg alltid styret | 0 | 0 | 0 | – | 0 % |
| Samme som sist i selskapet | 38 | 22 | 16 | 58 % | 33 % |
| **Agenten alene** | **33** | **26** | **7** | **79 %** | **39 %** |

Agenten sender 404 forslag (26 %) til en person, og 30 MOT er blant dem. Altså blir **56 av 66 MOT (85 %)** foreslått av agenten eller lagt fram for en person; 10 slipper gjennom.

### Lønnsstemmer i USA: 1 200 stemmer, 114 mot styret

| Metode | Sier mot | Riktig | Feil | Presisjon | Recall |
|---|---:|---:|---:|---:|---:|
| Følg alltid styret | 0 | 0 | 0 | – | 0 % |
| Samme som i fjor | 97 | 42 | 55 | 43 % | 37 % |
| Mot hvis CEO tjener 25 millioner dollar eller mer | 155 | 83 | 72 | 54 % | 73 % |
| **Agenten alene** | **93** | **69** | **24** | **74 %** | **61 %** |

Agenten sender 371 stemmer (31 %) til en person, og 36 MOT er blant dem. Altså blir **105 av 114 MOT (92 %)** foreslått eller sett; 9 slipper gjennom.

### Hvis en person leser mer

Nivået på 5 % er en innstilling. Det forsiktige nivået ble valgt på 2022–2025 alene: det som ville lagt 90 % av MOT de årene fram for en person.

| Nivå | Til en person | Andel | MOT foreslått eller sett | Slipper gjennom |
|---|---:|---:|---:|---:|
| 5 % (som over) | 404 | 26 % | 56 av 66 (85 %) | 10 |
| 3 % | 610 | 40 % | 64 av 66 (97 %) | 2 |
| Forsiktig nivå, 2,1 % | 751 | 49 % | 65 av 66 (98 %) | 1 |
| 1 % | 1 139 | 74 % | 66 av 66 (100 %) | 0 |

Hovedfunn:

- **Mot baseline:** agenten alene har presisjon 79 % mot 58 % for «samme som sist», og finner flere MOT med færre falske alarmer. «Følg alltid styret» finner ingen.
- **Mindre manuelt arbeid:** bare 26 % av forslagene må vurderes av en person, og 85 % av NBIMs faktiske MOT blir likevel foreslått eller sett.
- **Endret politikk oppdages:** `policy_watch.py` fant den ene regelen NBIM har mildnet, og det er nettopp der stemmene endret seg i 2026.
- **Resistens mot prompt injection:**
  - Vernet flagger alle instruksjonsangrep i forslagsteksten, uten falske alarmer på 66 663 ekte tekster.
  - En omskrevet instruksjon uten triggerord: uten ordsjekken slipper 6 flere MOT gjennom; med den ingen, og alle 66 når en person.
  - Instruksjoner og falske påstander plantet i 20 proxyer: KI-leseren endret 0 av 694 fakta, og en kodesjekk flagger alle 20 plantede proxyer og ingen av 214 ekte.
- **Mot grenen `marie`:** på 2026 var de to systemene omtrent like: med samme lesemengde la hvert av dem 55 av 66 MOT fram for en person, stort sett de samme. Den kombinerte modellen bruker begge.

**Forbehold:**

- **2026 er scoret flere ganger:** lønnsmodellen ble scoret seks ganger på 2026. Alle resultatene står i commit-historikken eller i `results.md`, og hvert valg ble tatt på treningssesongene. Se avsnittet om lekkasje i modellkortet.
- **Lønnsmodellen gjelder bare USA:** ca. 4 % av forslagene og 9 % av MOT i arrangørenes fil. For andre land og forslagstyper finnes det ingen åpen, maskinlesbar kilde til selskapsfakta.
- **Retningslinjene fra 2025 brukes for alle år.**
- **Feil i SEC-tallene:** tre innleveringer tagger lønn tusen eller en million ganger for høyt. Verdier på en milliard dollar eller mer skaleres ned; stemmer med usannsynlige tall går til en person.
- **Jev kan ha sett NBIMs stemmer under trening:** de er offentlige.

---

## 5. Hvordan KI er brukt

Hackathonreglene ber om denne listen.

### KI i systemet

- **Claude Haiku 5.5 (OpenRouter) leser proxyer:** fakta om styret og kandidatene (`fetch_board_facts.py`, 214 møter) og hvordan CEO-lønnen er bygd opp (`fetch_pay_structure.py`, 675 proxyer, vist som bevis og ikke brukt av noen modell). Hvert fakta har et sitat som sjekkes mot teksten. Den samme modellen er dommer for styrevalg i USA (`judge.py`): den får fakta og NBIMs historikk uten navn og gir en sannsynlighet.
- **Claude Sonnet 5.5 (OpenRouter)** leste 16 møter en gang til for å sjekke den første leseren (`board_reader_check.py`).
- **Jev (Typesafe):** de lagrede svarene fra Maries pipeline (`data/evidence/jev_pipeline/`) er input til den kombinerte modellen. Jev kalles også gjennom OpenRouter (`~typesafe/jev-latest`) av `jev_pay.py`.
- **Microsoft-Decision-1 (OpenRouter):** regelsjekken mot retningslinjene (`rule_check.py`) og resistenstesten.
- Alle svar caches i `src/agent/cache/`, slik at alt kan kjøres på nytt uten API-kall.

Ingen KI-modell avgir en stemme. Forslagene i `decisions_2026.csv` kommer fra den kombinerte modellen, lønnsmodellen og NBIMs skrevne regler i kode.

### KI som utviklingsverktøy

En kodeassistent (Claude Code, Anthropic) er brukt til research, kode og evaluering. Mennesker har styrt arbeidet, og alle tall i denne filen kommer fra skript i repoet som kan kjøres på nytt.

For de fullstendige kravene i caset, se [arrangørenes README for case 1](startpakke/case1_stemmegivning/README.md).
