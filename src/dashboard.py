"""Stemmegivningsagenten: dashboard (Streamlit). The interface is in Norwegian.

Run from the repository root:
    python src/dashboard_data.py           # once: builds data/outputs/dashboard/predictions_*.csv (no API calls)
    streamlit run src/dashboard.py

Tabs
    Oversikt        every proposal 2022-2026, recommended walk-forward: filter, sort, and see why
    Ny saksliste    paste an agenda and get recommendations (runs without Jev: no API call, about 30 seconds)
    Om modellen     what the numbers mean
"""

import json
import re
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "outputs" / "dashboard"
# "Med Jev" first: the overview uses Jev's saved answers (no API call), and its MOT recommendations are the more reliable.
FILES = {"Med Jev": DATA / "predictions_jev.csv", "Uten Jev": DATA / "predictions_nojev.csv"}
EXAMPLE = ROOT / "data" / "demo" / "hp_2026-04-16.txt"
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
HIGH, MEDIUM = 0.90, 0.70  # confidence bands; on 2023-2026, right about 97 %, 90-93 % and 46-80 % of the time
DEFAULT_MIN_CONFIDENCE = 0.50  # below this, similar recommendations in earlier years were wrong more often than right
BADGE = {"MOT": "red", "AVSTÅ": "orange", "FOR": "green"}

st.set_page_config(page_title="Stemmegivningsagenten", page_icon="🗳️", layout="wide")


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
    for c in ("confidence", "p_combined", "p_model"):
        df[c] = pd.to_numeric(df[c])
    df["p_mot"] = pd.to_numeric(df["p_mot"], errors="coerce")
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
    reached = int((actual & (df["route"] == "human_review")).sum())
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


def show_reasons(reasons, passages):
    """The reason lines. Where a line rests on a passage in a document, it gets Streamlit's own hover help (the
    icon beside the line): the source, the passage and a link to the document, at the quoted sentence where the
    browser supports text links. Plain markdown: no HTML, so it shows at once and in every browser."""
    for line in reasons:
        found = passages.get(line)
        if not found:
            st.markdown(f"- {md_escape(line)}")
            continue
        shown = re.sub(r' \(proxy: ".*?"\)', "", line)  # the quote is in the hover text instead
        passage = found["passage"] if len(found["passage"]) <= HOVER_CHARS else found["passage"][:HOVER_CHARS] + " …"
        tip = f"**{md_escape(found['source'])}**\n\n> {md_escape(passage)}"
        if found.get("url"):
            tip += f"\n\n[Åpne dokumentet ↗]({found['url']})"
        st.markdown(f"- {md_escape(shown)} 🔎", help=tip)
    if passages:
        st.caption("Hold musepekeren over ⓘ ved linjene merket 🔎 for å se avsnittet de bygger på, med lenke til dokumentet. "
                   "Avsnitt finnes der vi har tekst: proxysitater kontrollert mot dokumentet, 8-K, utdrag fra innkallingen, "
                   "NBIMs begrunnelser og retningslinjene. For Japan og Sør-Korea er faktaene strukturerte felt uten tekstavsnitt.")
    else:
        st.caption("Ingen av linjene over bygger på et tekstavsnitt vi har (for eksempel bare strukturerte felt eller "
                   "stemmehistorikk uten begrunnelse), så det er ingenting å vise ved hovring her.")


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
    c[1].metric("Sikkerhet", pct(r["confidence"]), help="Andelen riktige blant lignende anbefalinger tidligere år")
    c[2].metric("Risiko for MOT", pct(r["p_combined"]), help="Den samlede modellens sannsynlighet for at NBIM stemmer MOT")
    c[3].metric("Triagemodell", pct(r["p_model"]))
    c[4].metric("Jev", "–" if pd.isna(r.get("p_mot")) or r.get("p_mot") == "" else pct(float(r["p_mot"])))
    st.markdown(f"**Styrets anbefaling:** {r['mgmt_rec']} · **Type:** {TYPE.get(r['proposal_type'], r['proposal_type'])}"
                f" · **Rute:** {ROUTE.get(r['route'], r['route'])}"
                + (f" ({review_why(r)})" if r["route"] == "human_review" else ""))
    st.markdown("**Retningslinje**")
    st.info(r["guideline_text"] or "Ingen retningslinje funnet: en person avgjør.")
    st.caption(f"Kilde for siteringen: {SOURCE.get(r['citation_source'], r['citation_source'])}")
    reasons = [x for x in str(r["reasons"]).split(" | ") if x]
    if reasons:
        st.markdown("**Relevante retningslinjer for beslutning** (fakta og NBIMs historikk, fra datakildene)")
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


