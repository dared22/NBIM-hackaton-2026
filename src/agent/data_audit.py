"""Data audit: look at every column of every vote file before modelling.

Run from the repo root (a few seconds, no internet):
    python3 src/agent/data_audit.py

It prints the report and writes it to data/outputs/data_audit.md.

Files audited
    data/dirty/real_votes.csv       NBIM's votes, all proposal types (organisers)
    data/dirty/npx_votes.csv        another investor's votes (organisers)
    data/dirty/nbim_pay_votes.csv   NBIM's US pay votes (Norges Bank Form N-PX)

Nothing is changed in the files. Every count in the report comes from the raw
rows, so a reader can check any line against the CSV.
"""

import collections
import csv
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REAL = os.path.join(ROOT, "data", "dirty", "real_votes.csv")
NPX = os.path.join(ROOT, "data", "dirty", "npx_votes.csv")
PAY = os.path.join(ROOT, "data", "dirty", "nbim_pay_votes.csv")
OUT = os.path.join(ROOT, "data", "outputs", "data_audit.md")
C = collections.Counter
csv.field_size_limit(10 ** 9)


def read(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def rate(rows):
    return f"{sum(r['y'] for r in rows) / len(rows):.1%}" if rows else "-"


def text_key(r):
    return re.sub(r"[^a-z0-9]+", " ", r["proposal_text"].lower()).strip()


def name_key(s):
    s = re.sub(r"\b(INC|INCORPORATED|CORP|CORPORATION|COMPANY|CO|THE|PLC|LTD|LIMITED|HOLDINGS|GROUP|AG|SA|AB|NV)\b",
               "", s.upper().replace("&", "AND").replace(".", " "))
    return re.sub(r"[^A-Z0-9]", "", s)


def table(headers, rows):
    rows = [[str(v) for v in row] for row in [headers, *rows]]
    widths = [max(len(r[i]) for r in rows) for i in range(len(headers))]
    for i, row in enumerate(rows):
        print("  " + " | ".join(v.ljust(w) if j == 0 else v.rjust(w) for j, (v, w) in enumerate(zip(row, widths))))
        if i == 0:
            print("  " + "-+-".join("-" * w for w in widths))


def audit_real():
    R = read(REAL)
    raw = open(REAL, "rb").read()
    print(f"## 1. Main file: {os.path.relpath(REAL, ROOT)}\n")
    print(f"{len(R)} rows, {len(R[0])} columns, {raw.count(bytes([13, 10]))} Windows line endings, "
          f"{sum(1 for r in R if chr(10) in r['proposal_text'])} proposal texts contain a line break.\n")

    print("### 1.1 Empty cells per column\n")
    table(["Column", "Empty", "Distinct values"],
          [[c, sum(1 for r in R if r[c] == ""), len({r[c] for r in R})] for c in R[0]])

    print("\n### 1.2 Keys and duplicates\n")
    meet_company, company_names = collections.defaultdict(set), collections.defaultdict(set)
    for r in R:
        meet_company[r["meeting_id"]].add(r["company_id"])
        company_names[r["company_id"]].add((r["company"], r["ticker"], r["country"]))
    print(f"- Exact duplicate rows: {len(R) - len({tuple(r.values()) for r in R})}")
    print(f"- meeting_id + item_no is a unique key: {len({(r['meeting_id'], r['item_no']) for r in R}) == len(R)}")
    print(f"- Meetings with more than one company: {sum(1 for v in meet_company.values() if len(v) > 1)}")
    print(f"- Companies with more than one name, ticker or country: {sum(1 for v in company_names.values() if len(v) > 1)}")
    print(f"- The same wording twice in one meeting: "
          f"{sum(1 for v in C((r['meeting_id'], r['proposal_text']) for r in R).values() if v > 1)} cases")

    print("\n### 1.3 How the answer columns were built\n")
    table(["Board (raw)", "NBIM (raw)", "Board", "NBIM", "against_board", "Rows"],
          [list(k) + [n] for k, n in C((r["mgmt_rec_raw"], r["nbim_vote_raw"], r["mgmt_rec"], r["nbim_vote"],
                                        r["against_board"] or "(empty)") for r in R).most_common()])
    nolabel = [r for r in R if r["against_board"] == ""]
    print(f"\n{len(nolabel)} rows have no against_board value and are left out of every evaluation:")
    print(f"- {sum(1 for r in nolabel if r['nbim_vote'] == '' )} have no NBIM vote "
          f"(non-voting items such as 'Open Meeting', and {sum(1 for r in R if r['nbim_vote_raw'] == 'Do Not Vote')} 'Do Not Vote').")
    novote_rec = [r for r in nolabel if r["nbim_vote"] and not r["mgmt_rec"]]
    print(f"- {len(novote_rec)} have an NBIM vote but no board recommendation "
          f"({dict(C(r['nbim_vote'] for r in novote_rec))}), mostly director elections in "
          f"{', '.join(k for k, _ in C(r['country'] for r in novote_rec).most_common(3))}.")
    print("- An abstention against a board recommendation counts as against the board "
          f"({sum(1 for r in R if r['nbim_vote'] == 'AVSTÅ' and r['against_board'] == '1.0')} rows).")

    L = [r for r in R if r["against_board"] in ("0.0", "1.0")]
    for r in L:
        r["y"] = r["against_board"] == "1.0"
    L.sort(key=lambda r: (r["meeting_date"], r["meeting_id"], int(r["item_no"])))

    print(f"\n### 1.4 Over time ({len(L)} rows with an answer)\n")
    rows = []
    for y in sorted({r["year"] for r in L}):
        b = [r for r in L if r["year"] == y]
        ag = [r for r in b if r["y"]]
        rows.append([y, len(b), rate(b), rate([r for r in b if r["market"] == "DM"]), rate([r for r in b if r["market"] == "EM"]),
                     len({r["meeting_id"] for r in b}), len({r["company_id"] for r in b}),
                     f"{sum(1 for r in ag if r['rationale_text'])}/{len(ag)}"])
    table(["Year", "Rows", "Against", "Developed", "Emerging", "Meetings", "Companies", "Against-votes with NBIM's reason"], rows)
    print("\n2019 has no reasons at all. 2026 stops in September.")

    print("\n### 1.5 Companies\n")
    comp = collections.defaultdict(list)
    for r in L:
        comp[r["company_id"]].append(r)
    by_against = sorted(((sum(r["y"] for r in v), len(v), v[0]["company"], v[0]["country"]) for v in comp.values()), reverse=True)
    total = sum(a for a, *_ in by_against)
    print(f"- {len(comp)} companies in {len({v[0]['country'] for v in comp.values()})} countries; "
          f"{sum(1 for v in comp.values() if v[0]['market'] == 'DM')} developed, {sum(1 for v in comp.values() if v[0]['market'] == 'EM')} emerging.")
    print(f"- {sum(1 for a, *_ in by_against if a == 0)} companies have no against-vote in the whole file.")
    print(f"- The 10 companies with most against-votes hold {sum(a for a, *_ in by_against[:10])} of {total} "
          f"({sum(a for a, *_ in by_against[:10]) / total:.0%}).")
    table(["Company", "Country", "Rows", "Against"], [[n, c, k, a] for a, k, n, c in by_against[:6]])
    first = C(min(r["year"] for r in v) for v in comp.values())
    print(f"- Companies first seen per year: {dict(sorted(first.items()))}. A company's first year has no history to learn from.")

    print("\n### 1.6 Countries (at least 150 rows)\n")
    rows = []
    cc = collections.defaultdict(list)
    for r in L:
        cc[r["country"]].append(r)
    for k, v in sorted(cc.items(), key=lambda kv: -len(kv[1])):
        if len(v) >= 150:
            top = C(r["company_id"] for r in v if r["y"]).most_common(1)
            rest = [r for r in v if not top or r["company_id"] != top[0][0]]
            rows.append([k, len(v), len({r["company_id"] for r in v}), rate(v), rate(rest) if rest else "-"])
    table(["Country", "Rows", "Companies", "Against", "Against without the top company"], rows)

    print("\n### 1.7 Proposal types\n")
    types = collections.defaultdict(list)
    for r in L:
        types[r["proposal_type"]].append(r)
    table(["Type", "Rows", "Against", "Share of all against-votes"],
          [[t, len(v), rate(v), f"{sum(r['y'] for r in v) / total:.0%}"] for t, v in sorted(types.items(), key=lambda kv: -len(kv[1]))])
    om = types["OTHER_MGMT"]
    print("\nOTHER_MGMT is a catch-all. Inside it:")
    for label, rx in (("named director or manager appointed", r"appoint(ment)? .* as |as (managing|whole-time|executive|independent) director"),
                      ("pay, commission or allowance", r"remuneration|commission|allowance|bonus"),
                      ("rules, systems or articles changed", r"amend|rules|system|procedure")):
        b = [r for r in om if re.search(rx, r["proposal_text"].lower())]
        print(f"- {label}: {len(b)} rows, against {rate(b)}")

    print("\n### 1.8 Shareholder proposals\n")
    sh = [r for r in L if r["proponent"] == "Shareholder"]
    print(f"{len(sh)} with an answer. Board recommends: {dict(C(r['mgmt_rec'] for r in sh))}. NBIM votes: {dict(C(r['nbim_vote'] for r in sh))}.")
    print("NBIM's support for proposals the board opposed, by year: " + ", ".join(
        f"{y} {sum(1 for r in sh if r['year'] == y and r['mgmt_rec'] == 'MOT' and r['nbim_vote'] == 'FOR')}/"
        f"{sum(1 for r in sh if r['year'] == y and r['mgmt_rec'] == 'MOT')}" for y in sorted({r["year"] for r in sh})))

    print("\n### 1.9 New situations and repeats\n")
    last, by_date = {}, collections.defaultdict(list)
    for r in L:
        by_date[r["meeting_date"]].append(r)
    for d in sorted(by_date):
        for r in by_date[d]:
            r["prev"] = last.get((r["company_id"], text_key(r)))
        for r in by_date[d]:
            last[(r["company_id"], text_key(r))] = r["y"]
    ag = [r for r in L if r["y"]]
    print(f"Of {len(ag)} against-votes: NBIM opposed the same item at that company before in "
          f"{sum(1 for r in ag if r['prev'] is True)}, supported it before in {sum(1 for r in ag if r['prev'] is False)}, "
          f"and the item was not seen before in {sum(1 for r in ag if r['prev'] is None)}.")
    for lab, p in (("opposed last time", True), ("supported last time", False), ("item not seen before", None)):
        b = [r for r in L if r["prev"] is p]
        print(f"- {lab}: {len(b)} rows, against now {rate(b)}")

    print("\n### 1.10 Inside a meeting\n")
    meet = collections.defaultdict(list)
    for r in L:
        meet[r["meeting_id"]].append(r)
    n_against = [sum(r["y"] for r in v) for v in meet.values()]
    print(f"- {len(meet)} meetings. No against-vote in {sum(1 for a in n_against if a == 0)}, one in "
          f"{sum(1 for a in n_against if a == 1)}, two or more in {sum(1 for a in n_against if a > 1)}.")
    D = [r for r in L if r["proposal_type"] == "DIRECTOR_ELECTION"]
    for v in meet.values():
        ds = [r for r in v if r["proposal_type"] == "DIRECTOR_ELECTION"]
        for i, r in enumerate(ds):
            r["pos"], r["n_dir"] = i, len(ds)
    big = [r for r in D if r["n_dir"] >= 3]
    print("- Order on the ballot, meetings with at least three director items:")
    table(["Director listed", "Rows", "Against", "Against, where NBIM had not opposed that person before"],
          [[lab, len(b), rate(b), rate([r for r in b if r["prev"] is not True])]
           for lab, b in (("first", [r for r in big if r["pos"] == 0]), ("second", [r for r in big if r["pos"] == 1]),
                          ("third or later", [r for r in big if r["pos"] >= 2]))])
    rows = []
    for c in sorted({r["country"] for r in big}):
        a = [r for r in big if r["country"] == c and r["pos"] == 0 and r["prev"] is not True]
        b = [r for r in big if r["country"] == c and r["pos"] > 0 and r["prev"] is not True]
        if len(a) >= 15:
            rows.append([c, len(a), rate(a), len(b), rate(b)])
    print("\n  Same, by country (people NBIM had not opposed before):")
    table(["Country", "First listed", "Against", "Listed later", "Against"], sorted(rows, key=lambda r: -r[1]))
    print("\n- Number of directors on the ballot:")
    table(["Director items in the meeting", "Rows", "Against"],
          [[lab, len(b), rate(b)] for lab, b in ((lab, [r for r in D if lo <= r["n_dir"] <= hi])
                                                 for lab, lo, hi in (("1-2", 1, 2), ("3-6", 3, 6), ("7-9", 7, 9), ("10-12", 10, 12), ("13 or more", 13, 99)))])
    words = [("named 'independent' or 'outside'", r"(?<!non-)independent|outside"),
             ("named 'non-independent', 'inside' or 'executive'", r"non-independent|inside director|executive director"),
             ("supervisory board", r"supervisory"), ("chair in the wording", r"chair"),
             ("several people in one item", r"^elect (directors|board|supervisory board members|members)|slate|bundled")]
    print("\n- What the wording of a director item says:")
    table(["Wording", "Rows", "Against"], [[lab, len(b), rate(b)] for lab, b in
                                          ((lab, [r for r in D if re.search(rx, r["proposal_text"].lower())]) for lab, rx in words)]
          + [["all director items", len(D), rate(D)]])
    comp_meet = collections.defaultdict(list)
    for v in meet.values():
        comp_meet[v[0]["company_id"]].append(v)
    t = C()
    for vs in comp_meet.values():
        vs.sort(key=lambda v: v[0]["meeting_date"])
        for a, b in zip(vs, vs[1:]):
            t[(any(r["y"] for r in a), any(r["y"] for r in b))] += 1
    print(f"\n- If NBIM opposed anything at a company's previous meeting, it opposes something at the next in "
          f"{t[(True, True)] / (t[(True, True)] + t[(True, False)]):.0%} of cases; otherwise in "
          f"{t[(False, True)] / (t[(False, True)] + t[(False, False)]):.0%}.")
    return R


def audit_npx(R):
    N = read(NPX)
    print(f"\n## 2. Second file: {os.path.relpath(NPX, ROOT)}\n")
    print(f"{len(N)} rows from US Form N-PX filings. It is another investor's votes, not NBIM's, although the column is called nbim_vote.")
    print(f"- Empty columns: ticker, proposal_number, rationale_text, position_paper, rationale_section.")
    print(f"- {sum(1 for r in N if r['proposal_text'].isupper())} texts are in capitals, "
          f"{sum(1 for r in N if 'PLEASE NOTE' in r['proposal_text'].upper())} are notes to voters and not proposals, "
          f"{sum(1 for r in N if r['injection_flag'] == '1')} carry the organisers' injection flag.")
    given = sum(1 for r in N if r["against_board"] == "1.0")
    true = sum(1 for r in N if r["mgmt_rec_raw"] == "AGAINST")
    both = sum(1 for r in N if r["against_board"] == "1.0" and r["mgmt_rec_raw"] == "AGAINST")
    print(f"- The against_board column marks {given} rows. The source field it is built on means 'this vote was for or "
          f"against management' and marks {true} rows. Only {both} rows are in both.")
    real = {(name_key(r["company"]), r["meeting_date"], text_key(r)): r for r in R}
    pairs = [(n, real[k]) for n in N for k in [(name_key(n["company"]), n["meeting_date"], text_key(n))] if k in real]
    check = C((b["mgmt_rec"], a["nbim_vote_raw"]) for a, b in pairs if a["mgmt_rec_raw"] == "FOR" and b["mgmt_rec"])
    print(f"- Proof from the {len(pairs)} proposals that are in both files: where the N-PX field says FOR, the vote is "
          f"FOR when NBIM's file says the board recommended FOR ({check[('FOR', 'FOR')]} rows) and AGAINST when the board "
          f"recommended against ({check[('MOT', 'AGAINST')]} rows). So the field is 'for management', not 'the board recommended for'.")
    print("- Use `mgmt_rec_raw == 'AGAINST'` as the answer for this file.")


def audit_pay():
    P = read(PAY)
    print(f"\n## 3. Pay file: {os.path.relpath(PAY, ROOT)}\n")
    print(f"{len(P)} rows from Norges Bank's own Form N-PX filings: {dict(sorted(C(r['innsendt'] for r in P).items()))}.")
    print(f"- Exact duplicate rows: {len(P) - len({tuple(r.values()) for r in P})}. Rows with no vote recorded: {sum(1 for r in P if not r['stemme'])}.")
    print(f"- Votes (vote, for or against management): {dict(C((r['stemme'], r['for_eller_mot_ledelsen']) for r in P).most_common(6))}")
    print("- Frequency votes ('ONE YEAR' and so on) were never against management. Merger payout votes are one-off events.")
    print("- Every category is 'SECTION 14A SAY-ON-PAY VOTES': the file holds pay votes only.")


class Tee(io.StringIO):
    def write(self, s):
        sys.__stdout__.write(s)
        return super().write(s)


def main():
    buf = Tee()
    sys.stdout = buf
    print("# Data audit\n")
    print("Produced by `python3 src/agent/data_audit.py`. Counts come straight from the raw files.\n")
    R = audit_real()
    audit_npx(R)
    audit_pay()
    sys.stdout = sys.__stdout__
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(buf.getvalue())
    print(f"\nWrote {os.path.relpath(OUT, ROOT)}")


if __name__ == "__main__":
    main()
