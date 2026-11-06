# Stemmegivningsagenten: NBIM FinTech Hackathon 2026, case 1

Agenten foreslår hvordan NBIM bør stemme på hvert forslag på en generalforsamling: **FOR**, **MOT** eller **AVSTÅ**.

For hvert forslag:

- **Begrunnelse:** den viser til retningslinjen som avgjør, med fakta og NBIMs tidligere stemmer som begrunnelse.
- **Sikkerhet:** den gir en kalibrert sikkerhetsscore.
- **Manuell vurdering:** usikre forslag sendes til en person. Det gjelder alltid MOT, AVSTÅ og avvik fra styret.

Systemet måles på presisjon og recall for MOT, mot en baseline som følger styret. Det er også testet mot instruksjoner som er skjult i forslagsteksten og i selskapets dokumenter (prompt injection).

---

## 1. Kom i gang og kjør demoen

Krever Python 3.10 eller nyere. Kjør alt fra rotmappen i repoet.

```bash
pip install -e .            # installerer pakken nbim_vote og avhengighetene (pyproject.toml)
pip install -e ".[dev]"     # valgfritt: pytest og playwright for testene
```

### Demo med Dashbord (Streamlit, på norsk)

```bash
python -m nbim_vote.dashboard_data          # én gang: lager data/outputs/dashboard/predictions_*.csv (ca. 2 min, ingen API-kall)
streamlit run src/nbim_vote/dashboard.py
```

Dashbordet har tre faner:

- **Oversikt:** alle forslag fra 2022 til 2026, med anbefalingene modellen ville gitt på møtedagen. Du kan filtrere og sortere på blant annet dato, manuell vurdering og sikkerhet. Detaljvisningen viser:
  - begrunnelsen og fakta, med avsnittet fra dokumentet når du holder musepekeren over linjen;
  - lenker til kildedokumentene;
  - knappene Forrige og Neste, som også styres med piltastene.
- **Ny saksliste:** den samme demoen som i terminalen.
- **Om modellen:** forklaring av modellen og tallene.

### Demo i terminalen (ingen API-nøkkel trengs)

```bash
python -m nbim_vote.demo data/demo/hp_2026-04-16.txt --company "HP Inc." --date 2026-04-16
```

Demoen bruker ikke Jev som standard og kaller ingen API. Den tar rundt 25 sekunder, mest fordi modellene trenes på all historikk før møtet.

Andre varianter:

```bash
# Lim inn en saksliste fra standard input
python -m nbim_vote.demo - --company "HP Inc." --date 2026-04-16 < saksliste.txt

# Spør også Jev (krever TYPESAFE_API_KEY, se avsnitt 2)
python -m nbim_vote.demo data/demo/hp_2026-04-16.txt --company "HP Inc." --date 2026-04-16 --jev

# Kjør Jev-løypa med en stubb som følger styret (ingen API-kall)
python -m nbim_vote.demo data/demo/hp_2026-04-16.txt --company "HP Inc." --date 2026-04-16 --jev --dry-run
```

**Format for sakslisten:**

- **Én linje per forslag:** skriv forslaget slik det står på stemmeseddelen. Linjer som begynner med `#` hoppes over.
- **Aksjonærforslag:** `SH: <tekst>` markerer et aksjonærforslag. Da antas det at styret anbefaler MOT.
- **Styrets anbefaling:** `[board: FOR]` eller `[board: MOT]` sist på linjen setter den.

Demoen gir bare anbefalinger for møter der vi har selskapets dokumenter i dataene. Det gjelder SEC for USA, EDINET for Japan og DART for Sør-Korea. For andre møter sier demoen fra og stopper, i stedet for å gjette.

### Tester

```bash
python -m pytest            # 76 tester, ca. 2 min, ingen API-kall
```

### Andre kommandoer

