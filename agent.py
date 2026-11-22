import os
import re
import json
import time
import threading
from groq import (Groq, APIConnectionError, APIStatusError, BadRequestError,
                  InternalServerError, RateLimitError)
from events import agent_from_prefix, emit
from evidence import check_evidence
from tools import TOOL_SCHEMAS, execute_tool

MODEL = "openai/gpt-oss-120b"
MAX_ITERATIONS = 10
MAX_RETRIES = 5          # for errors other than rate limits (bad model output, server/network errors)
MAX_TOTAL_WAIT = 600     # seconds one request may spend waiting on rate limits before giving up
STEP_MAX_TOKENS = 2000   # reply budget for a tool-calling step (gpt-oss spends part on reasoning)
FINAL_MAX_TOKENS = 3000  # reply budget for the final report
DEFAULT_RETRY_WAIT = 20  # seconds, if Groq doesn't send retry-after
MAX_RETRY_WAIT = 120     # longer than this is a daily quota, not a per-minute one: give up
MAX_FULL_RESULTS = 3     # tool results kept with full code; older ones become location-only summaries
# Appended to results that show code. Agents tend to save findings for the end,
# by which time the code has been removed from their context and they guess it.
CODE_TOOLS = ("symbol_search", "semantic_search", "text_search")
REPORT_NOW_HINT = ("\n[If this code shows a problem in your focus area, call report_finding NOW "
                   "while the code is in front of you - older code is removed from your context.]")
REPLY_RESERVE = 800     # Groq counts only part of max_tokens up front; measured ~700
# Groq counts input tokens + max_tokens against the per-minute limit, and a single
# request above the limit fails outright (413). Free tier for gpt-oss-120b: 8000.
DEFAULT_TPM_LIMIT = 8000
SAFETY_MARGIN = 300
# Groq transient model-output errors that usually succeed on a second try
RETRYABLE_400_CODES = ("output_parse_failed", "tool_use_failed")

# Shared by every agent (single auditor and specialists): tools + evidence rules
TOOL_RULES = """You have these tools over a codebase:
- text_search: exact text / regex search, like grep. Best for concrete code
  patterns ('execute(', 'md5', 'autoescape', 'except:', 'debug=True').
- semantic_search: find code by describing behaviour in a full phrase
  ('building SQL queries from user input'). Don't pass single keywords.
- symbol_search: read a specific function/class by name, with line numbers.
- graph_traversal: who calls a function (callers) or what it calls (callees),
  to trace how data and control flow between functions.
- report_finding: record a confirmed problem. Call it as soon as you've seen
  the problematic code - older tool results are shortened to save space, so
  report while the code is still in front of you.

Investigate with targeted searches. Only report actual problems you have
evidence for: no positive notes, no generic advice ("consider adding rate
limiting") that isn't tied to a specific defect in the code you saw.

For report_finding: file_path and line numbers must come from tool results
(code lines are shown as "41| code" - use those numbers, never invent them).
evidence is the problematic code copied verbatim, without the "41| " prefixes.

When you have nothing more to investigate, stop calling tools and reply with
a one-line summary."""

SYSTEM_PROMPT = "You are a code security and quality auditor. " + TOOL_RULES

# Final report: a separate prompt that never mentions tools. With the tool-using
# prompt and a long tool history, gpt-oss often answers with a tool call even when
# no tools are offered ("Tool choice is none, but model called a tool").
REPORT_SYSTEM_PROMPT = (
    "You are a code auditor writing up an investigation that is already finished. "
    "No tools exist in this step. Using only the notes provided, write the final "
    "report as a single JSON object and nothing else."
)
# Tried in order for the final report; it fails randomly, so retry, then switch model.
FINAL_REPORT_MODELS = [MODEL, MODEL, "qwen/qwen3.8-27b"]

DEFAULT_TASK = (
    "Investigate this codebase for security issues, bad practices, and "
    "architectural problems. Look at authentication/session handling, user "
    "input, database access, and file operations. Report each confirmed "
    "problem with report_finding."
)

