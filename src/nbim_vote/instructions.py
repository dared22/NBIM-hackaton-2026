"""The filter for text that addresses the reader instead of describing a proposal.

Its own module so that every place that reads proposal text (Jev's input, history matching,
company facts) can strip the same instructions without importing jev_mvp.
"""

import re

# Words that appear in none of the 5,110 distinct proposal texts in real_votes.csv. Phrases
# like "vote for" and "guidelines" do appear in real proposals, so they are left out.
# This covers proposal text only: filings say "recommend" constantly.
INSTRUCTION = re.compile(
    r"\b(?:IMPORTANT|NOTE|ATTENTION|WARNING|INSTRUCTIONS?)\s*:"
    r"|(?i:\b(?:ignore|disregard|override|bypass|forget|recommend\w*|you (?:must|should|are)"
    r"|your (?:task|answer|output|recommendation)|system prompt|assistant)\b)[^.!?]*[.!?]?"
)


def has_instruction(text):
    return bool(INSTRUCTION.search(text))


def strip_instructions(text):
    """The proposal without text that addresses the reader. Real proposals come through unchanged."""
    if not has_instruction(text):
        return text
    return re.sub(r"\s+", " ", INSTRUCTION.sub(" ", text)).strip()