| Kommando | Hva den gjør |
|---|---|
| `python -m nbim_vote.report_results` | Skriver `data/outputs/jev_results.md` fra lagrede Jev-svar (ingen API-kall) |
| `python -m nbim_vote.report_results --main-dir <checkout av main>` | Sammenligner også med main-grenen (`comparison_with_main.md`) |
| `python -m nbim_vote.jev_mvp --year 2025 --level history` | Kjører pipelinen for et år (Jev-svar leses fra cachen) |
| `python -m nbim_vote.jev_mvp --year 2025 --n 100 --level history --resistance --enrich` | Resistenstest (injection) |
| `python -m nbim_vote.fit_combination --years 2021 2022 2023 2024 2025` | Tilpasser den kombinerte scoren (`data/combination.json`) |
| `python -m nbim_vote.fetch_edinet index` / `download`, `python -m nbim_vote.fetch_dart`, `python -m nbim_vote.fetch_sec_votes` | Henter selskapsdokumenter på nytt |

---

## 2. API-nøkler

Kopier `.env.example` til `.env` og fyll inn de nøklene du trenger. `.env` ligger i `.gitignore` og skal aldri committes.

| Nøkkel | Trengs til | Hvor du får den |
|---|---|---|
| `TYPESAFE_API_KEY` | Jev: `--jev` i demoen, og `jev_mvp.py` på forslag som ikke ligger i cachen | https://console.typesafe.ai/keys |
| `EDINET_API_KEY` | Bare for å hente nye japanske dokumenter (`fetch_edinet`) | Gratis på https://api.edinet-fsa.go.jp |
| `OPENDART_API_KEY` | Bare for å hente nye koreanske dokumenter (`fetch_dart`) | Gratis på https://opendart.fss.or.kr |

**Ingen nøkkel trengs** for demoen, dashbordet, testene eller resultatrapporten. Alle Jev-svar fra evalueringen ligger lagret i `data/jev_runs/cache.jsonl`, og selskapsdokumentene ligger i `data/`.

**SEC-skriptene** (`fetch_sec_votes`, `hent_npx`, `hent_def14a`) bruker ingen nøkkel. SEC krever likevel en kontaktadresse i User-Agent, og den settes i `USER_AGENT` i `src/nbim_vote/hent_npx.py`. Bytt den til din egen adresse før du henter.

---

## 3. Slik virker modellen

### Arkitektur

```
Saksliste / stemmeseddel
   │
   ├─ 1. Forslagstype fra teksten (classify.py, regelbasert, 96 % enig med arrangørens typer)
   ├─ 2. Instruksjonsfilter (instructions.py): fjerner og flagger «ignorer retningslinjene …»
   ├─ 3. Retningslinjene som gjaldt på møtedatoen (data/guidelines, utgavene 2016–2025)
   ├─ 4. Kontekst fra før møtet:
   │      • NBIMs tidligere stemmer og begrunnelser på samme sak i samme selskap
   │      • selskapsfakta fra dokumenter levert før møtet (company_facts.py):
   │          USA: df14a proxy (kandidatens rolle, uavhengighet, styreleder), fjorårets stemmeresultat (8-K 5.07), CEO-lønn
   │          Japan: EDINET-årsrapporter (rolle, uavhengige i styret)
   │          Sør-Korea: DART (styrets sammensetning, om CEO også leder styret)
   │
   ├─ 5a. Triagemodell (triage_model.py): gradient boosting som gir p(NBIM stemmer MOT)
   ├─ 5b. Jev (valgfri, jev_mvp.py): språkmodell som leser forslag, retningslinjer og kontekst, og stemmer
   ├─ 5c. NBIMs regler for styrevalg, skrevet som kode (director_rules.py), med tillitsmonitor
   ├─ 5d. Lønnsmodellen fra main for amerikanske say-on-pay-forslag (pay_model.py), tilpasset bare på tidligere år
   │
   ├─ 6. Kombinert score (logistisk, combination.json), rangert mot de siste 12 månedene
   ├─ 7. Beslutning: MOT / AVSTÅ / styrets anbefaling, pluss om forslaget skal til en person
   ├─ 8. Sitering (citations.py): regel i kode → NBIMs tidligere begrunnelse → samme selskap → tekstmodell
   ├─ 9. Kalibrert sikkerhet (confidence.py): andelen riktige i tidligere år, per stemme og scoreintervall
   └─ 10. Forklaring (explain.py): grunner, retningslinjetekst, avsnitt fra dokumentene og lenker
```