FINAL_PROMPT = (
    "Search budget used up. If you confirmed problems that you have NOT yet "
    "reported with report_finding, reply with ONLY this JSON object listing them:\n"
    '{"findings": [{"title": "...", "severity": "low|medium|high", '
    '"file_path": "...", "start_line": 0, "end_line": 0, '
    '"evidence": "verbatim code", "explanation": "..."}]}\n'
    "Rules:\n"
    "- Only report a problem if the notes above show its actual code. Results marked "
    "'[already read, code removed...]' list locations only - do not reconstruct code "
    "from memory; skip a finding rather than guess its code.\n"
    "- Report each function only for what you saw in it. Do not assume that similar "
    "functions (e.g. other methods of the same class) have the same bug.\n"
    "- evidence must be copied exactly from the notes, without the '41| ' prefixes.\n"
    'If everything is already reported, or nothing qualifies, reply {"findings": []}.'
)


REPO_MAP_HEADER = (
    "\n\nHow to start: below is a map of every file and its functions/classes. "
    "BEFORE any pattern search, pick the 3-5 functions whose names or files suggest "
    "problems in YOUR focus area (e.g. names with auth, login, verify, token, password, "
    "upload, load, query, search, admin, config, error, or anything named 'insecure'/'unsafe'/'raw') "
    "and read them with symbol_search. Generic searches for patterns that may not exist "
    "here (e.g. 'pickle' or 'eval' when nothing suggests them) waste your limited steps.\n"
    "Repository map:\n"
)


class RequestTooLarge(Exception):
    """A single request exceeds the tokens-per-minute limit (HTTP 413)."""


class DailyLimitReached(Exception):
    """Groq's per-day quota is used up. Waiting or retrying can't help, so the
    whole audit stops (every agent shares the same quota)."""

    def __init__(self, message: str, resets_in: float | None):
        super().__init__(message)
        self.resets_in = resets_in


# Set once any agent hits the daily limit, so the others stop at their next request
# instead of each waiting, retrying and spending a "salvage" report on an empty quota.
DAILY_LIMIT_HIT = threading.Event()
_daily_limit_info: dict = {}


def _daily_limit(e: RateLimitError) -> DailyLimitReached | None:
    # Groq's message names the limit: "... on tokens per day (TPD): Limit 200000 ..."
    msg = str(e)
    if "per day" not in msg and "(TPD)" not in msg and "(RPD)" not in msg:
        return None
    resets_in = None
    m = re.search(r"try again in (?:(\d+)h)?(?:(\d+)m)?(?:([\d.]+)s)?", msg)
    if m and any(m.groups()):
        h, mins, s = (float(g) if g else 0.0 for g in m.groups())
        resets_in = h * 3600 + mins * 60 + s
    return DailyLimitReached(msg, resets_in)


def get_client() -> Groq:
    return Groq(api_key=os.environ["GROQ_API_KEY"], max_retries=0)  # we retry ourselves


def tpm_limit() -> int:
    return int(os.environ.get("GROQ_TPM_LIMIT", DEFAULT_TPM_LIMIT))


def estimate_tokens(obj) -> int:
    # Rough and deliberately pessimistic (code + JSON escaping is ~3 chars/token).
    text = obj if isinstance(obj, str) else json.dumps(obj, ensure_ascii=False)
    return len(text) // 3 + 1


def _error_code(e: APIStatusError) -> str:
    body = e.body if isinstance(e.body, dict) else {}
    err = body.get("error", body)
    return str(err.get("code", "")) if isinstance(err, dict) else ""


