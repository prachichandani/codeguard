from agent import (DAILY_LIMIT_HIT, MODEL, SAFETY_MARGIN, RequestTooLarge, create_with_retry, estimate_tokens,
                   get_client, parse_json_object, tpm_limit)
from events import emit
from evidence import check_evidence

JUDGE_MAX_TOKENS = 2500

JUDGE_PROMPT = """You are the Judge in a team of code auditors. Specialist agents
submitted findings. Each finding comes with the ACTUAL code around the location
it cites (already confirmed to exist). Lines the finding cites are marked with
">"; the other lines are surrounding context from the same function/class, and
count as evidence too. Decide for each finding:

- accept: the code shown clearly has the stated problem.
- reject: the code shown does not have the problem; or the claim is speculative
  ("could", "might", "if X were..."); or it is generic advice not tied to a
  defect in this code (e.g. "add rate limiting"); or it is not a problem at all.
- duplicate: same underlying problem at the same place as another finding.
  Set duplicate_of to the id of the one to keep (keep the clearest one).

Some findings are marked QUOTE MISMATCH: the code the agent quoted does not exist
at that location (it probably guessed). Ignore its quote and explanation details
entirely; accept ONLY if the real code shown has the stated problem by itself.
Agents often wrongly assume that similar functions share a bug - check each one.

Judge only from the code shown. Reply with ONLY this JSON object:
{"verdicts": [{"id": "F1", "decision": "accept|reject|duplicate",
  "duplicate_of": null, "reason": "one sentence"}]}
Give exactly one verdict per finding id."""


def _describe(f: dict) -> str:
    mismatch = ("QUOTE MISMATCH: the agent's quoted code was not found here; judge only the real code below.\n"
                if f.get("quote_mismatch") else "")
    return (
        f"## {f['id']} (from {f['specialist']} specialist)\n{mismatch}"
        f"Title: {f.get('title')}\nSeverity: {f.get('severity')}\n"
        f"Location: {f.get('file_path')} lines {f.get('start_line')}-{f.get('end_line')}\n"
        f"Explanation: {f.get('explanation')}\n"
        f"Code around that location:\n```\n{f['code_shown']}\n```"
    )


def _batches(candidates: list[dict]) -> list[list[dict]]:
    # Each judge request must fit the per-minute token limit. Findings in the same
    # file go in the same batch where possible, so duplicates can be spotted.
    budget = tpm_limit() - JUDGE_MAX_TOKENS - SAFETY_MARGIN - estimate_tokens(JUDGE_PROMPT)
    by_file: dict[str, list[dict]] = {}
    for f in candidates:
        key = str(f.get("file_path", "")).replace("\\", "/").lower()
        by_file.setdefault(key, []).append(f)

    batches, current, used = [], [], 0
    for group in by_file.values():
        for f in group:
            size = estimate_tokens(_describe(f))
            if current and used + size > budget:
                batches.append(current)
                current, used = [], 0
            current.append(f)
            used += size
    if current:
        batches.append(current)
    return batches


def _ask_judge(batch: list[dict]) -> dict[str, dict]:
    try:
        response = create_with_retry(
            get_client(),
            "[judge] ",
            model=MODEL,
            messages=[
                {"role": "system", "content": JUDGE_PROMPT},
                {"role": "user", "content": "\n\n".join(_describe(f) for f in batch)},
            ],
            response_format={"type": "json_object"},
            max_tokens=JUDGE_MAX_TOKENS,
        )
    except RequestTooLarge:
        if len(batch) == 1:
            return {}
        mid = len(batch) // 2
        return {**_ask_judge(batch[:mid]), **_ask_judge(batch[mid:])}
    data = parse_json_object(response.choices[0].message.content) or {}
    return {v["id"]: v for v in data.get("verdicts", []) if isinstance(v, dict) and "id" in v}