Når modellen anbefaler **MOT**, skjer det på én av to måter:

- Jev sier MOT og triagemodellen ligger over terskelen.
- En av NBIMs regler for styrevalg slår til på verifiserte fakta, og regelen har ikke bommet nylig.
- Lønnsmodellen fra main ligger over sin egen terskel på et amerikansk say-on-pay-forslag. Over 5 % går forslaget til en person.

Modellen anbefaler **AVSTÅ** når det er Jevs førstevalg. Ellers følger den styret. Et unntak: når styret anbefaler MOT, men både Jev og triagemodellen mener NBIM ville stemt for, blir anbefalingen FOR. *I dataene våre, så skjer avstå nært aldri.*

**Disse går alltid til en person:** alle anbefalinger om MOT og AVSTÅ, og alle avvik fra styret. Det samme gjelder forslag med lav score. En forslagstype slipper manuell vurdering bare når NBIM ikke har stemt mot noen av minst 100 slike forslag tidligere.

### Valg vi har tatt, og hvorfor

- **Walk-forward uten lekkasje:** hvert testår tilpasses bare på tidligere år. Selskapsfakta og utdrag fra dokumenter tas bare fra dokumenter levert *før* møtet. Testene sjekker blant annet at fremtidige begrunnelser ikke lekker inn i forklaringene.
- **Jev er valgfri:**
  - Uten Jev går F1 ned fra 53,9 % til 50,3 %, og andelen til manuell vurdering går opp fra 39,9 % til 46,2 %.
  - Siteringene fra kode treffer *bedre* enn Jevs: 77,0 % mot 71,9 % riktig avsnitt.
  - Uten Jev trengs altså ingen API, og systemet virker fortsatt.
- **Regler i kode der det går:** NBIMs regler for styrevalg er skrevet som kode i stedet for å overlates til språkmodellen. Da er de sporbare og kan testes. Tillitsmonitoren sørger for at en regel som har bommet ikke styrer beslutningen før den har truffet igjen.
- **Forklaringer som kan etterprøves:** hver grunn peker til avsnittet den bygger på i et konkret dokument (proxy, 8-K, EDINET, DART eller NBIMs tidligere begrunnelse), med lenke.

### Moduler i `src/nbim_vote/`

| Modul | Rolle |
|---|---|
| `jev_mvp.py` | Kjernen: data, retningslinjer, Jev-klient med cache, beslutning, evaluering og resistenstest |
| `triage_model.py` | Gradient boosting-modellen for p(MOT) |
| `director_rules.py` | NBIMs regler for styrevalg som kode, med tillitsmonitor |
| `pay_model.py` | Mains lønnsmodell (logistisk, på NBIMs N-PX-stemmer om lederlønn), walk-forward per år |
| `company_facts.py`, `japan_facts.py` | Selskapsfakta fra SEC, EDINET og DART |
| `citations.py` | Hvilken retningslinje som siteres, uten Jev |
| `confidence.py` | Kalibrert sikkerhet |
| `explain.py` | Begrunnelser, avsnitt og lenker |
| `against_board.py` | Signaler for når «MOT» og «mot styret» er forskjellige ting |
| `instructions.py` | Instruksjonsfilter mot prompt injection |
| `classify.py` | Forslagstype fra tekst |
| `demo.py`, `dashboard.py`, `dashboard_data.py` | Demo i terminal og Streamlit |
| `report_results.py`, `evaluate_jev.py`, `fit_combination.py`, `export_components.py` | Evaluering, tilpasning og sammenligning med main |
| `fetch_*.py`, `hent_*.py` | Henting av data |

---

## 4. Statistikk

Alle tall er walk-forward på NBIMs faktiske stemmer. Målet er «NBIM stemte MOT». Kilde: [data/outputs/jev_results.md](data/outputs/jev_results.md).

