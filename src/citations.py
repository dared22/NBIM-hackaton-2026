"""Guideline citations without Jev: from NBIM's own earlier reasons, the rules in code, and a text model.

For a recommended vote, the first source that gives an answer is used:
    1. rule in code     a director rule that fired on filed facts (director_rules.py)
    2. same item        NBIM's cited section the last time it opposed this same item at this company
    3. same company     NBIM's most recent cited section for this proposal type at this company
    4. text model       a classifier from the proposal text, type and country to the section NBIM cited,
                        trained on NBIM's MOT votes before the current year only
Steps 2-4 give a section (e.g. 1.3), the level NBIM cites. The point within it (e.g. 1.3.1) is the
section's rule pointing the same way whose words best match the proposal and its company facts.
A FOR that departs from a board MOT is matched to the candidate FOR rules by text. Following the
board is cited as the voting principle (P.1), also an MOT on a board MOT unless step 1-3 names a reason. AVSTÅ gets no citation: a person decides.

Only earlier meetings and filings are used; the row's own vote and rationale are never read.

    python src/citations.py        # how often each source names the section NBIM cited, 2022-2026
"""

import re
from collections import Counter

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics.pairwise import cosine_similarity
from scipy.sparse import hstack

from director_rules import deciding_rule
from jev_mvp import TYPE_TO_SECTIONS, candidate_rules, item_key, strip_instructions

MIN_TRAIN = 50  # fewer earlier cited MOT votes than this: no text model


def nbim_section(text):
    """'GVG 1.3' -> '1.3'; anything else -> None."""
    m = re.match(r"GVG (\d+\.\d+)", text or "")
    return m.group(1) if m else None


def section_rules(section, by_section, vote):
    """Rules in a section (6.2 includes the anti-takeover points) that point to this vote."""
    keys = [k for k in by_section if k == section or k.startswith(section + "-")]
    seen, out = set(), []
    for k in keys:
        for r in by_section[k]:
            if r["avledet"]["handling"] == vote and r["id"] not in seen:
                seen.add(r["id"])
                out.append(r)
    return out


class Citer:
    """Built once per test year: the text model trains on NBIM's cited MOT votes before `before_date`."""

    def __init__(self, rows, before_date):
        self.before = before_date
        train = [r for r in rows if r["meeting_date"] < before_date and r["nbim_vote"] == "MOT" and nbim_section(r["rationale_section"])]
        self.model = None
        if len(train) >= MIN_TRAIN and len({nbim_section(r["rationale_section"]) for r in train}) > 1:
            self.words = TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True)
            self.tags = TfidfVectorizer(token_pattern=r"\S+")
            X = hstack([self.words.fit_transform([self._text(r) for r in train]), self.tags.fit_transform([self._tags(r) for r in train])])
            self.model = LogisticRegression(C=3.0, max_iter=3000).fit(X, [nbim_section(r["rationale_section"]) for r in train])
        self._match = {}

    @staticmethod
    def _text(r):
        return strip_instructions(r["proposal_text"])

    @staticmethod
    def _tags(r):
        return f"type={r['proposal_type']} country={r['country'].replace(' ', '_')} market={r['market']} by={r['proponent']}"

    def text_section(self, row):
        if self.model is None:
            return None, 0.0
        X = hstack([self.words.transform([self._text(row)]), self.tags.transform([self._tags(row)])])
        p = self.model.predict_proba(X)[0]
        i = int(np.argmax(p))
        return self.model.classes_[i], float(p[i])

    def best_point(self, rules, query):
        """The rule whose words best match the query (TF-IDF over these rules' texts)."""
        if len(rules) == 1:
            return rules[0]
        key = tuple(r["id"] for r in rules)
        if key not in self._match:
            v = TfidfVectorizer(sublinear_tf=True, stop_words="english")
            self._match[key] = (v, v.fit_transform([r["tekst"] for r in rules]))
        v, M = self._match[key]
        scores = cosine_similarity(v.transform([query]), M)[0]
        return rules[int(np.argmax(scores))]  # ties: the lowest point number, the order in the guidelines

    def cite(self, row, vote, by_section, history_index, signals=(), facts_text=""):
        """(rule or None, source). Same interface whatever the vote."""
        board = row["mgmt_rec"] if row["mgmt_rec"] in ("FOR", "MOT") else "FOR"
        if vote == "AVSTÅ":
            return None, ""
        query = f"{self._text(row)} {row['proposal_type'].lower().replace('_', ' ')} {facts_text}"
        if vote == "FOR":
            if board == "FOR":
                return None, "voting principle"
            rules = [r for r in candidate_rules(row["proposal_type"], by_section) if r["avledet"]["handling"] == "FOR"]
            return (self.best_point(rules, query), "text match") if rules else (None, "")

        # MOT
        decided = deciding_rule(signals) or next((s[0] for s in signals), None)
        if decided:
            rule = next((r for k in by_section for r in by_section[k] if r["id"] == decided), None)
            if rule:
                return rule, "rule in code"
        past = [p for p in history_index.get(row["company_id"], []) if p["meeting_date"] < row["meeting_date"]
                and p["proposal_type"] == row["proposal_type"] and p["nbim_vote"] == "MOT" and nbim_section(p["rationale_section"])]
        key = item_key(row)
        for source, pool in (("NBIM's earlier reason, same item", [p for p in past if item_key(p) == key]),
                             ("NBIM's earlier reason, same company", past)):
            for p in reversed(pool):
                rules = section_rules(nbim_section(p["rationale_section"]), by_section, "MOT")
                if rules:
                    return self.best_point(rules, query), source
        if board == "MOT":
            # Following the board's MOT with no rule or record that names a reason: the voting principle.
            return None, "voting principle"
        section, prob = self.text_section(row)
        if section:
            rules = section_rules(section, by_section, "MOT")
            if rules:
                return self.best_point(rules, query), f"text model (p={prob:.2f})"
        rules = [r for r in candidate_rules(row["proposal_type"], by_section) if r["avledet"]["handling"] == "MOT"]
        if rules:
            return self.best_point(rules, query), "text match"
        return None, ""


def main():
    """How often each source names the section NBIM cited, on NBIM's MOT votes with a GVG section."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from company_facts import facts
    from director_rules import rule_states
    from explain import fact_reasons
    from jev_mvp import build_history_index, cited_section, guidelines_for, load_guideline_versions, load_votes

    rows = load_votes()
    index = build_history_index(rows)
    versions = load_guideline_versions()
    known = facts()
    states = rule_states(rows, known, guidelines_for, versions)
    right, used = Counter(), Counter()
    for year in range(2022, 2027):
        citer = Citer(rows, f"{year}-01-01")
        for r in rows:
            if r["year"] != str(year) or r["nbim_vote"] != "MOT" or not nbim_section(r["rationale_section"]):
                continue
            _, by_section = guidelines_for(r["meeting_date"], versions)
            rule, source = citer.cite(r, "MOT", by_section, index, states.get((r["meeting_id"], r["item_no"]), []),
                                      " ".join(fact_reasons(r, known)[0]))
            name = source.split(" (")[0] or "none"
            used[name] += 1
            right[name] += bool(rule) and cited_section(rule) == nbim_section(r["rationale_section"])
    print(f"NBIM MOT votes with a GVG section, 2022-2026: {sum(used.values())}. Section named right: {sum(right.values())}.")
    for name, n in used.most_common():
        print(f"  {name:38s} {n:4d}  right {right[name]:4d} ({right[name] / n:.0%})")


if __name__ == "__main__":
    main()
