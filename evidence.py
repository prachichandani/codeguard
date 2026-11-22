import re
from vectorstore import code_at_lines

MAX_SHOWN_LINES = 40  # code shown to the judge per finding

# Tool results show code as "  41| code"; models sometimes copy those prefixes
_LINE_PREFIX = re.compile(r"^\s*\d+\s*\|\s?", re.MULTILINE)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _code_window(entity_code: str, entity_start: int, start: int, end: int) -> str:
    # The enclosing function/class around the cited lines (not just the cited
    # lines - agents' line ranges are often slightly off, and the judge needs
    # context). Numbered; cited lines are marked with ">".
    lines = entity_code.splitlines()
    n = len(lines)
    s = max(start, entity_start) - entity_start
    e = min(end, entity_start + n - 1) - entity_start
    if n <= MAX_SHOWN_LINES:
        lo, hi = 0, n - 1
    elif e - s + 1 >= MAX_SHOWN_LINES:
        lo, hi = s, s + MAX_SHOWN_LINES - 1
    else:
        lo = max(0, s - (MAX_SHOWN_LINES - (e - s + 1)) // 2)
        hi = min(n - 1, lo + MAX_SHOWN_LINES - 1)
        lo = max(0, hi - MAX_SHOWN_LINES + 1)
    return "\n".join(
        f"{'>' if s <= i <= e else ' '}{entity_start + i:5d}| {lines[i]}" for i in range(lo, hi + 1)
    )


def check_evidence(collection, finding: dict) -> tuple[bool, str, str]:
    # Deterministic check, no LLM: does the cited location exist in the index,
    # and does the quoted evidence actually appear in that code?
    # Returns (ok, reason, code around the cited lines for the judge).
    try:
        start = int(finding["start_line"])
        end = int(finding.get("end_line") or start)
    except (KeyError, TypeError, ValueError):
        return False, "missing or invalid line numbers", ""
    if end < start:
        start, end = end, start

    located = code_at_lines(collection, str(finding.get("file_path", "")), start, end)
    if located is None:
        return False, "cited file/lines not found in the indexed code", ""
    _, entity_code, entity_start = located
    shown = _code_window(entity_code, entity_start, start, end)

    # Models abbreviate quotes with "..." - each remaining fragment must be real code
    # Models sometimes write line breaks as a literal backslash-n; make them real
    # first, or the line-number prefixes after them can't be stripped
    evidence = str(finding.get("evidence") or "").replace("\\n", "\n")
    evidence = _LINE_PREFIX.sub("", evidence)
    fragments = [f for f in (_normalize(p) for p in re.split(r"\.\.\.|…", evidence)) if len(f) >= 4]
    if not fragments:
        return False, "no code quoted as evidence", shown
    haystack = _normalize(entity_code)
    missing = [f for f in fragments if f not in haystack]
    if missing:
        return False, f"quoted evidence not found at the cited location: {missing[0][:80]!r}", shown
    return True, "evidence matches the code", shown
