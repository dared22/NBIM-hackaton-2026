"""Signals for the proposals where "NBIM voted MOT" and "NBIM voted against the board" differ.

The pipeline is trained to find NBIM's MOT votes. The two targets differ in two places only:
    abstentions            in some markets NBIM casts its votes against the board as AVSTÅ
    board recommends MOT   mostly shareholder proposals; NBIM voting FOR is then the vote against the board
Both signals are learned from NBIM's votes before the year being scored (like the skip rule):
    abstain   (country, proposal type) where most of NBIM's earlier votes against the board were
              abstentions, with at least ABSTAIN_MIN such votes: an MOT against a board FOR becomes AVSTÅ.
              This is main's rule (src/agent/routing.py abstain_markets), with main's untuned limit.
    support   NBIM supported the same proposal wording, or this proposal type, when the board opposed it:
              the same wording at least SUPPORT_MIN_TEXT times with a majority FOR, or the proposal type
              at least SUPPORT_MIN_TYPE times with at least SUPPORT_SHARE FOR. Then the vote is FOR.
The limits were set before measuring, from the size of the groups, not tuned on any test year.

score_against() turns the pipeline's p(MOT) ranking into a ranking for "against the board": on a
proposal the board recommends against, NBIM opposing the board means voting FOR (main's combined model
does the same).
"""

import re
from collections import defaultdict

ABSTAIN_MIN = 2
SUPPORT_MIN_TEXT = 2
SUPPORT_MIN_TYPE = 5
SUPPORT_SHARE = 0.6
VOTED = ("FOR", "MOT", "AVSTÅ")


def text_key(text):
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def against_board(r):
    return r["nbim_vote"] == "AVSTÅ" or (r["nbim_vote"] in ("FOR", "MOT") and r["nbim_vote"] != r["mgmt_rec"])


class Signals:
    """Learned from NBIM's votes before `before_date` (the first day of the year being scored)."""

    def __init__(self, rows, before_date):
        earlier = [r for r in rows if r["meeting_date"] < before_date and r["nbim_vote"] in VOTED and r["mgmt_rec"] in ("FOR", "MOT")]
        markets = defaultdict(lambda: [0, 0])
        for r in earlier:
            if against_board(r):
                m = markets[(r["country"], r["proposal_type"])]
                m[0] += r["nbim_vote"] == "AVSTÅ"
                m[1] += 1
        self.abstain_markets = {k: (a, n) for k, (a, n) in markets.items() if n >= ABSTAIN_MIN and 2 * a > n}
        by_text, by_type = defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0])
        for r in earlier:
            if r["mgmt_rec"] == "MOT":
                for table, key in ((by_text, text_key(r["proposal_text"])), (by_type, r["proposal_type"])):
                    table[key][0] += r["nbim_vote"] == "FOR"
                    table[key][1] += 1
        self.by_text, self.by_type = dict(by_text), dict(by_type)

    def abstain(self, row):
        """(True, reason) when NBIM usually abstains instead of voting against the board in this market."""
        hit = self.abstain_markets.get((row["country"], row["proposal_type"]))
        if not hit:
            return False, ""
        return True, (f"in {row['country']}, NBIM cast {hit[0]} of its {hit[1]} earlier votes against the board on "
                      f"{row['proposal_type'].lower().replace('_', ' ')} proposals as abstentions")

    def support(self, row):
        """(True, reason) when NBIM has usually supported this kind of proposal although the board opposed it."""
        if row["mgmt_rec"] != "MOT":
            return False, ""
        n_for, n = self.by_text.get(text_key(row["proposal_text"]), (0, 0))
        if n >= SUPPORT_MIN_TEXT and 2 * n_for > n:
            return True, f"NBIM supported this same proposal wording at {n_for} of {n} earlier meetings where the board opposed it"
        n_for, n = self.by_type.get(row["proposal_type"], (0, 0))
        if n >= SUPPORT_MIN_TYPE and n_for >= SUPPORT_SHARE * n:
            return True, (f"NBIM supported {n_for} of {n} earlier {row['proposal_type'].lower().replace('_', ' ')} "
                          f"proposals the board opposed")
        return False, ""


def score_against(p_mot, board):
    """Ranking score for "NBIM votes against the board" from the pipeline's p(MOT)."""
    return 1 - p_mot if board == "MOT" else p_mot
