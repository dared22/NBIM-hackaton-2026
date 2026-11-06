"""rules.guardrails: NBIM voting decision support."""

import collections
import re

# Text appended to the proposal. {VOTE} is FOR when the attacker wants the
# proposal waved through and AGAINST (MOT) in the mirrored test.

# Guardrail patterns: wording that a ballot item has no reason to contain.
PATTERNS = [
    (
        "tells the reader to ignore rules",
        r"\b(ignore|disregard|override|forget|ignorer|overse)\b[^.]{0,80}\b(guideline|rule|instruction|polic|previous|retningslinj|regl|instruks)",
    ),
    (
        "talks about the voter or its rulebook",
        r"\b(nbim|norges bank investment|voting guidelines?|position paper|compliance note|system prompt|pre-?approved)\b",
    ),
    (
        "gives a voting order",
        r"\b(recommend|anbefal)\s+(for|against|mot)\b|\bvote\s+(for|against)\s*[.!\]]*\s*$",
    ),
]


def guard_patterns(text):
    """Names of the guardrail patterns the text triggers."""
    return [name for name, rx in PATTERNS if re.search(rx, text, re.I)]


LOWER_WORD = re.compile(r"(?<![A-Za-z'’.-])[a-z]{4,}(?![A-Za-z'’-])")
NEW_LOWER, NEW_ANY = 2, 5


def ballot_vocabulary(earlier_texts):
    """Words of four letters or more found in at least three earlier ballot texts:
    (written in lower case, written in any case)."""
    lower, anycase = collections.Counter(), collections.Counter()
    for text in earlier_texts:
        lower.update(set(LOWER_WORD.findall(text)))
        anycase.update(set(re.findall(r"[a-z]{4,}", text.lower())))
    return {w for w, n in lower.items() if n >= 3}, {w for w, n in anycase.items() if n >= 3}


def unusual_wording(text, vocabulary):
    """The words that make a text read unlike a ballot item, or [] if it reads like one.

    Ballot items are titles ("Elect Director Jane Doe", "Approve Remuneration Report"): capitalised
    words and a small set of connecting words. Running prose is not. A text is unusual when it holds
    two or more lower-case words that no earlier ballot used in lower case, or five or more words
    that no earlier ballot used at all (a new name brings one or two, a planted sentence more).
    No list of trigger words is involved, so a reworded instruction is caught like any other sentence.
    """
    lower, anycase = vocabulary
    new_lower = [w for w in LOWER_WORD.findall(text) if w not in lower]
    if len(new_lower) >= NEW_LOWER:
        return new_lower
    new_any = [w for w in re.findall(r"[a-z]{4,}", text.lower()) if w not in anycase]
    return new_any if len(new_any) >= NEW_ANY else []


def restore_known_items(test, train):
    """If a proposal's text is a known item plus extra words, use the known item.

    Known = text this company has voted on before, or generic wording seen at
    least five times across companies. Returns the number of rows changed.
    """
    by_company = collections.defaultdict(set)
    counts = collections.Counter()
    for r in train:
        by_company[r["company_id"]].add(r["text_key"])
        counts[r["text_key"]] += 1
    generic = {t for t, n in counts.items() if n >= 5}
    changed = 0
    for r in test:
        key = r["text_key"]
        if key in by_company[r["company_id"]] or key in counts:
            continue
        padded = " " + key + " "
        hits = [
            t
            for t in by_company[r["company_id"]] | generic
            if len(t) >= 12 and " " + t + " " in padded
        ]
        if hits:
            r["text_key"] = max(hits, key=len)
            r["restored"] = True
            changed += 1
    return changed
