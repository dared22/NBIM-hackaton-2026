"""Export this branch's per-proposal scores for main's combined model (main: src/agent/combined_model.py).

Same columns as main's data/evidence/jev_pipeline/components_<year>.csv, from saved Jev answers (no API
calls), plus two columns main does not read yet:
    jev_vote, jev_p_mot       Jev's own answer and probability of MOT (saved run _v7, with company facts)
    jev_cited_section         the section Jev named for its vote
    triage_p                  the triage model's probability of MOT, trained on earlier years only
    marie_score, marie_flag, marie_review   the walk-forward combined score and routing (2022 on)
    marie_vote                the pipeline's final recommendation: board-MOT rule, director rules, AVSTÅ (2022 on)
    code_cited_section        the section the code citations give for MOT (src/nbim_vote/citations.py, 2022 on)
No NBIM vote and no rationale are written.

    python -m nbim_vote.export_components <out_dir>                 # main's format, from this branch
    python -m nbim_vote.export_components <out_dir> --final-vote    # jev_vote holds marie_vote instead (2022 on)

--final-vote lets main's combined model read the pipeline's final recommendation where it reads Jev's vote.
"""

import argparse
import csv
from pathlib import Path

from nbim_vote import report_results as rr

COLUMNS = ["meeting_id", "item_no", "jev_vote", "jev_p_mot", "jev_cited_section", "triage_p",
           "marie_score", "marie_flag", "marie_review", "marie_vote", "code_cited_section"]


def export(out_dir, final_vote=False, setup=None):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    s = setup or rr.Setup()
    for year in rr.YEARS:
        results = rr.read(rr.RUNS / f"results_{year}_history{rr.WITH}.csv")
        triage = s.triage[True][year].scores
        extra = {}
        if year in rr.TEST_YEARS:
            w = s.walk_forward(year, True)
            for r, score, flag, rev, vote in zip(w["results"], w["scores"], w["flagged"], w["reviewed"], w["votes"]):
                k = (r["meeting_id"], r["item_no"])
                extra[k] = (f"{score:.5f}", int(flag), int(rev), str(vote), s.code_section(year, k)[0])
        with open(out_dir / f"components_{year}.csv", "w", newline="", encoding="utf-8") as f:
            out = csv.writer(f)
            out.writerow(COLUMNS)
            for r in results:
                k = (r["meeting_id"], r["item_no"])
                score, flag, rev, vote, code = extra.get(k, ("", "", "", "", ""))
                jev_vote = vote if final_vote and vote else r["jev_vote"]
                out.writerow([k[0], k[1], jev_vote, r["p_mot"], r.get("cited_section", ""), f"{triage[k]:.5f}",
                              score, flag, rev, vote, code])
        print(f"{year}: {len(results)} rows")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("out_dir")
    p.add_argument("--final-vote", action="store_true", help="put the pipeline's final recommendation in jev_vote (2022 on)")
    a = p.parse_args()
    export(a.out_dir, a.final_vote)


if __name__ == "__main__":
    main()
