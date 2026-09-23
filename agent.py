import os
import re
import json
import time
from groq import Groq, RateLimitError
from tools import TOOL_SCHEMAS, execute_tool

MODEL = "openai/gpt-oss-120b"
MAX_ITERATIONS = 10
MAX_RETRIES = 3
MAX_TOKENS = 4000  # per response; gpt-oss spends part of this on reasoning
DEFAULT_RETRY_WAIT = 20  # seconds, if Groq doesn't send retry-after

# Shared by every agent (single auditor and specialists): tools + evidence rules
TOOL_RULES = """You have three tools over a codebase:
- semantic_search: find code related to a concept when you don't know names.
- symbol_search: fetch a specific function/class by name (e.g. one you saw
  called in earlier results) to inspect its actual implementation.
- graph_traversal: see who calls a function (callers) or what it calls
  (callees), to trace how data and control flow between functions.
Investigate the repository by making targeted searches, then report concrete
findings.

Only report actual problems you have evidence for: no positive notes, no
generic advice ("consider adding rate limiting") that isn't tied to a specific
defect in the code you saw. If you find nothing, return an empty list.

When done, stop calling tools and reply with ONLY this JSON object, no other text:
{"findings": [{"title": "...", "severity": "low|medium|high",
  "file_path": "exact path from tool results", "start_line": 0, "end_line": 0,
  "evidence": "the problematic code, copied verbatim from tool results",
  "explanation": "why this is a problem"}]}
file_path and line numbers must come from tool results - never invent them.
Findings whose evidence can't be found at that location are thrown away.
"""

SYSTEM_PROMPT = "You are a code security and quality auditor. " + TOOL_RULES

DEFAULT_TASK = (
    "Investigate this codebase for security issues, bad practices, and "
    "architectural problems. Use semantic_search to look for risk areas: "
    "authentication/session handling, user input, and file operations. "
    "Use symbol_search to inspect specific functions you see referenced, and "
    "graph_traversal to trace who calls risky functions. "
    "Report concrete findings with evidence."
)


def get_client() -> Groq:
    return Groq(api_key=os.environ["GROQ_API_KEY"], max_retries=0)  # we retry ourselves


def create_with_retry(client, prefix="", **kwargs):
    # On "too many requests", wait (Groq's retry-after if given) and try again.
    for attempt in range(MAX_RETRIES + 1):
        try:
            return client.chat.completions.create(**kwargs)
        except RateLimitError as e:
            if attempt == MAX_RETRIES:
                raise
            wait = float(e.response.headers.get("retry-after", DEFAULT_RETRY_WAIT))
            print(f"{prefix}  Rate limited, waiting {wait:.0f}s (retry {attempt + 1}/{MAX_RETRIES})...")
            time.sleep(wait)


def run_agent(task: str, collection, system_prompt: str = SYSTEM_PROMPT, label: str = "") -> str:
    prefix = f"[{label}] " if label else ""  # tells parallel agents' output apart
    client = get_client()
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": task},
    ]

    for i in range(MAX_ITERATIONS):
        print(f"{prefix}Iteration {i+1}/{MAX_ITERATIONS}")
        if i == MAX_ITERATIONS - 1:
            # Last round: take the tools away so we always get a final report.
            # (tool_choice="none" isn't enough - the model still tries to call them.)
            messages.append({
                "role": "user",
                "content": "Search budget used up. Reply now with the JSON findings object, using only the evidence gathered so far.",
            })
            response = create_with_retry(client, prefix, model=MODEL, messages=messages, max_tokens=MAX_TOKENS)
        else:
            response = create_with_retry(
                client,
                prefix,
                model=MODEL,
                messages=messages,
                tools=TOOL_SCHEMAS,
                tool_choice="auto",
                max_tokens=MAX_TOKENS,
            )

        message = response.choices[0].message

        if not message.tool_calls:
            return message.content

        messages.append(message)

        for tool_call in message.tool_calls:
            tool_name = tool_call.function.name
            try:
                tool_input = json.loads(tool_call.function.arguments)
                print(f"{prefix}  -> {tool_name}({tool_input})")
                result = execute_tool(tool_name, tool_input, collection)
                content = json.dumps(result)  # compact: indentation wastes tokens
            except Exception as e:
                print(f"{prefix}  -> {tool_name} failed: {e}")
                content = f"Tool error: {e}"

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": content,
            })

    return "Hit iteration limit without a final answer."


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
