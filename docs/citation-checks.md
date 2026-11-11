# Numeric-list citation checks

A manual Trees.pptx check found a correct registration-ID sequence attributed to
slide 30 even though its retrieved passage was labeled slide 29. Retrieval and
slide metadata were correct; the cited slide was also in the retrieved set, so
membership validation alone accepted the wrong attribution.

The numeric-list check flags an ordered list of at least three values when it
occurs in retrieved text but is attributed to a location that does not contain it.
It preserves order, repeated values, source identity, and page-versus-slide type.

## Citation-only correction

A model rewrite was tested first. The user's local model changed `60` into `6.0`
while fixing the citation. The value-preservation guard blocked that reply. The
rewrite step has now been removed.

Correction can change only the citation label. It requires one recognized
citation, one numeric list, and exactly one retrieved location containing that
entire ordered numeric list. Duplicate chunks at the same location are allowed.
The target must be in the same document and use the same page/slide type as the
original citation. Every character outside the citation stays unchanged. The
corrected result passes the citation validator and numeric check again before
it is shown. The original cleaned model draft remains available in diagnostics.

Ambiguous locations, partial-list matches, multiple lists/citations, another
document, or a page-to-slide change are not auto-corrected. Detected unresolved
mismatches return the refusal with diagnostic `citation_numeric_sequence_mismatch`.
No extra generation request is made and retrieval rank is not used to select a
replacement label.

This is a narrow attribution check, not general semantic verification. Initial
model answers can still contain factual errors. Lists absent from all retrieved
passages, derived values, some formatting/OCR differences, diagrams, and arbitrary
prose are outside this guard's scope. Exact numeric overlap alone does not prove
all surrounding prose, so source review remains necessary.

## Checks

`python -m unittest discover -s tests -v` includes the reported `60` to `6.0` risk,
byte-for-byte preservation outside the corrected label, exact list ordering,
repeated values, ambiguous locations, source/type restrictions, and a supporting
PDF page that is not the first-ranked hit.

`python -m eval.citation_repair_smoke_test` is now a deterministic regression
check with an injected draft and two authored passages. It makes no model/API
requests. It proves the label changes without changing the original answer; it
is not a retrieval, model-answer-accuracy, or general-grounding benchmark.