# ---------------------------------------------------------------- page

st.title("🗳️ Stemmegivningsagenten")
st.caption("Forslag til FOR / MOT / AVSTÅ på generalforsamlinger, med begrunnelse, sitert retningslinje og sikkerhet. "
           "Systemet foreslår; en person tar den endelige avgjørelsen på alt som sendes til manuell vurdering.")

tab_overview, tab_new, tab_about = st.tabs(["📊 Oversikt", "📝 Ny saksliste", "ℹ️ Om modellen"])

with tab_overview:
    available = {k: v for k, v in FILES.items() if v.exists()}
    if not available:
        st.warning("Fant ingen prediksjoner. Kjør `python src/dashboard_data.py` fra rotmappen først (ingen API-kall).")
    else:
        with st.sidebar:
            st.header("Utvalg")
            model = st.radio("Modell", list(available), help="Uten Jev: triagemodell, regler i kode og kodesiteringer. "
                                                           "Med Jev: i tillegg språkmodellen Jev (lagrede svar, ingen API-kall).")
            df = load(str(available[model]), available[model].stat().st_mtime)
            fasit = st.toggle("Vis fasit (NBIMs faktiske stemme)", value=False)
            only_data = st.toggle("Bare forslag med data bak", value=True,
                                  help="Bare møter der vi har selskapsdokumenter levert før møtet: SEC for amerikanske "
                                       "noteringer, EDINET for Japan og DART for Sør-Korea. Uten dokumenter gir systemet "
                                       "ingen anbefaling.")
            df_all = df
            if only_data:
                df = df[df["document_url"] != ""]
            years = st.multiselect("År", sorted(df["year"].unique(), reverse=True), default=[df["year"].max()])
            votes = st.multiselect("Anbefaling", ["FOR", "MOT", "AVSTÅ"], default=[])
            route = st.radio("Rute", ["Alle", "Manuell vurdering", "Automatisk"], horizontal=True)
            types = st.multiselect("Forslagstype", sorted(df["Type"].unique()))
            countries = st.multiselect("Land", sorted(df["country"].unique()))
            board = st.radio("Styrets anbefaling", ["Alle", "FOR", "MOT"], horizontal=True)
            search = st.text_input("Søk i selskap eller forslag")
            min_conf = st.slider("Minste sikkerhet", 0.0, 1.0, DEFAULT_MIN_CONFIDENCE, 0.05,
                                 help="Skjuler forslag med lavere sikkerhet. Sikkerheten er andelen riktige blant lignende "
                                      "anbefalinger tidligere år, så under 50 % var lignende anbefalinger oftere feil enn "
                                      "riktige. De usikre forslagene er nesten alltid anbefalt MOT og går uansett til en person; "
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

        k = st.columns(5 if not fasit else 7)
        k[0].metric("Forslag", f"{len(view):,}".replace(",", " "))
        k[1].metric("Anbefalt MOT", int((view["vote"] == "MOT").sum()))
        k[2].metric("Anbefalt AVSTÅ", int((view["vote"] == "AVSTÅ").sum()))
        n_review = int((view["route"] == "human_review").sum())
        k[3].metric("Til manuell vurdering", f"{n_review} ({pct(n_review / len(view)) if len(view) else '–'})")
        k[4].metric("Gj.sn. sikkerhet", pct(view["confidence"].mean()) if len(view) else "–")
        if fasit and len(view):
            p, r, f1, reached, n_mot = metrics(view)
            k[5].metric("Presisjon / recall på MOT", f"{pct(p)} / {pct(r)}", help=f"F1 {pct(f1)}. Måles mot NBIMs faktiske stemmer.")
            k[6].metric("MOT som når en person", f"{reached} av {n_mot}")

        table = pd.DataFrame({
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
            "Sikkerhet": st.column_config.Column("Sikkerhet", help="Andelen riktige blant lignende anbefalinger tidligere år"),
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
            notes.append(f"{omitted:,} forslag uten selskapsdokumenter er utelatt (bryteren «Bare forslag med data bak»)."
                         .replace(",", " "))
        if len(hidden):
            notes.append(f"«Minste sikkerhet» ({pct(min_conf)}) skjuler {len(hidden)} forslag, hvorav "
                         f"{int((hidden['vote'] == 'MOT').sum())} anbefalt MOT. Sett den til 0 for å se alle.")
        st.caption(" ".join(notes + ["Klikk på en rad for å se hvorfor systemet anbefaler som det gjør."]))
        event = st.dataframe(styled(table), column_config=config, hide_index=True, width="stretch", height=420,
                             on_select="rerun", selection_mode="single-row", key="table")
        st.download_button("⬇️ Last ned utvalget som CSV", view.drop(columns=["_review_first"]).to_csv(index=False).encode("utf-8"),
                           file_name="anbefalinger.csv", mime="text/csv")

        picked = event.selection.rows if event and event.selection else []
        st.divider()
        if picked:
            show_details(view.iloc[picked[0]].to_dict(), fasit)
        elif len(view):
            st.markdown("**Detaljer:** velg en rad i tabellen over. Viser den første raden i utvalget:")
            show_details(view.iloc[0].to_dict(), fasit)

with tab_new:
    st.subheader("Lim inn en saksliste")
    st.caption("Kjøres uten Jev: ingen API-kall og ingen nøkkel trengs. Tar rundt 30 sekunder. "
               "Gir bare anbefalinger der det finnes selskapsdokumenter (SEC, EDINET eller DART). Én sak per linje. «SH:» foran markerer et aksjonærforslag (styret antas da å anbefale MOT). "
               "«[board: FOR]» eller «[board: MOT]» til slutt i linjen setter styrets anbefaling.")
    example = EXAMPLE.read_text(encoding="utf-8") if EXAMPLE.exists() else ""
    with st.form("agenda"):
        c = st.columns(4)
        company = c[0].text_input("Selskap", "HP Inc.")
        date = c[1].date_input("Møtedato", pd.Timestamp("2026-04-16"))
        country = c[2].text_input("Land (trengs for nye selskaper)", "")
        market = c[3].selectbox("Marked", ["Fra historikken", "DM", "EM"])
        agenda = st.text_area("Saksliste", example, height=260)
        go = st.form_submit_button("Gi anbefalinger", type="primary")
    if go:
        from demo import NoDataError, parse_agenda, run_agenda  # Loaded on demand: it reads all data and trains the models.

        items = parse_agenda(agenda)
        if not items:
            st.error("Fant ingen saker i sakslisten.")
        else:
            try:
                with st.spinner("Beregner anbefalinger … (rundt 30 sekunder)"):
                    out = run_agenda(items, company.strip(), date.isoformat(), country.strip() or None,
                                     None if market == "Fra historikken" else market)
            except NoDataError:
                st.warning(f"Ingen anbefaling: det finnes ingen selskapsdokumenter i datagrunnlaget for {company} før "
                           f"{date.isoformat()}. Systemet anbefaler bare der det har dokumenter bak møtet: SEC for "
                           f"amerikanske noteringer, EDINET for Japan og DART for Sør-Korea.")
                out = None
            except ValueError:
                st.error("Selskapet finnes ikke i NBIMs tidligere stemmer. Fyll inn land.")
                out = None
            if out:
                known = (f"NBIM har stemt på {out['earlier_proposals']} tidligere forslag i selskapet."
                         if out["known_company"] else "Ingen tidligere NBIM-stemmer i selskapet: ingen historikk.")
                st.success(f"{out['company']}, {out['date']}, {out['country']} ({out['market']}). "
                           f"Retningslinjer: {out['edition']}-utgaven. {known}")
                res = pd.DataFrame(out["results"])
                res["Rute"] = res["route"].map(ROUTE)
                res["Årsak til vurdering"] = res.apply(review_why, axis=1)
                st.markdown(LEGEND)
                st.dataframe(styled(pd.DataFrame({
                    "Nr": res["item_no"], "Forslag": res["proposal_text"], "Type": res["proposal_type"].map(TYPE).fillna(res["proposal_type"]),
                    "Styret": res["mgmt_rec"], "Anbefaling": res["vote"], "Sikkerhet": res["confidence"],
                    "Risiko for MOT": res["p_combined"], "Rute": res["Rute"], "Årsak til vurdering": res["Årsak til vurdering"],
                    "Retningslinje": res["citation"].where(res["citation"] != "P.1", "Prinsipp"),
                })), hide_index=True, width="stretch", column_config={
                    "Risiko for MOT": st.column_config.ProgressColumn("Risiko for MOT", format="percent", min_value=0.0, max_value=1.0),
                    "Forslag": st.column_config.TextColumn("Forslag", width="large")})
                for r in out["results"]:
                    with st.expander(f"{r['item_no']}. {r['proposal_text'][:90]}  →  {r['vote']} ({pct(r['confidence'])} sikker)"):
                        show_details({**r, "company": out["company"], "company_id": out["company_id"],
                                      "meeting_date": out["date"], "reasons": " | ".join(r["reasons"])},
                                     fasit=False, docs=out["documents"])

with tab_about:
    st.subheader("Hva tallene betyr")
    st.markdown("""
- **Anbefaling:** FOR, MOT eller AVSTÅ. Uten grunn til å avvike følger systemet styrets anbefaling.
- **Risiko for MOT:** den samlede modellens sannsynlighet for at NBIM stemmer MOT. Den er tilpasset på tidligere år.
- **Sikkerhet:** hvor ofte lignende anbefalinger var riktige tidligere år: samme anbefaling, samme anbefaling fra
  styret og lignende risiko for MOT. Den beregnes bare fra år før det året som vises. 2022 har ingen tidligere år å
  kalibrere på og viser derfor modellens rå score (risikoen for MOT når anbefalingen er MOT, ellers 1 minus risikoen).
- **Farger:** anbefalingen er markert (rød MOT, gul AVSTÅ, grønn FOR). Sikkerheten er grønn fra 90 %, gul fra 70 %
  og rød under 70 %. På 2023–2026 var anbefalingen riktig rundt 97 % av gangene i grønt, 90–93 % i gult og 46–80 % i rødt.
- **Bare forslag med data bak:** systemet anbefaler bare der det finnes selskapsdokumenter levert før møtet
  (SEC for amerikanske noteringer, EDINET for Japan, DART for Sør-Korea).
- **Minste sikkerhet:** står på 50 % som standard: da skjules anbefalinger som tidligere var feil oftere enn riktige.
  De usikre forslagene er nesten alltid anbefalt MOT og går uansett til en person, så tabellen sier hvor mange
  MOT-forslag filteret skjuler.
- **Manuell vurdering:** forslaget går til en person når det er blant de mest risikable de siste 12 månedene, når
  anbefalingen er MOT eller AVSTÅ, når den avviker fra styret, når en av NBIMs regler slår til uten å være betrodd ennå,
  eller når teksten inneholder en instruksjon til leseren.
- **Retningslinje:** punktet i NBIMs stemmeretningslinjer som avgjør, med utgave og side. Det hentes fra en regel i kode,
  fra NBIMs egen tidligere begrunnelse for samme sak eller selskap, eller fra en tekstmodell trent på tidligere år.
  «Prinsipp» betyr at systemet følger styret.
- **Hvorfor:** fakta fra dokumenter levert før møtet (fullmakt/proxy, EDINET, DART) og NBIMs tidligere stemmer i
  selskapet. Teksten kommer fra datakildene og er på engelsk.

**Hvordan årene er beregnet:** hvert år er anbefalt som om det skjedde live: modellene er trent på tidligere år, og
hvert forslag rangeres mot de foregående 12 månedene. Fasiten (NBIMs faktiske stemme) brukes bare til å vise hvordan
systemet traff.

**Viktige forbehold**
- 2026 ble brukt mens systemet ble utviklet, og er ikke en ren test. 2022 og 2023 er de reneste årene.
- Med 60–110 MOT-stemmer i året er små forskjeller mellom år støy.
- «Med Jev» bruker lagrede svar fra språkmodellen Jev; dashbordet gjør aldri API-kall.
""")
