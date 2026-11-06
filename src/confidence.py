"""Confidence that means what it says: how often similar recommendations were right in earlier years.

The combined score is a probability that NBIM votes MOT. It is a poor guide to whether a recommendation
is right when the recommendation does not come from the score: following a board's MOT, or an MOT from a
rule in code or from NBIM's earlier reason. Those are right far more often than the score suggests.

So the confidence shown is calibrated on earlier years: recommendations are grouped by (recommendation,
board's recommendation) and by score band within the group, and the confidence is the share that matched
NBIM's vote in that band, pulled towards the group's share when the band is small. Only years before the
one being scored are used. Without earlier years, the raw value is kept: p(MOT) for MOT or AVSTÅ, else 1 - p(MOT).
"""

from collections import defaultdict

import numpy as np

BINS = 5          # score bands per group
SMOOTH = 10       # how many cases the group's share counts for in a band
MIN_GROUP = 20    # smaller groups fall back to all earlier recommendations of the same vote


def raw_confidence(vote, p_mot):
    return p_mot if vote in ("MOT", "AVSTÅ") else 1 - p_mot


class Calibrator:
    """Fitted on earlier recommendations: dicts with vote, mgmt_rec, p_combined and nbim_vote."""

    def __init__(self, records):
        records = [r for r in records if r.get("nbim_vote") in ("FOR", "MOT", "AVSTÅ")]
        self.ok = len(records) >= MIN_GROUP
        self.groups, self.by_vote = {}, defaultdict(list)
        grouped = defaultdict(list)
        for r in records:
            right = r["vote"] == r["nbim_vote"]
            grouped[(r["vote"], r["mgmt_rec"])].append((float(r["p_combined"]), right))
            self.by_vote[r["vote"]].append(right)
        self.overall = float(np.mean([x for v in self.by_vote.values() for x in v])) if records else 0.0
        for key, cases in grouped.items():
            if len(cases) < MIN_GROUP:
                continue
            p = np.array([c[0] for c in cases])
            right = np.array([c[1] for c in cases], float)
            edges = np.unique(np.quantile(p, np.linspace(0, 1, BINS + 1)[1:-1]))
            band = np.searchsorted(edges, p, side="right")
            share = right.mean()
            rates = {b: (right[band == b].sum() + SMOOTH * share) / ((band == b).sum() + SMOOTH) for b in range(len(edges) + 1)}
            self.groups[key] = (edges, rates, len(cases))

    def __call__(self, vote, board, p_mot):
        """(confidence, basis): basis says what the number rests on, in Norwegian for the dashboard."""
        if not self.ok:
            return raw_confidence(vote, p_mot), "rå modellscore (ingen tidligere år å kalibrere på)"
        group = self.groups.get((vote, board))
        if group:
            edges, rates, n = group
            return float(rates[int(np.searchsorted(edges, p_mot, side="right"))]), \
                f"andel riktige blant {n} tidligere anbefalinger {vote} der styret sa {board}, med lignende risiko"
        same = self.by_vote.get(vote)
        if same and len(same) >= 5:
            return float((sum(same) + SMOOTH * self.overall) / (len(same) + SMOOTH)), \
                f"andel riktige blant {len(same)} tidligere anbefalinger {vote}"
        return raw_confidence(vote, p_mot), "rå modellscore (for få tidligere tilfeller)"