def judge(collection, findings: list[dict]) -> dict:
    accepted, rejected, candidates = [], [], []

    # Stage 1: evidence check
    for i, finding in enumerate(findings, 1):
        finding = {**finding, "id": f"F{i}"}
        ok, reason, code_shown = check_evidence(collection, finding)
        if ok:
            candidates.append({**finding, "code_shown": code_shown})
        elif code_shown:
            # The location is real but the quote isn't (agents reconstruct code they no
            # longer have in context). Don't discard the claim: the judge checks it
            # against the real code, which made-up code can't get past.
            candidates.append({**finding, "code_shown": code_shown, "quote_mismatch": True,
                               "mismatch_reason": reason})
        else:
            rejected.append({**finding, "rejected_by": "evidence check", "reason": reason})
    mismatches = sum(1 for f in candidates if f.get("quote_mismatch"))
    print(f"[judge] evidence check: {len(candidates)} passed ({mismatches} with an inaccurate quote, "
          f"checked against the real code), {len(rejected)} rejected")
    emit("judge_evidence", passed=len(candidates), rejected=len(rejected), quote_mismatches=mismatches,
         results=[{"id": f["id"], "agent": f.get("specialist"), "title": f.get("title"), "ok": False,
                   "reason": f["reason"]} for f in rejected]
                 + [{"id": f["id"], "agent": f.get("specialist"), "title": f.get("title"), "ok": True,
                     "quote_mismatch": bool(f.get("quote_mismatch"))} for f in candidates])
    if not candidates:
        return {"accepted": accepted, "rejected": rejected}

    # Stage 2: LLM review of what survived, in batches that fit the token limit
    verdicts: dict[str, dict] = {}
    for batch in _batches(candidates):
        try:
            verdicts.update(_ask_judge(batch))
        except Exception as e:
            print(f"[judge] review failed for {len(batch)} findings: {e}")

    by_id = {f["id"]: f for f in candidates}
    dup_of: dict[str, str] = {}
    for f in candidates:
        v = verdicts.get(f["id"])
        if v is None and f.get("quote_mismatch"):
            # Its quote was wrong, so without the judge's review nothing supports it
            rejected.append({**f, "rejected_by": "judge", "reason": "inaccurate quote and not reviewed by judge"})
        elif v is None:
            # Don't silently drop a finding with real evidence just because the judge skipped it
            why = "daily token limit reached" if DAILY_LIMIT_HIT.is_set() else "judge skipped it"
            accepted.append({**f, "judge_reason": f"not reviewed by judge ({why}); quoted evidence verified",
                             "also_reported_by": [], "unreviewed": True})
        elif v.get("decision") == "reject":
            rejected.append({**f, "rejected_by": "judge", "reason": v.get("reason", "")})
        elif v.get("decision") == "duplicate" and v.get("duplicate_of") in by_id and v.get("duplicate_of") != f["id"]:
            dup_of[f["id"]] = v["duplicate_of"]
        else:
            accepted.append({**f, "judge_reason": v.get("reason", ""), "also_reported_by": []})

    # Merge duplicates into the finding they (eventually) duplicate: follow chains
    # like F3 -> F2 -> F1 to the root, stopping on cycles.
    accepted_by_id = {f["id"]: f for f in accepted}
    rejected_ids = {f["id"] for f in rejected}
    for fid, target in dup_of.items():
        f = by_id[fid]
        seen = {fid}
        while target in dup_of and target not in seen:
            seen.add(target)
            target = dup_of[target]
        if target in seen:
            target = min(seen)  # cycle: pick one member consistently as the keeper
        keeper = accepted_by_id.get(target)
        if target == fid and keeper is not None:
            continue  # cycle keeper, already accepted while merging another member
        if keeper is not None:
            keeper["also_reported_by"].append(f["specialist"])
            rejected.append({**f, "rejected_by": "judge", "reason": f"duplicate of {keeper['id']}"})
        elif target in rejected_ids:
            rejected.append({**f, "rejected_by": "judge", "reason": f"duplicate of rejected {target}"})
        elif target == fid:
            # This finding is the chosen keeper of a cycle: accept it
            keeper = {**f, "judge_reason": verdicts[fid].get("reason", ""), "also_reported_by": []}
            accepted.append(keeper)
            accepted_by_id[fid] = keeper
        else:
            # Root is a cycle keeper not processed yet: accept it now, then merge into it
            root = by_id[target]
            keeper = {**root, "judge_reason": verdicts[target].get("reason", ""), "also_reported_by": [f["specialist"]]}
            accepted.append(keeper)
            accepted_by_id[target] = keeper
            rejected.append({**f, "rejected_by": "judge", "reason": f"duplicate of {target}"})

    print(f"[judge] review: {len(accepted)} accepted, {len(rejected)} rejected in total")
    emit("judge_done", accepted=len(accepted), rejected=len(rejected))
    return {"accepted": accepted, "rejected": rejected}