class TokenBudget:
    """Groq's tokens-per-minute budget, shared by all agents (they run in parallel
    threads). Agents wait here for their turn instead of all firing at once and
    burning retries on 429s. Groq's response headers tell us the real remaining
    budget; between responses we assume it refills evenly over a minute."""

    def __init__(self):
        self.lock = threading.Lock()
        self.available: float | None = None  # unknown until the first response
        self.updated = 0.0

    def _now_available(self, now: float) -> float | None:
        if self.available is None:
            return None
        return min(tpm_limit(), self.available + (now - self.updated) * tpm_limit() / 60)

    def acquire(self, need: int, prefix: str) -> float:
        # Blocks until `need` tokens are available, reserves them. Returns seconds waited.
        need = min(need, tpm_limit())
        waited = 0.0
        while True:
            with self.lock:
                now = time.time()
                avail = self._now_available(now)
                if avail is None or avail >= need:
                    if avail is not None:
                        self.available, self.updated = avail - need, now
                    return waited
                wait = (need - avail) / (tpm_limit() / 60) + 0.5
            if waited == 0:
                print(f"{prefix}  Waiting {wait:.0f}s for the token budget...")
                _ev(prefix, "budget_wait", seconds=round(wait, 1))
            time.sleep(wait)
            waited += wait

    def update(self, headers):
        try:
            remaining = float(headers["x-ratelimit-remaining-tokens"])
        except (KeyError, TypeError, ValueError):
            return
        with self.lock:
            self.available, self.updated = remaining, time.time()

    def exhausted(self):
        # After a 429: treat the budget as empty so other agents back off too
        with self.lock:
            self.available, self.updated = 0.0, time.time()


BUDGET = TokenBudget()


def _ev(prefix: str, type_: str, **data):
    # Dashboard event attributed to the agent named in the log prefix
    emit(type_, agent=agent_from_prefix(prefix), **data)


def create_with_retry(client, prefix="", **kwargs):
    # Waits for the shared token budget, then sends. Retries rate limits (for up to
    # MAX_TOTAL_WAIT seconds in total), network/server errors, and Groq's transient
    # "model output couldn't be parsed" 400s.
    need = estimate_tokens(kwargs["messages"]) + estimate_tokens(kwargs.get("tools", [])) + REPLY_RESERVE
    waited, errors = 0.0, 0

    def retry_or_raise(e, message, sleep=0.0):
        nonlocal errors
        errors += 1
        if errors > MAX_RETRIES:
            raise e
        print(f"{prefix}  {message}, retrying ({errors}/{MAX_RETRIES})...")
        _ev(prefix, "retry", message=message, attempt=errors, of=MAX_RETRIES)
        time.sleep(sleep)

    while True:
        if DAILY_LIMIT_HIT.is_set():
            raise DailyLimitReached("daily token limit already reached by another agent",
                                    _daily_limit_info.get("resets_in"))
        waited += BUDGET.acquire(need, prefix)
        try:
            raw = client.chat.completions.with_raw_response.create(**kwargs)
            BUDGET.update(raw.headers)
            parsed = raw.parse()
            usage = getattr(parsed, "usage", None)
            _ev(prefix, "llm_call", model=kwargs.get("model"),
                prompt_tokens=getattr(usage, "prompt_tokens", None),
                completion_tokens=getattr(usage, "completion_tokens", None),
                remaining=raw.headers.get("x-ratelimit-remaining-tokens"),
                limit=raw.headers.get("x-ratelimit-limit-tokens"))
            return parsed
        except RateLimitError as e:
            daily = _daily_limit(e)
            if daily is not None:
                if not DAILY_LIMIT_HIT.is_set():
                    DAILY_LIMIT_HIT.set()
                    _daily_limit_info.update(resets_in=daily.resets_in)
                    mins = f" (about {daily.resets_in / 60:.0f} min until enough is freed)" if daily.resets_in else ""
                    print(f"{prefix}  Daily Groq token limit reached{mins}. Stopping the audit.")
                    emit("quota_exhausted", agent=agent_from_prefix(prefix), limit="tokens per day",
                         resets_in=daily.resets_in, message=str(e)[:400])
                raise daily from e
            BUDGET.exhausted()
            wait = float(e.response.headers.get("retry-after", DEFAULT_RETRY_WAIT))
            if wait > MAX_RETRY_WAIT or waited + wait > MAX_TOTAL_WAIT:
                raise
            print(f"{prefix}  Rate limited, waiting {wait:.0f}s...")
            _ev(prefix, "budget_wait", seconds=round(wait, 1), rate_limited=True)
            time.sleep(wait)
            waited += wait
        except BadRequestError as e:
            code = _error_code(e)
            if code not in RETRYABLE_400_CODES or "tool choice is none" in str(e).lower():
                raise  # the latter fails the same way every time: retrying only wastes time
            retry_or_raise(e, f"Model output error ({code})")
        except InternalServerError as e:
            retry_or_raise(e, f"Groq server error {e.status_code}", sleep=5)
        except APIConnectionError as e:  # includes timeouts
            retry_or_raise(e, f"Connection problem ({type(e).__name__})", sleep=5 * (errors + 1))
        except APIStatusError as e:
            if e.status_code == 413:
                raise RequestTooLarge(str(e)) from e
            raise


