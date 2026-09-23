import re
from agent import MODEL, MAX_TOKENS, get_client, create_with_retry, parse_json_object
from vectorstore import code_at_lines

MAX_CITED_LINES = 40  # code shown to the judge per finding

JUDGE_PROMPT = """You are the Judge in a team of code auditors. Specialist agents
submitted findings. Each finding comes with the ACTUAL code at the location it
cites (already confirmed to exist). Decide for each finding:

- accept: the code shown clearly has the stated problem.
- reject: the code shown does not have the problem; or the claim is speculative
  ("could", "might", "if X were..."); or it is generic advice not tied to a
  defect in this code (e.g. "add rate limiting"); or it is not a problem at all.
- duplicate: same underlying problem at the same place as another finding.
  Set duplicate_of to the id of the one to keep (keep the clearest one).

Judge only from the code shown. Reply with ONLY this JSON object:
{"verdicts": [{"id": "F1", "decision": "accept|reject|duplicate",
  "duplicate_of": null, "reason": "one sentence"}]}
Give exactly one verdict per finding id."""


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def check_evidence(collection, finding: dict) -> tuple[bool, str, str]:
    # Deterministic check, no LLM: does the cited location exist in the index,
    # and does the quoted evidence actually appear in that code?
    # Returns (ok, reason, code at the cited lines).
    try:
        start = int(finding["start_line"])
        end = int(finding.get("end_line") or start)
    except (KeyError, TypeError, ValueError):
        return False, "missing or invalid line numbers", ""

    located = code_at_lines(collection, str(finding.get("file_path", "")), start, end)
    if located is None:
        return False, "cited file/lines not found in the indexed code", ""
    cited_code, entity_code = located

    # Models abbreviate quotes with "..." - each remaining fragment must be real code
    evidence = str(finding.get("evidence") or "")
    fragments = [f for f in (_normalize(p) for p in re.split(r"\.\.\.|…", evidence)) if len(f) >= 4]
    if not fragments:
        return False, "no code quoted as evidence", cited_code
    haystack = _normalize(entity_code)
    missing = [f for f in fragments if f not in haystack]
    if missing:
        return False, f"quoted evidence not found at the cited location: {missing[0][:80]!r}", cited_code
    return True, "evidence matches the code", cited_code


def _ask_judge(candidates: list[dict]) -> dict[str, dict]:
    listing = []
    for f in candidates:
        code = "\n".join(f["cited_code"].splitlines()[:MAX_CITED_LINES])
        listing.append(
            f"## {f['id']} (from {f['specialist']} specialist)\n"
            f"Title: {f.get('title')}\nSeverity: {f.get('severity')}\n"
            f"Location: {f.get('file_path')} lines {f.get('start_line')}-{f.get('end_line')}\n"
            f"Explanation: {f.get('explanation')}\n"
            f"Actual code at that location:\n```\n{code}\n```"
        )
    response = create_with_retry(
        get_client(),
        "[judge] ",
        model=MODEL,
        messages=[
            {"role": "system", "content": JUDGE_PROMPT},
            {"role": "user", "content": "\n\n".join(listing)},
        ],
        response_format={"type": "json_object"},
        max_tokens=MAX_TOKENS,
    )
    data = parse_json_object(response.choices[0].message.content) or {}
    return {v["id"]: v for v in data.get("verdicts", []) if isinstance(v, dict) and "id" in v}


def judge(collection, findings: list[dict]) -> dict:
    accepted, rejected, candidates = [], [], []

    # Stage 1: evidence check
    for i, finding in enumerate(findings, 1):
        finding = {**finding, "id": f"F{i}"}
        ok, reason, cited_code = check_evidence(collection, finding)
        if ok:
            candidates.append({**finding, "cited_code": cited_code})
        else:
            rejected.append({**finding, "rejected_by": "evidence check", "reason": reason})
    print(f"[judge] evidence check: {len(candidates)} passed, {len(rejected)} rejected")
    if not candidates:
        return {"accepted": accepted, "rejected": rejected}

    # Stage 2: LLM review of what survived
    verdicts = _ask_judge(candidates)
    by_id = {f["id"]: f for f in candidates}
    duplicates = []
    for f in candidates:
        v = verdicts.get(f["id"])
        if v is None:
            # Don't silently drop a finding with real evidence just because the judge skipped it
            accepted.append({**f, "judge_reason": "not reviewed by judge (evidence verified)"})
        elif v.get("decision") == "reject":
            rejected.append({**f, "rejected_by": "judge", "reason": v.get("reason", "")})
        elif v.get("decision") == "duplicate" and v.get("duplicate_of") in by_id and v.get("duplicate_of") != f["id"]:
            duplicates.append((f, v))
        else:
            accepted.append({**f, "judge_reason": v.get("reason", ""), "also_reported_by": []})

    # Merge duplicates into the finding they duplicate, if that one was accepted
    accepted_by_id = {f["id"]: f for f in accepted}
    for f, v in duplicates:
        keeper = accepted_by_id.get(v["duplicate_of"])
        if keeper is not None:
            keeper.setdefault("also_reported_by", []).append(f["specialist"])
            rejected.append({**f, "rejected_by": "judge", "reason": f"duplicate of {keeper['id']}"})
        else:
            accepted.append({**f, "judge_reason": v.get("reason", ""), "also_reported_by": []})

    print(f"[judge] review: {len(accepted)} accepted, {len(rejected)} rejected in total")
    return {"accepted": accepted, "rejected": rejected}
