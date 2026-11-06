"""Stemmegivningsagenten: dashboard (Streamlit). The interface is in Norwegian.

Copied from branch marie (src/nbim_vote/dashboard.py at commit 1608464), where Marie built it, and
adapted to show the decisions of the model in this branch. Her branch is unchanged. What differs:
the files it reads, the "Ny saksliste" tab is left out (it runs her pipeline, which is not in this
branch), "sikkerhet" is the model's probability of the suggested vote, and the last key figure
counts against-votes the tool suggests on its own as well as those in the review pile.

Run from the repository root (the pipeline itself needs nothing beyond Python; the dashboard needs
two packages):
    python3 src/run.py                      # writes data/outputs/dashboard/predictions_main*.csv
    pip install streamlit pandas
    streamlit run src/dashboard.py

Tabs
    Oversikt        every proposal of the test year: filter, sort, and see why
    Om modellen     what the numbers mean
"""

import json
import re
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "outputs" / "dashboard"
FILES = {"Stemmefilen, alle land (kombinert modell)": DATA / "predictions_main.csv",
         "Lønnsavstemninger USA (lønnsmodell)": DATA / "predictions_main_pay.csv"}
VOTES = ROOT / "data" / "dirty" / "real_votes.csv"

ROUTE = {"human_review": "Manuell vurdering", "automatic": "Automatisk"}
SOURCE = {
    "rule in code": "Regel i kode", "NBIM's earlier reason, same item": "NBIMs tidligere begrunnelse, samme sak",
    "NBIM's earlier reason, same company": "NBIMs tidligere begrunnelse, samme selskap", "text model": "Tekstmodell",
    "text match": "Tekstsamsvar", "voting principle": "Stemmeprinsipp (støtt styret)", "Jev": "Jev", "": "–",
}
TYPE = {
    "DIRECTOR_ELECTION": "Styrevalg", "AUDITOR": "Revisor", "FIN_STATEMENTS": "Årsregnskap", "DISCHARGE": "Ansvarsfrihet",
    "DIVIDEND": "Utbytte", "OTHER_MGMT": "Annet fra ledelsen", "SAY_ON_PAY": "Lederlønn", "SAY_ON_PAY_FREQ": "Hyppighet lønnsavstemning",
    "ROUTINE": "Rutinesak", "DIRECTOR_PAY": "Styrehonorar", "EQUITY_PLAN": "Aksjeprogram", "ARTICLES": "Vedtekter",
    "SHARE_ISSUANCE": "Aksjeutstedelse", "SHARE_REPURCHASE": "Tilbakekjøp", "RPT": "Nærstående transaksjoner",
    "OTHER_BUSINESS": "Eventuelt", "SHP_OTHER": "Aksjonærforslag, annet", "MERGER": "Fusjon/oppkjøp",
    "SHP_SUSTAINABILITY": "Aksjonærforslag, bærekraft", "SHP_GOVERNANCE": "Aksjonærforslag, styring",
    "ANTITAKEOVER": "Oppkjøpsvern", "SHP_INDEP_CHAIR": "Aksjonærforslag, uavhengig styreleder", "DUAL_CLASS": "Aksjeklasser",
    "CLASSIFY_BOARD": "Styrestruktur",
}
SORT = {
    "Møtedato": ("meeting_date", False), "Manuell vurdering først": ("_review_first", True),
    "Sikkerhet": ("confidence", False), "Risiko for MOT": ("p_combined", False), "Selskap": ("company", True),
    "Forslagstype": ("Type", True), "Land": ("country", True), "Anbefaling": ("vote", True),
}

# Colours: explicit text and background, so they read in both light and dark themes.
VOTE_STYLE = {"MOT": ("#f8d7da", "#842029"), "AVSTÅ": ("#fff3cd", "#664d03"), "FOR": ("#d1e7dd", "#0f5132")}
HIGH, MEDIUM = 0.90, 0.70  # confidence bands
DEFAULT_MIN_CONFIDENCE = 0.0  # nothing is hidden: an unsure suggestion against the board is what a person should see
BADGE = {"MOT": "red", "AVSTÅ": "orange", "FOR": "green"}