| År | Forslag | MOT | Baseline F1 (følg styret) | Presisjon | Recall | **F1** | **Til manuell vurdering** | MOT som når en person |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2022 | 1772 | 112 | 24,8 % | 56,1 % | 41,1 % | **47,4 %** | **37,1 %** | 88,4 % |
| 2023 | 1761 | 100 | 36,2 % | 71,2 % | 52,0 % | **60,1 %** | **42,4 %** | 84,0 % |
| 2024 | 1883 | 98 | 17,1 % | 70,7 % | 41,8 % | **52,6 %** | **42,0 %** | 95,9 % |
| 2025 | 1909 | 112 | 20,2 % | 76,8 % | 38,4 % | **51,2 %** | **37,1 %** | 86,6 % |
| 2026 | 1539 | 66 | 20,0 % | 64,8 % | 53,0 % | **58,3 %** | **41,1 %** | 95,5 % |
| **Snitt** | | | ~23,7 % | 67,9 % | 45,3 % | **53,9 %** | **39,9 %** | 90,1 % |

Hovedfunn:

- **Mot baseline:** F1 på MOT er omtrent 2,3 ganger så høy som for en baseline som følger styret (53,9 % mot ca. 24 %).
- **Mindre manuelt arbeid:** bare 39,9 % av forslagene må vurderes av en person, i stedet for alle. Det er mer enn en halvering. Likevel når 90 % av NBIMs faktiske MOT-stemmer en person.
- **Siteringer:** av MOT-stemmene der NBIM oppga et avsnitt i retningslinjene, sier koden hvilket avsnitt i 77 % av tilfellene.
- **Resistens mot prompt injection:**
  - Eksplisitte instruksjoner i forslagsteksten blir fanget og fjernet i 100 % av tilfellene, og ingen stemmer endret seg.
  - Jev alene følger heller ikke omskrevne instruksjoner.
  - Svakheten er at omskrevet tekst kan bryte koblingen til historikken for samme sak. Det kostet 4 av 6 anbefalte MOT i testutvalget, men alle faktiske MOT nådde likevel en person.
  - Tiltak (ikke målt ennå): en sak regnes nå som samme sak når teksten er den gamle teksten pluss en ekstra setning (`same_item` i `jev_mvp.py`). På de rene dataene endrer det ingen kobling, så tallene og Jevs lagrede svar er uendret. Effekten under angrep krever nye Jev-kall og er ikke kjørt.
  - Se `data/outputs/resistance_*.md`.
- **Lønnsmodellen fra main:**
  - På alle NBIMs say-on-pay-stemmer i N-PX, walk-forward: average precision 0,58 (2024), 0,68 (2025) og 0,70 (2026), mot 0,11–0,22 for «samme som i fjor».
  - I denne grenens data finner den 4 av 6 MOT i 2024 (mot 0 før) og 3 av 4 i 2025 (mot 2), uten mer manuell vurdering. Snittet F1 går fra 54,1 % til 54,8 % på denne maskinen.
  - Det er bare 10 MOT på lønn i 2024–2025 i dataene her, så N-PX-tallene er den egentlige testen. Se avsnittet om lønnsmodellen i `jev_results.md`.
  - Forskjeller fra main: tilpasset bare på møter før 1. januar i året som scores, og ingen SEC API-tall rapportert etter møtet.
- **Mot main-grenen:** på de samme forslagene er denne grenen signifikant bedre enn mains historikkmodell på MOT (+0,128 i average precision). Mot mains kombinerte modell er det jevnt: +0,03 på MOT, som ikke er signifikant. På målet «mot styret» er main signifikant bedre (+0,06). Se [data/outputs/comparison_with_main.md](data/outputs/comparison_with_main.md).

**Forbehold:**

