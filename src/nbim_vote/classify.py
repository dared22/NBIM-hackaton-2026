"""Proposal type from the ballot text and the proponent, for agendas pasted into the demo.

real_votes.csv comes with a proposal type. A pasted agenda does not, so this assigns one with
ordered keyword rules: the first rule that matches wins. Run it to see how often it agrees with
the types in real_votes.csv:
    python src/classify.py

The rules read only the proposal text and the proponent, never a vote or rationale.
"""

import re

SHAREHOLDER_RULES = (
    ("SHP_INDEP_CHAIR", r"independent (board )?chair|separate chair"),
    ("SHP_GOVERNANCE", r"written consent|special meeting|simple majority|declassify|proxy access|majority vote|cumulative voting|one vote per share|recapitali[sz]ation plan"),
    ("SHP_SUSTAINABILITY", r"climate|ghg|greenhouse|emission|paris agreement|deforestation|plastic|human rights|child labor|harassment|discrimination|diversity|lobbying|political|biodiversity|water|sustainab|pay gap|racial|gender|indigenous"),
    ("DIRECTOR_ELECTION", r"^(re-?)?elect |^appoint .* as (non-executive |independent )?director|^elect |director nominee"),
)

RULES = (
    ("OTHER_BUSINESS", r"^(transact )?other business"),
    ("SAY_ON_PAY_FREQ", r"say on pay frequency|frequency of (the )?(say|advisory vote)"),
    ("SAY_ON_PAY", r"named executive officers'? compensation|remuneration (report|policy)|compensation report|executive compensation|say.on.pay|remuneration of (the )?(executive|management board|ceo)|approve compensation of (ceo|chairman|chair)|remuneration system"),
    ("DISCHARGE", r"discharge"),
    ("DIRECTOR_PAY", r"remuneration of (inside |outside |non-executive |the )*directors|directors' (fees|remuneration)|remuneration of (the )?(supervisory|board)|fees? (of|for) (the )?(non-executive )?directors|director compensation|total remuneration of"),
    ("SHARE_REPURCHASE", r"(share|stock) repurchase(?! .*reissu)|repurchase (of )?(issued )?(share|stock)|market purchase|buy ?back|purchase of (own|ordinary) shares|acquire (own|treasury) shares"),
    ("EQUITY_PLAN", r"(stock|share|equity|incentive|option|award|purchase|performance rights?|ownership) (plan|scheme|program)|performance rights|award shares|restricted stock|esop|employee stock|share options? to|grant of (options|rights|shares|performance)|matching shares|long.term incentive"),
    ("AUDITOR", r"auditor|audit firm|accounting firm|auditing firm"),
    ("FIN_STATEMENTS", r"financial statements|statutory reports|annual (account|report)|final account|board'?s report|report of the board|work report|directors' report|financial (budget|report)|budget report|annual accounts"),
    ("DIVIDEND", r"dividend|allocation of income|profit distribution|distribution of profit|treatment of (net )?loss|appropriation of (income|profit|retained)|omission of dividend"),
    ("SHARE_ISSUANCE", r"issu(e|ance) of (equity|shares|ordinary|new shares|a shares|h shares)|without pre-?emptive|pre-?emptive rights|reissuance of repurchased|capital increase|increase (in )?(authori[sz]ed )?(share )?capital|authori[sz]ed capital|convertible|warrants|share capital increase"),
    ("ANTITAKEOVER", r"takeover defen[cs]e|poison pill|rights plan|shareholder rights plan"),
    ("CLASSIFY_BOARD", r"(de)?classif(y|ied) (the )?board"),
    ("DUAL_CLASS", r"class [ab] shares"),
    ("MERGER", r"merger|acquisition|amalgamation|share exchange|spin.?off|demerger|disposal of|scheme of arrangement|tender offer|absorption"),
    ("RPT", r"related.party|connected transaction|guarantee|loans?,|provision of (financial )?assistance|framework agreement|deposit services|financial services agreement|continuing connected"),
    ("ARTICLES", r"articles|bylaws|by-laws|charter|memorandum|statute|constitution"),
    ("DIRECTOR_ELECTION", r"^(re-?)?elect\b|^appoint .*director|director\b.*\belect|^ratify (the )?(appointment|co-?option)|supervisory board member|^elect .* (as|to) |members? of (the )?(audit|nomination) committee"),
    ("DIRECTOR_ELECTION", r"supervisors|fiscal council|number of (members|directors)|member of the (nomination|compensation|remuneration)"),
    ("ROUTINE", r"re-registration|competitive activities|donations|editorial changes|^(open|close) meeting|^receive |^call the meeting|^registration|^prepare and approve list|^designate|^acknowledge|^approve agenda|^elect chairman of meeting|inspector|minutes|notice|^verify quorum|^note |^present |^discuss|^approve (the )?(meeting )?agenda|share premium|^authori[sz]e filing|^authori[sz]e board to ratify"),
)

_SHAREHOLDER = [(t, re.compile(p, re.I)) for t, p in SHAREHOLDER_RULES]
_RULES = [(t, re.compile(p, re.I)) for t, p in RULES]


def proposal_type(text, proponent="Management"):
    text = " ".join(text.split())
    if proponent.lower().startswith("share"):
        for t, rx in _SHAREHOLDER:
            if rx.search(text):
                return t
        return "SHP_OTHER"
    for t, rx in _RULES:
        if rx.search(text):
            return t
    return "OTHER_MGMT"


def main():
    import sys
    from collections import Counter
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from jev_mvp import load_votes
    rows = [r for r in load_votes() if r["proposal_text"].strip()]
    right = [proposal_type(r["proposal_text"], r["proponent"]) == r["proposal_type"] for r in rows]
    mot = [ok for ok, r in zip(right, rows) if r["nbim_vote"] == "MOT"]
    print(f"Agrees with real_votes.csv on {sum(right) / len(rows):.1%} of {len(rows)} proposals, "
          f"and on {sum(mot) / len(mot):.1%} of the {len(mot)} NBIM voted MOT on.")
    wrong = Counter((r["proposal_type"], proposal_type(r["proposal_text"], r["proponent"])) for ok, r in zip(right, rows) if not ok)
    print("Most common disagreements (real type, assigned type):")
    for (real, got), n in wrong.most_common(12):
        print(f"  {n:4d}  {real:20s} -> {got}")


if __name__ == "__main__":
    main()