st.set_page_config(page_title="Stemmegivningsagenten", page_icon="🗳️", layout="wide")
# Key figures: scale with the window and wrap instead of being cut off with "…" in narrow boxes.
st.html("""<style>
[data-testid="stMetricValue"] { font-size: clamp(1.25rem, 2.1vw, 2.25rem); }
[data-testid="stMetricValue"] *, [data-testid="stMetricDelta"], [data-testid="stMetricDelta"] *,
[data-testid="stMetricLabel"] * {
  white-space: normal !important; overflow: visible !important; text-overflow: clip !important; }
</style>""")


def confidence_band(c):
    return ("høy", "green", VOTE_STYLE["FOR"]) if c >= HIGH else \
           ("middels", "orange", VOTE_STYLE["AVSTÅ"]) if c >= MEDIUM else ("lav", "red", VOTE_STYLE["MOT"])


def styled(table):
    """The recommendation highlighted, and confidence coloured by band."""
    def vote(v):
        bg, fg = VOTE_STYLE.get(v, ("", ""))
        return f"background-color: {bg}; color: {fg}; font-weight: 700" if bg else ""

    def conf(c):
        bg, fg = confidence_band(c)[2]
        return f"background-color: {bg}; color: {fg}; font-weight: 600"

    return (table.style.map(vote, subset=["Anbefaling"]).map(conf, subset=["Sikkerhet"])
            .format({"Sikkerhet": pct}))


LEGEND = (f"**Anbefaling:** :red-background[MOT] · :orange-background[AVSTÅ] · :green-background[FOR] — "
          f"**Sikkerhet:** :green-background[høy ≥ {HIGH:.0%}] · :orange-background[middels {MEDIUM:.0%}–{HIGH:.0%}] · "
          f":red-background[lav < {MEDIUM:.0%}]").replace("%", " %")


# ---------------------------------------------------------------- data

