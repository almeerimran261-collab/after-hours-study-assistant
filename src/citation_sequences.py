"""Check attribution for numeric lists that occur verbatim in retrieved text.

This is a narrow content check, not a general semantic entailment validator.
Lists absent from every retrieved passage may be derived or differently formatted;
this check makes no decision about those answers.
"""
from decimal import Decimal
import re


_NUMBER = r"[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
_NUMBER_PATTERN = re.compile(_NUMBER)
_SEPARATOR = r"(?:\s*[,;]\s*(?:and\s+)?|\s+and\s+|\s*(?:->|→)\s*)"
_LIST_PATTERN = re.compile(
    rf"(?<![\w.]){_NUMBER}(?:{_SEPARATOR}{_NUMBER}){{2,}}(?!\w|\.\d)",
    re.IGNORECASE,
)


def _lists(text):
    # Inline code formatting is common around array values.
    text = text.replace("`", "").replace("−", "-")
    return [
        tuple(Decimal(value.replace(",", ""))
              for value in _NUMBER_PATTERN.findall(match.group()))
        for match in _LIST_PATTERN.finditer(text)
    ]


def _location(hit):
    slide = hit.get("location_type") == "slide"
    return (str(hit["source"]).strip(), "slide" if slide else "page",
            int(hit["slide"] if slide else hit["page"]))


def _citation(match):
    return (match.group(1).strip(),
            "slide" if match.group(2).casefold() == "slide" else "page",
            int(match.group(3)))


def _label(location):
    source, kind, number = location
    return f"[{source}, {'slide' if kind == 'slide' else 'p.'} {number}]"


def _contains(sequence, candidates):
    size = len(sequence)
    return any(
        candidate[start:start + size] == sequence
        for candidate in candidates
        for start in range(len(candidate) - size + 1)
    )


def _claims(answer, citation_pattern):
    """Associate text with its following citation(s), preserving separate claims."""
    matches = list(citation_pattern.finditer(answer))
    cursor, index, previous = 0, 0, []
    while index < len(matches):
        first = last = matches[index]
        group = [_citation(first)]
        index += 1
        while index < len(matches) and re.fullmatch(
            r"[\s,;]*(?:and[\s,;]*)?", answer[last.end():matches[index].start()], re.I,
        ):
            last = matches[index]
            group.append(_citation(last))
            index += 1
        yield answer[cursor:first.start()], group
        cursor, previous = last.end(), group
    if previous and answer[cursor:].strip():
        # Also cover replies that put a citation before their final list.
        yield answer[cursor:], previous


def numeric_citation_mismatches(answer, retrieved_chunks, citation_pattern):
    """Return evidence-backed feedback for mismatches; never choose a new citation.

    Order, repeated values, source, and page-versus-slide identity are preserved.
    A literal sequence must occur in a retrieved passage before this check can
    flag an attributed citation. At least three values are required.
    """
    evidence = [(_location(hit), _lists(hit.get("text") or ""))
                for hit in retrieved_chunks]
    issues, seen = [], set()
    for claim, citations in _claims(answer, citation_pattern):
        for sequence in _lists(claim):
            supporting = {location for location, lists in evidence
                          if _contains(sequence, lists)}
            if not supporting:
                continue
            unsupported = set(citations) - supporting
            signature = (sequence, tuple(sorted(unsupported)), tuple(sorted(supporting)))
            if unsupported and signature not in seen:
                seen.add(signature)
                values = ", ".join(str(value) for value in sequence)
                issues.append(
                    f"The ordered list {values} occurs in "
                    + ", ".join(_label(location) for location in sorted(supporting))
                    + ", but not in the attributed "
                    + ", ".join(_label(location) for location in sorted(unsupported))
                    + "."
                )
    return issues


def repair_unique_numeric_citation(answer, retrieved_chunks, citation_pattern):
    """Correct only a single label, with one exact list and unique provenance.

    Ambiguous locations, multiple lists/citations, partial list matches,
    other documents, and a change between page and slide are not auto-repaired.
    Every character outside the citation remains exactly as generated.
    """
    matches = list(citation_pattern.finditer(answer))
    sequences = _lists(citation_pattern.sub("", answer))
    if len(matches) != 1 or len(sequences) != 1:
        return None
    sequence = sequences[0]
    supporting = {
        _location(hit) for hit in retrieved_chunks
        if sequence in _lists(hit.get("text") or "")
    }
    if len(supporting) != 1:
        return None
    target = next(iter(supporting))
    match = matches[0]
    current = _citation(match)
    if target[:2] != current[:2] or target == current:
        return None
    return answer[:match.start()] + _label(target) + answer[match.end():]
