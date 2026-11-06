"""Export, per proposal and year, the pieces of Marie's pipeline from her saved Jev answers (no API calls).
Run in a checkout of branch marie:  python export_marie.py <out_dir>
    jev_vote, jev_p_mot   Jev's answer and its probability of MOT (saved run _v7, with company facts)
    triage_p              her second model's probability of MOT, trained on earlier years only
    marie_score, marie_flag, marie_review   her walk-forward combined score and routing (2022 on)
"""
import sys, csv, os
sys.path.insert(0, "src")
import report_results as rr
out_dir = sys.argv[1]
os.makedirs(out_dir, exist_ok=True)
s = rr.Setup()
for year in rr.YEARS:
    results = rr.read(rr.RUNS / f"results_{year}_history{rr.WITH}.csv")
    triage = s.triage[True][year].scores
    wf = s.walk_forward(year, True) if year in rr.TEST_YEARS else None
    extra = {}
    if wf:
        for r, sc, fl, rev in zip(wf["results"], wf["scores"], wf["flagged"], wf["reviewed"]):
            extra[(r["meeting_id"], r["item_no"])] = (f"{sc:.5f}", int(fl), int(rev))
    with open(os.path.join(out_dir, f"components_{year}.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["meeting_id", "item_no", "jev_vote", "jev_p_mot", "jev_cited_section", "triage_p", "marie_score", "marie_flag", "marie_review"])
        for r in results:
            k = (r["meeting_id"], r["item_no"])
            w.writerow([k[0], k[1], r["jev_vote"], r["p_mot"], r.get("cited_section", ""), f"{triage[k]:.5f}", *extra.get(k, ("", "", ""))])
    print(year, len(results), "rows")