# ---------- keeping requests small ----------

def _summarize_result(tool_name: str, result) -> str:
    # Short stand-in for a tool result the model has already read.
    def loc(h):
        cls = f"{h['parent_class']}." if h.get("parent_class") else ""
        return f"{h['file_path']}::{cls}{h['name']} (lines {h['start_line']}-{h['end_line']})"

    if isinstance(result, list):
        body = "; ".join(loc(h) for h in result) or "no results"
    elif isinstance(result, dict) and tool_name == "text_search" and "results" in result:
        body = "; ".join(
            f"{loc(h)} at lines {','.join(str(m['line']) for m in h['matches'])}" for h in result["results"]
        ) or "no matches"
    else:
        body = json.dumps(result, ensure_ascii=False)[:400]
    return f"[already read, code removed to save space - use symbol_search to see it again] {body}"


class Conversation:
    """Message list that keeps full tool results only while they're new."""

    def __init__(self, system_prompt: str, task: str):
        self.messages: list[dict] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": task},
        ]
        self.short: dict[str, str] = {}  # tool_call_id -> shortened content

    def add_assistant(self, message):
        # Store as a plain dict (drops the model's hidden reasoning: saves tokens)
        entry = {"role": "assistant", "content": message.content or ""}
        if message.tool_calls:
            entry["tool_calls"] = [
                {"id": tc.id, "type": "function",
                 "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in message.tool_calls
            ]
        self.messages.append(entry)

    def add_tool_result(self, tool_call_id: str, content: str, short: str):
        self.messages.append({"role": "tool", "tool_call_id": tool_call_id, "content": content})
        self.short[tool_call_id] = short

    def add_user(self, content: str):
        self.messages.append({"role": "user", "content": content})

    def as_transcript(self, closing: str) -> list[dict]:
        # The same conversation as plain text, with no tool-call messages. Used for
        # the final report: shown its own tool calls, gpt-oss keeps trying to call
        # tools even when none are offered ("Tool choice is none, but model called a tool").
        lines = []
        for m in self.messages[2:]:
            if m["role"] == "assistant":
                if m.get("content"):
                    lines.append(f"Auditor's note: {m['content']}")
                for tc in m.get("tool_calls", []):
                    lines.append(f"Looked up ({tc['function']['name']}): {tc['function']['arguments']}")
            elif m["role"] == "tool":
                # Drop the "call report_finding NOW" hint: tool talk in the no-tools final
                # step is what makes gpt-oss emit tool calls there
                lines.append(f"Found: {m['content'].replace(REPORT_NOW_HINT, '')}")
            elif not m["content"].startswith("Halfway through"):
                lines.append(f"Note: {m['content']}")
        transcript = "\n".join(lines)
        # Keep the specialist's focus (what to look for) but drop the tool instructions
        role = self.messages[0]["content"].split("You have these tools")[0].strip()
        return [
            {"role": "system", "content": REPORT_SYSTEM_PROMPT},
            {"role": "user", "content": f"Auditor role: {role}\n\n"
                                        f"Task: {self.messages[1]['content'].split(REPO_MAP_HEADER)[0]}\n\n"
                                        f"=== Investigation notes ===\n{transcript}\n\n{closing}"},
        ]

    def _shorten(self, msg: dict) -> bool:
        short = self.short.get(msg.get("tool_call_id"))
        if short is None or msg["content"] == short:
            return False
        msg["content"] = short
        return True

    def _full_results(self) -> list[dict]:
        # Tool results still holding their full content, oldest first
        return [m for m in self.messages
                if m["role"] == "tool" and self.short.get(m["tool_call_id"]) != m["content"]]

    def fit(self, budget: int, extra_tokens: int = 0):
        # Keep recent code in context so the agent can compare functions and quote
        # real code; remove old code only when needed, oldest first.
        # 1. Never keep more than MAX_FULL_RESULTS full results (limits tokens per run).
        full = self._full_results()
        for m in full[:max(0, len(full) - MAX_FULL_RESULTS)]:
            self._shorten(m)
        # 2. Over the request budget: shorten the oldest remaining results, then cut text.
        while estimate_tokens(self.messages) + extra_tokens > budget:
            full = self._full_results()
            if full:
                self._shorten(full[0])
                continue
            biggest = max(self.messages[2:] or self.messages, key=lambda m: len(m.get("content") or ""))
            content = biggest.get("content") or ""
            if len(content) < 200:
                break  # nothing meaningful left to cut
            biggest["content"] = content[: len(content) // 2] + "\n[...cut to fit the request size limit]"
            if biggest.get("role") == "tool":
                # Keep the stored short version in sync, or step 2 would restore the longer one forever
                self.short[biggest["tool_call_id"]] = biggest["content"]


# ---------- the agent loop ----------

def _finding_event(prefix: str, f: dict, recorded: bool, source: str, reason: str = ""):
    _ev(prefix, "finding", title=f.get("title"), severity=f.get("severity"),
        file_path=f.get("file_path"), start_line=f.get("start_line"),
        recorded=recorded, source=source, reason=reason)


def _record_finding(tool_input: dict, collection, findings: list[dict], prefix: str = "") -> str:
    ok, reason, _ = check_evidence(collection, tool_input)
    _finding_event(prefix, tool_input, ok, "report_finding", "" if ok else reason)
    if not ok:
        return (f"NOT recorded: {reason}. Check file_path and line numbers against the tool "
                f"results and copy the code verbatim, then call report_finding again.")
    findings.append(tool_input)
    return f"Recorded finding #{len(findings)}. Continue investigating."


def run_agent(task: str, collection, system_prompt: str = SYSTEM_PROMPT, label: str = "") -> dict:
    # Returns {"findings": [...], "report": final text, "error": None or message}.
    # Findings are kept even if the agent fails part-way through.
    prefix = f"[{label}] " if label else ""  # tells parallel agents' output apart
    client = get_client()
    conv = Conversation(system_prompt, task)
    findings: list[dict] = []
    schema_tokens = estimate_tokens(TOOL_SCHEMAS)
    shrink = 1.0  # reduced after a 413

    def final_report():
        # No tools, plain-text notes, JSON mode. gpt-oss still sometimes emits a tool
        # call here (a random failure), so retry, then switch to another model.
        messages = conv.as_transcript(FINAL_PROMPT)
        for n, model in enumerate(FINAL_REPORT_MODELS):
            try:
                return create_with_retry(client, prefix, model=model, messages=messages,
                                         max_tokens=FINAL_MAX_TOKENS, response_format={"type": "json_object"})
            except BadRequestError as e:
                if _error_code(e) not in RETRYABLE_400_CODES or n == len(FINAL_REPORT_MODELS) - 1:
                    raise
                print(f"{prefix}  Final report failed ({_error_code(e)}), trying again with {FINAL_REPORT_MODELS[n + 1]}...")

    def call(final: bool):
        nonlocal shrink
        max_tokens = FINAL_MAX_TOKENS if final else STEP_MAX_TOKENS
        for _ in range(3):
            budget = int((tpm_limit() - max_tokens - SAFETY_MARGIN) * shrink)
            conv.fit(budget, extra_tokens=0 if final else schema_tokens)
            try:
                if final:
                    return final_report()
                return create_with_retry(client, prefix, model=MODEL, messages=conv.messages,
                                         max_tokens=max_tokens, tools=TOOL_SCHEMAS, tool_choice="auto")
            except RequestTooLarge:
                shrink *= 0.75
                print(f"{prefix}  Request too large for the per-minute limit, shrinking and retrying...")
        raise RequestTooLarge("request still too large after shrinking")

    try:
        for i in range(MAX_ITERATIONS):
            print(f"{prefix}Iteration {i+1}/{MAX_ITERATIONS}")
            final = i == MAX_ITERATIONS - 1
            _ev(prefix, "agent_step", step=i + 1, of=MAX_ITERATIONS, final=final)
            if i == MAX_ITERATIONS // 2 and not findings:
                conv.add_user("Halfway through your search budget and nothing reported yet. If you have "
                              "already seen a real problem, report it now with report_finding, then continue.")
            # Last round (final=True): tools are taken away so we always get a report
            choice = call(final).choices[0]
            message = choice.message

            if not message.tool_calls:
                if not (message.content or "").strip() and choice.finish_reason == "length" and not final:
                    # Ran out of reply budget while thinking; nudge and continue
                    conv.add_assistant(message)
                    conv.add_user("Your reply was cut off. Make one tool call at a time, or give your summary.")
                    continue
                reported = parse_findings(message.content) or []
                for f in reported:
                    _finding_event(prefix, f, True, "final_report")
                findings.extend(reported)
                return {"findings": findings, "report": message.content or "", "error": None}

            conv.add_assistant(message)
            for tool_call in message.tool_calls:
                tool_name = tool_call.function.name
                try:
                    tool_input = json.loads(tool_call.function.arguments)
                    if tool_name == "report_finding":
                        content = _record_finding(tool_input, collection, findings, prefix)
                        print(f"{prefix}  -> report_finding({tool_input.get('title')!r}): {content.split('.')[0]}")
                        short = content
                    else:
                        print(f"{prefix}  -> {tool_name}({tool_input})")
                        _ev(prefix, "tool_call", tool=tool_name, args=tool_input)
                        result = execute_tool(tool_name, tool_input, collection)
                        content = json.dumps(result, ensure_ascii=False)  # compact: indentation wastes tokens
                        if tool_name in CODE_TOOLS:
                            content += REPORT_NOW_HINT
                        short = _summarize_result(tool_name, result)
                        _ev(prefix, "tool_result", tool=tool_name,
                            summary=short.split("] ", 1)[-1][:300])
                except Exception as e:
                    print(f"{prefix}  -> {tool_name} failed: {e}")
                    _ev(prefix, "tool_result", tool=tool_name, error=str(e)[:300])
                    content = short = f"Tool error: {e}"
                conv.add_tool_result(tool_call.id, content, short)
    except DailyLimitReached:
        # No salvage report: the quota is empty, so it would fail too
        print(f"{prefix}stopped: daily Groq token limit reached")
        _ev(prefix, "agent_error", error="Daily Groq token limit reached", quota=True)
        return {"findings": findings, "report": "", "error": "daily Groq token limit reached"}
    except Exception as e:
        print(f"{prefix}stopped early: {e}")
        _ev(prefix, "agent_error", error=str(e)[:500])
        # Salvage: ask once for a report of what was seen but not yet reported
        if any(m["role"] == "tool" for m in conv.messages):
            try:
                print(f"{prefix}  asking for a final report of what was found so far...")
                salvaged = parse_findings(call(final=True).choices[0].message.content) or []
                for f in salvaged:
                    _finding_event(prefix, f, True, "salvage_report")
                findings.extend(salvaged)
            except Exception as e2:
                print(f"{prefix}  final report failed too: {e2}")
        return {"findings": findings, "report": "", "error": str(e)}

    return {"findings": findings, "report": "", "error": "hit iteration limit without a final answer"}


def parse_json_object(text: str | None) -> dict | None:
    # Models sometimes wrap JSON in ```json fences or add a sentence around it,
    # so parse from the first "{" to the last "}".
    if not text:
        return None
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def parse_findings(text: str | None) -> list[dict] | None:
    # None means the report couldn't be parsed (as opposed to "no findings").
    data = parse_json_object(text)
    if data is None or not isinstance(data.get("findings"), list):
        return None
    return [f for f in data["findings"] if isinstance(f, dict)]