- **2026 er ikke et rent holdout-år:** designet ble justert etter at 2026 var kjørt. Den første, rene kjøringen ga F1 53,4 %, men hele 73,4 % til manuell vurdering.
- **Siteringene for 2022–2024 er optimistiske:** avsnittene Jev fikk velge mellom ble satt opp ut fra NBIMs siteringer før 2025.
- **Jev kan ha sett NBIMs stemmer under trening:** de er offentlige. Tallene er like i alle år, så det er ingen tegn til at det har mye å si, men det kan ikke utelukkes.
- **Noen valg er tatt med testårene i sikte (design-lekkasje):** selve tilpasningen er walk-forward, men disse valgene er ikke det:
  - Regelen for forslag der styret anbefaler MOT ble valgt ut fra 2021–2025, som overlapper testårene. Den påvirker 14–27 forslag i året.
  - Reglene for styrevalg bygger på mains liste, som ifølge main ble laget etter å ha sett alle år.
  - Faste parametre ble satt mens vi så på resultatene, også fra testårene: målrecall 90 % (`TARGET_RECALL`), regularisering (`C=0.3`), minst 100 forslag for å slippe manuell vurdering, tillitsmonitorens `TRUST_AFTER` og tidsvinduene for selskapsdokumenter (400 og 45 dager).
- **2021–2023 er ikke garantert urørte:** Jev ble kjørt med flere varianter av input på disse årene (v4–v7 for 2021 og 2022, v5–v7 for 2023). Git-historikken kan ikke vise at designet var fryst før resultatene ble sett. De er likevel de reneste årene.
- **Tallene er laget i et annet miljø enn dette:** med Python 3.14, scikit-learn 1.9.1 og numpy 2.5.1 gir den samme koden snittet F1 54,1 % og 40,7 % til manuell vurdering, mot 53,9 % og 39,9 % i tabellen over. Tallene per år avviker med opptil 3 prosentpoeng. Versjonene er ikke låst i `pyproject.toml`.

---

## 5. Hvordan KI er brukt

KI er brukt på to måter: som en del av selve systemet, og som verktøy for å utvikle det.

### KI i systemet

- **Jev (Typesafe, `jev-1.14.0`) er en språkmodell.** Den leser forslaget, retningslinjene som gjaldt, NBIMs tidligere stemmer og selskapsfaktaene. Svaret er en strukturert sannsynlighet for FOR, MOT og AVSTÅ, og hvilken retningslinje som passer best.
  - **Data, ikke instruksjoner:** all tekst fra dokumentene går til Jev som data, ikke som instruksjoner, og kjente instruksjonsmønstre fjernes først.
  - **Cache:** svarene caches, slik at evalueringen kan kjøres på nytt uten API-kall.
- **Maskinlæring:**
  - triagemodellen (gradient boosting);
  - den kombinerte scoren (logistisk regresjon);
  - tekstmodellen for siteringer (TF-IDF + logistisk regresjon).
  - Alle trenes bare på tidligere år.
- **Regler og kode:** reglene for styrevalg, kalibreringen og forklaringene er bevisst *ikke* språkmodell. Da blir avgjørelsene sporbare, de kan testes, og de virker uten API.

### KI som utviklingsverktøy

En kodeassistent (Claude Code) er brukt underveis til dette:

- **Gjennomgang av koden:** lete etter datalekkasje (for eksempel dokumenter levert etter møtet og fremtidige begrunnelser), feil, og punkter som ikke svarte på caset.
- **Rettelser med tester:** fikse funnene og skrive tester for dem. Testsuiten har nå 76 tester.
- **Evaluering:**
  - resistenstestene;
  - en mer rettferdig sammenligning med main: samme forslag, lik vurderingsinnsats og bootstrap over møter;
  - analysen med og uten Jev.
- **Ny funksjonalitet:** regler for styrevalg og siteringer uten Jev, kalibrert sikkerhet, forklaringer med lenker til avsnittene i dokumentene, terminaldemoen og Streamlit-dashbordet.
- **Struktur:** ordne koden som en pakke under `src/`.

Mennesker har styrt arbeidet. Forslagene fra assistenten er sjekket mot testene og mot de målte resultatene, ikke bare tatt for god fisk. Alle tall i denne filen kommer fra skript i repoet som kan kjøres på nytt.