@st.cache_data(show_spinner=False)
def load(path, modified=None):
    """The predictions file; `modified` (its change time) makes a running server re-read it after a rebuild."""
    df = pd.read_csv(path, dtype={"meeting_id": str, "item_no": str}, keep_default_na=False)
    for c in ("confidence", "p_combined"):
        df[c] = pd.to_numeric(df[c])
    for c in ("p_mot", "p_model"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["Type"] = df["proposal_type"].map(TYPE).fillna(df["proposal_type"])
    df["Rute"] = df["route"].map(ROUTE)
    df["Kilde for sitering"] = df["citation_source"].map(SOURCE).fillna(df["citation_source"])
    df["Årsak til vurdering"] = df.apply(review_why, axis=1)
    df["_review_first"] = (df["route"] != "human_review").astype(int)
    df["Riktig"] = df.apply(lambda r: r["nbim_vote"] == r["vote"], axis=1)
    return df


def review_why(r):
    """Why a proposal goes to a person, in words."""
    out = []
    codes = r["review_reason"].split(";") if r["review_reason"] else []
    if "review_band" in codes:
        if r["vote"] != r["mgmt_rec"]:
            out.append("Avviker fra styret")
        elif r["vote"] in ("MOT", "AVSTÅ"):
            out.append(f"Anbefaler {r['vote']}")
        else:
            out.append("Høy risiko for MOT")
    names = {"rule_needs_person": "Regel slo til, ikke betrodd ennå", "instruction_in_text": "Mistenkelig instruksjon i teksten",
             "no_citation": "Ingen retningslinje funnet", "low_confidence": "Lav sikkerhet"}
    out += [names[c] for c in codes if c in names]
    return "; ".join(out) if out else "–"


def metrics(df):
    """Precision and recall on MOT votes, against NBIM's actual votes."""
    pred, actual = df["vote"] == "MOT", df["nbim_vote"] == "MOT"
    tp, fp, fn = int((pred & actual).sum()), int((pred & ~actual).sum()), int((~pred & actual).sum())
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    reached = int((actual & ((df["route"] == "human_review") | pred)).sum())
    return p, r, (2 * p * r / (p + r) if p + r else 0.0), reached, int(actual.sum())


def pct(x):
    return f"{100 * x:.1f} %".replace(".", ",")


@st.cache_data(show_spinner=False)
def votes_file():
    """NBIM's published votes, for the history behind each recommendation (earlier meetings only)."""
    return pd.read_csv(VOTES, dtype=str, keep_default_na=False, encoding="utf-8-sig")


def earlier_votes(company_id, company, date):
    """NBIM's votes at this company at meetings before `date`, newest first. These are inputs, not the answer."""
    v = votes_file()
    mine = v[(v["company_id"] == str(company_id)) if company_id and not str(company_id).startswith("new:") else
             (v["company"].str.lower() == str(company).lower())]
    mine = mine[(mine["meeting_date"] < date) & mine["nbim_vote"].isin(["FOR", "MOT", "AVSTÅ"])]
    return pd.DataFrame({"Dato": mine["meeting_date"], "Forslag": mine["proposal_text"], "Styret": mine["mgmt_rec"],
                         "NBIM stemte": mine["nbim_vote"], "Seksjon": mine["rationale_section"],
                         "NBIMs begrunnelse": mine["rationale_text"]}).sort_values("Dato", ascending=False)


def show_documents(r, docs):
    """The documents the recommendation rests on, each filed before the meeting, and NBIM's earlier votes."""
    st.markdown("**Dokumenter brukt som grunnlag** (levert før møtet)")
    lines = []
    for d in docs:
        name = f"[{d['label']}]({d['url']})" if d["url"] else d["label"]
        lines.append(f"- {name} · levert {d['filed']} · {d['about']}")
    edition = r.get("guideline_edition") or ""
    if edition:
        lines.append(f"- NBIMs stemmeretningslinjer (Global Voting Guidelines), {edition}-utgaven"
                     + (f": punkt {r['citation']}" if r.get("citation") and r["citation"] != "P.1" else ""))
    if not docs:
        lines.insert(0, "- Ingen selskapsdokumenter i datagrunnlaget for dette landet (vi har SEC for USA, EDINET for "
                        "Japan og DART for Sør-Korea).")
    st.markdown("\n".join(lines))
    if any(d["url"] and "edinet-fsa" in d["url"] for d in docs):
        st.caption("EDINET-lenkene åpner EDINETs offentlige dokumentvisning etter dokument-ID. Adressen virker, men er ikke "
                   "dokumentert av EDINET.")
    past = earlier_votes(r.get("company_id"), r["company"], r["meeting_date"])
    with st.expander(f"NBIMs tidligere stemmer i selskapet ({len(past)} forslag før {r['meeting_date']})"):
        if len(past):
            st.dataframe(past, hide_index=True, width="stretch", height=260,
                         column_config={"Forslag": st.column_config.TextColumn("Forslag", width="large"),
                                        "NBIMs begrunnelse": st.column_config.TextColumn("NBIMs begrunnelse", width="large")})
        else:
            st.caption("Ingen tidligere stemmer i datagrunnlaget.")


HOVER_CHARS = 900  # browsers cut very long hover texts


def md_escape(text):
    """Text shown literally in markdown (no stray emphasis, links or HTML from the documents)."""
    return re.sub(r"([\\`*_{}\[\]<>#|~$])", r"\\\1", " ".join(str(text).split()))


def passage_kind(found):
    """document, guideline or history. Older data has no kind: tell it from the source."""
    if found.get("kind"):
        return found["kind"]
    source = found.get("source", "")
    if source.startswith("NBIMs stemmeretningslinjer"):
        return "guideline"
    if source.startswith(("NBIMs publiserte begrunnelse", "NBIMs stemme")):
        return "history"
    return "document"


def show_reasons(reasons, passages):
    """The reason lines, with what each rests on, shown by kind:
        🔎 a passage in a company document: hover help (the icon beside the line) with the source, the passage and a
           link to the document, at the quoted sentence where the browser supports text links
        🗳️ NBIM's own published rationale at an earlier meeting: hover help with the text, no document link
        📘 NBIM's voting guidelines: the rule's own words shown under the line, not as a link to a document
    Plain markdown, no HTML: it shows at once and in every browser."""
    kinds = set()
    for line in reasons:
        found = passages.get(line)
        if not found:
            st.markdown(f"- {md_escape(line)}")
            continue
        kind = passage_kind(found)
        kinds.add(kind)
        shown = re.sub(r' \(proxy: ".*?"\)', "", line)  # the quote is in the hover text instead
        passage = found["passage"] if len(found["passage"]) <= HOVER_CHARS else found["passage"][:HOVER_CHARS] + " …"
        if kind == "guideline":
            st.markdown(f"- {md_escape(shown)} 📘")
            st.caption(f"📘 {md_escape(found['source'])}: «{md_escape(passage)}»")
        elif kind == "history":
            st.markdown(f"- {md_escape(shown)} 🗳️", help=f"**{md_escape(found['source'])}**\n\n> {md_escape(passage)}")
        else:
            tip = f"**{md_escape(found['source'])}**\n\n> {md_escape(passage)}"
            if found.get("url"):
                tip += f"\n\n[Åpne dokumentet ↗]({found['url']})"
            st.markdown(f"- {md_escape(shown)} 🔎", help=tip)
    legend = []
    if "document" in kinds:
        legend.append("🔎 avsnitt i et selskapsdokument: hold musepekeren over ⓘ for utdraget og lenke til dokumentet")
    if "history" in kinds:
        legend.append("🗳️ NBIMs egen begrunnelse fra et tidligere møte: hold over ⓘ for teksten")
    if "guideline" in kinds:
        legend.append("📘 retningslinjen: ordlyden står under linjen")
    if legend:
        st.caption(" · ".join(legend) + ". For Japan og Sør-Korea er utdragene felt lest fra rapportene, ikke løpende tekst.")
    else:
        st.caption("Ingen av linjene over bygger på et tekstavsnitt vi har (for eksempel bare strukturerte felt eller "
                   "stemmehistorikk uten begrunnelse).")


def navigation_position(view):
    """The row the details show. Reset to the first row when the selection (filters, sorting) changes; follow a
    new click in the table; otherwise keep the position Forrige/Neste moved to."""
    s = st.session_state
    signature = hash(tuple(view["meeting_id"] + "-" + view["item_no"]))
    if s.get("nav_signature") != signature:
        s["nav_signature"], s["nav_pos"], s["nav_last_pick"] = signature, 0, None
    table_state = s.get("table")
    picked = list(table_state["selection"]["rows"]) if table_state and table_state.get("selection") else []
    if picked and picked != s.get("nav_last_pick"):
        s["nav_pos"] = picked[0]
    s["nav_last_pick"] = picked
    s["nav_pos"] = min(max(int(s.get("nav_pos", 0)), 0), max(len(view) - 1, 0))
    return s["nav_pos"]


def move(step, n):
    """Forrige/Neste: one row up or down, within the selection."""
    st.session_state["nav_pos"] = min(max(st.session_state.get("nav_pos", 0) + step, 0), n - 1)


def show_details(r, fasit, docs=None):
    """One proposal: recommendation, confidence, why, guideline, documents, and (optionally) what NBIM did."""
    if docs is None:
        docs = json.loads(r.get("documents") or "[]")
    st.markdown(f"#### {r['company']} · {r['meeting_date']}")
    main = docs[0] if docs and docs[0]["url"] else None
    st.markdown(f"**Forslag:** [{r['proposal_text']}]({main['url']}) ↗" if main else f"**Forslag:** {r['proposal_text']}")
    if main:
        st.caption(f"Lenken åpner {main['label'].lower()}, levert {main['filed']}.")
    band, colour, _ = confidence_band(float(r["confidence"]))
    st.markdown(f"**Anbefaling:** :{BADGE.get(r['vote'], 'gray')}-background[**{r['vote']}**] · "
                f"**Sikkerhet:** :{colour}-background[{band} ({pct(float(r['confidence']))})]")
    if r.get("confidence_basis"):
        st.caption(f"Sikkerheten bygger på: {r['confidence_basis']}.")
    c = st.columns(5)
    c[0].metric("Anbefaling", r["vote"])
    c[1].metric("Sikkerhet", pct(r["confidence"]), help="Modellens sannsynlighet for den anbefalte stemmen")
    c[2].metric("Risiko for MOT", pct(r["p_combined"]), help="Modellens sannsynlighet for at NBIM stemmer mot styrets anbefaling")
    c[3].metric("Modell nr. 2 (Marie)", "–" if pd.isna(r.get("p_model")) or r.get("p_model") == "" else pct(float(r["p_model"])))
    c[4].metric("Jev", "–" if pd.isna(r.get("p_mot")) or r.get("p_mot") == "" else pct(float(r["p_mot"])))
    st.markdown(f"**Styrets anbefaling:** {r['mgmt_rec']} · **Type:** {TYPE.get(r['proposal_type'], r['proposal_type'])}"
                f" · **Rute:** {ROUTE.get(r['route'], r['route'])}"
                + (f" ({review_why(r)})" if r["route"] == "human_review" else ""))
    st.markdown("**Retningslinje**")
    st.info(r["guideline_text"] or "Ingen retningslinje funnet: en person avgjør.")
    st.caption(f"Kilde for siteringen: {SOURCE.get(r['citation_source'], r['citation_source'])}")
    reasons = [x for x in str(r["reasons"]).split(" | ") if x]
    if reasons:
        st.markdown("**Relevant informasjon og retningslinjer** (fakta og NBIMs historikk, fra datakildene)")
        passages = r.get("passages") or {}
        if isinstance(passages, str):
            passages = json.loads(passages or "{}")
        show_reasons(reasons, passages)
    show_documents(r, docs)
    if fasit and r.get("nbim_vote"):
        ok = "✅ samme som anbefalingen" if r["nbim_vote"] == r["vote"] else "❌ ulik anbefalingen"
        st.markdown(f"**Fasit – NBIM stemte:** {r['nbim_vote']} ({ok})")
        if r.get("rationale_text"):
            st.caption(f"NBIMs begrunnelse ({r.get('rationale_section') or 'uten seksjon'}): {r['rationale_text']}")


ABOUT = """
- **Anbefaling:** FOR, MOT eller AVSTÅ. Uten grunn til å avvike følger verktøyet styrets anbefaling.
- **Risiko for MOT:** modellens sannsynlighet for at NBIM stemmer mot styrets anbefaling. Vektene er tilpasset på
  tidligere år.
- **Sikkerhet:** modellens sannsynlighet for den anbefalte stemmen: risikoen når anbefalingen går mot styret, ellers
  1 minus risikoen.
- **Farger:** anbefalingen er markert (rød MOT, gul AVSTÅ, grønn FOR). Sikkerheten er grønn fra 90 %, gul fra 70 %
  og rød under 70 %.
- **Automatisk:** verktøyet foreslår selv. Det gjør det mot styret bare når forslaget hviler på noe en person kan
  kontrollere: en av NBIMs regler med faktumet bak, lønnstallene, eller NBIMs egen stemme mot styret i samme sak sist.
- **Manuell vurdering:** alt verktøyet er usikker på går til en person, med grunnen: modellen er usikker, modellene
  foreslår å stemme mot styret uten regel eller faktum bak, en regel NBIM ikke har fulgt i det siste, et selskap uten
  historikk, mistenkelig tekst i forslaget, eller lav oppslutning ved forrige lønnsavstemning.
- **MOT foreslått eller sett:** NBIMs faktiske MOT-stemmer som verktøyet enten foreslo MOT på eller sendte til en
  person.
- **Retningslinje:** punktet i NBIMs stemmeretningslinjer (2025-utgaven) som forslaget hviler på, med ordlyden.
  «Prinsipp» betyr at verktøyet følger styret.
- **Hvorfor:** fakta og NBIMs tidligere stemmer. Teksten kommer fra datakildene og er på engelsk.

**De to datasettene**
- *Stemmefilen, alle land:* 1 539 forslag i 2026 fra NBIMs publiserte stemmer. Kombinert modell: stemmehistorikk,
  NBIMs regler anvendt på fakta fra selskapsdokumenter, Jev og en modell nummer to fra Maries løype, vektet på
  tidligere år.
- *Lønnsavstemninger USA:* 1 200 say-on-pay-vedtak i sesongen 2026 fra Norges Banks innrapportering til SEC.
  Lønnsmodellen: lønnstall fra innkallingen, NBIMs stemme forrige sesong og Jevs lesning av tallene mot NBIMs
  lønnsregler.

**Viktige forbehold**
- 2026 er testår, men er kjørt flere ganger under utviklingen. Hvor mange ganger står i `docs/model-card.md`.
- Med 66 og 114 MOT-stemmer er små forskjeller støy. Usikkerhetsintervaller står i `data/outputs/results.md`.
- Dashbordet gjør aldri API-kall. Alle svar fra språkmodellene er lagret.
- Dashbordet er bygget av Marie (gren `marie`) og kopiert hit for å vise denne grenens modell.
"""

# ---------------------------------------------------------------- page

st.title("🗳️ Stemmegivningsagenten")
st.caption("Forslag til FOR / MOT / AVSTÅ på generalforsamlinger, med begrunnelse, sitert retningslinje og sikkerhet. "
           "Systemet foreslår; en person tar den endelige avgjørelsen på alt som sendes til manuell vurdering.")

tab_overview, tab_about = st.tabs(["📊 Oversikt", "ℹ️ Om modellen"])

with tab_overview:
    available = {k: v for k, v in FILES.items() if v.exists()}
    if not available:
        st.warning("Fant ingen prediksjoner. Kjør `python3 src/run.py` fra rotmappen først (ingen API-kall).")
    else:
        with st.sidebar:
            st.header("Utvalg")
            model = st.radio("Modell", list(available), help="Stemmefilen: alle forslagstyper i NBIMs publiserte stemmer, kombinert modell. "
                                                           "Lønnsavstemninger: amerikanske say-on-pay-vedtak fra Norges Banks "
                                                           "SEC-innrapportering, lønnsmodellen. De to er ulike datasett.")
            df = load(str(available[model]), available[model].stat().st_mtime)
            fasit = st.toggle("Vis fasit (NBIMs faktiske stemme)", value=True)
            only_data = st.toggle("Bare forslag med dokument bak", value=False,
                                  help="Viser bare møter der et selskapsdokument levert før møtet er lenket: SEC for amerikanske "
                                       "noteringer, EDINET for Japan og DART for Sør-Korea. Modellen gir en anbefaling også "
                                       "uten dokument, da fra stemmehistorikken og NBIMs regler.")
            df_all = df
            if only_data:
                df = df[df["document_url"] != ""]
            years = st.multiselect("År", sorted(df["year"].unique(), reverse=True), default=[])
            votes = st.multiselect("Anbefaling", ["FOR", "MOT", "AVSTÅ"], default=[])
            route = st.radio("Rute", ["Alle", "Manuell vurdering", "Automatisk"], horizontal=True)
            types = st.multiselect("Forslagstype", sorted(df["Type"].unique()))
            countries = st.multiselect("Land", sorted(df["country"].unique()))
            board = st.radio("Styrets anbefaling", ["Alle", "FOR", "MOT"], horizontal=True)
            search = st.text_input("Søk i selskap eller forslag")
            min_conf = st.slider("Minste sikkerhet", 0.0, 1.0, DEFAULT_MIN_CONFIDENCE, 0.05,
                                 help="Skjuler forslag med lavere sikkerhet. Sikkerheten er modellens sannsynlighet for den "
                                      "anbefalte stemmen. Usikre forslag mot styret går uansett til en person; "
                                      "tabellen sier hvor mange filteret skjuler.")
            st.header("Sortering")
            sort_by = st.selectbox("Sorter etter", list(SORT))
            descending = st.toggle("Synkende", value=not SORT[sort_by][1])

        view = df[df["year"].isin(years)] if years else df
        if votes:
            view = view[view["vote"].isin(votes)]
        if route != "Alle":
            view = view[view["Rute"] == route]
        if types:
            view = view[view["Type"].isin(types)]
        if countries:
            view = view[view["country"].isin(countries)]
        if board != "Alle":
            view = view[view["mgmt_rec"] == board]
        if search:
            hit = view["company"].str.contains(search, case=False, regex=False) | view["proposal_text"].str.contains(search, case=False, regex=False)
            view = view[hit]
        hidden = view[view["confidence"] < min_conf]
        view = view[view["confidence"] >= min_conf]
        column, _ = SORT[sort_by]
        view = view.sort_values([column, "meeting_date", "company", "item_no"], ascending=[not descending, False, True, True],
                                kind="stable")

        # Two rows, one number per box, so no value is cut off: the selection first, then (with fasit) how it scored.
        k = st.columns(5)
        k[0].metric("Forslag", f"{len(view):,}".replace(",", " "))
        k[1].metric("Anbefalt MOT", int((view["vote"] == "MOT").sum()))
        k[2].metric("Anbefalt AVSTÅ", int((view["vote"] == "AVSTÅ").sum()))
        n_review = int((view["route"] == "human_review").sum())
        k[3].metric("Til manuell vurdering", n_review,
                    delta=f"{pct(n_review / len(view))} av utvalget" if len(view) else None, delta_color="off", delta_arrow="off")
        k[4].metric("Gj.sn. sikkerhet", pct(view["confidence"].mean()) if len(view) else "–")
        if fasit and len(view):
            p, r, f1, reached, n_mot = metrics(view)
            f = st.columns(5)
            f[0].metric("Presisjon på MOT", pct(p), help="Andelen av de anbefalte MOT-stemmene der NBIM faktisk stemte MOT.")
            f[1].metric("Recall på MOT", pct(r), help="Andelen av NBIMs faktiske MOT-stemmer som systemet anbefalte MOT på.")
            f[2].metric("F1 på MOT", pct(f1), help="Det harmoniske gjennomsnittet av presisjon og recall.")
            f[3].metric("MOT foreslått eller sett", f"{reached} av {n_mot}",
                        help="NBIMs faktiske MOT-stemmer som enten ble anbefalt MOT eller sendt til manuell vurdering.")
            f[4].metric("NBIM stemte MOT", n_mot, help="Antall forslag i utvalget der NBIM faktisk stemte MOT.")

        # Which row the details show: a click in the table, or Forrige/Neste (arrow keys). A new selection
        # (filters or sorting) starts at the first row again.
        pos = navigation_position(view)
        table = pd.DataFrame({
            "▶": ["▶" if i == pos else "" for i in range(len(view))],
            "Dato": view["meeting_date"], "Selskap": view["company"], "Land": view["country"], "Forslag": view["proposal_text"],
            "Dokument": view["document_url"].replace("", None),
            "Type": view["Type"], "Styret": view["mgmt_rec"], "Anbefaling": view["vote"], "Sikkerhet": view["confidence"],
            "Risiko for MOT": view["p_combined"], "Rute": view["Rute"], "Årsak til vurdering": view["Årsak til vurdering"],
            "Retningslinje": view["citation"].where(view["citation"] != "P.1", "Prinsipp"),
            "Kilde for sitering": view["Kilde for sitering"],
        })
        if fasit:
            table["NBIM stemte"] = view["nbim_vote"]
            table["Riktig"] = view["Riktig"]
        config = {
            "▶": st.column_config.Column("", width=28, help="Raden som vises i detaljene under"),
            "Sikkerhet": st.column_config.Column("Sikkerhet", help="Modellens sannsynlighet for den anbefalte stemmen"),
            "Anbefaling": st.column_config.Column("Anbefaling", help="Systemets forslag. En person avgjør alt som går til manuell vurdering."),
            "Risiko for MOT": st.column_config.ProgressColumn("Risiko for MOT", format="percent", min_value=0.0, max_value=1.0),
            "Forslag": st.column_config.TextColumn("Forslag", width="large"),
            "Dokument": st.column_config.LinkColumn("Dokument", display_text="Åpne ↗",
                                                    help="Hoveddokumentet for møtet: innkallingen (proxy) eller årsrapporten"),
            "Riktig": st.column_config.CheckboxColumn("Riktig"),
        }
        st.markdown(LEGEND)
        notes = []
        omitted = int(((df_all["year"].isin(years) if years else True) & (df_all["document_url"] == "")).sum()) if only_data else 0
        if omitted:
            notes.append(f"{omitted:,} forslag uten selskapsdokumenter er utelatt (bryteren «Bare forslag med dokument bak»)."
                         .replace(",", " "))
        if len(hidden):
            notes.append(f"«Minste sikkerhet» ({pct(min_conf)}) skjuler {len(hidden)} forslag, hvorav "
                         f"{int((hidden['vote'] == 'MOT').sum())} anbefalt MOT. Sett den til 0 for å se alle.")
        st.caption(" ".join(notes + ["Klikk på en rad, eller bruk Forrige/Neste (pil opp/ned), for å se hvorfor "
                                     "systemet anbefaler som det gjør."]))
        st.dataframe(styled(table), column_config=config, hide_index=True, width="stretch", height=420,
                     on_select="rerun", selection_mode="single-row", key="table")
        st.download_button("⬇️ Last ned utvalget som CSV", view.drop(columns=["_review_first"]).to_csv(index=False).encode("utf-8"),
                           file_name="anbefalinger.csv", mime="text/csv")

        st.divider()
        if len(view):
            nav = st.columns([1, 3, 1], vertical_alignment="center")
            nav[0].button("◀ Forrige", key="nav_prev", shortcut="left", on_click=move, args=(-1, len(view)),
                          disabled=pos == 0, width="stretch", help="Forrige rad i tabellen. Tastatur: pil opp.")
            nav[1].markdown(f"Forslag **{pos + 1}** av {len(view)} i utvalget", text_alignment="center")
            nav[2].button("Neste ▶", key="nav_next", shortcut="right", on_click=move, args=(1, len(view)),
                          disabled=pos == len(view) - 1, width="stretch", help="Neste rad i tabellen. Tastatur: pil ned.")
            show_details(view.iloc[pos].to_dict(), fasit)

with tab_about:
    st.subheader("Hva tallene betyr")
    st.markdown(ABOUT)
