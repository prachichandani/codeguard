from agent import TOOL_RULES

# Each specialist shares the same tools and evidence rules but looks for
# different problems. Keep focus areas non-overlapping so the Judge (step 14)
# has fewer duplicates to merge.
SPECIALISTS = {
    "security": {
        "role": "Security specialist",
        "focus": """Look ONLY for security vulnerabilities:
- injection: SQL built with string formatting/concatenation, shell commands,
  eval/exec, template injection
- XSS: disabled auto-escaping, marking user input as safe
- authentication/authorization: missing checks, weak password hashing (md5,
  sha1, unsalted), session handling
- secrets: hardcoded keys, passwords, tokens
- unsafe deserialization (pickle, yaml.load), path traversal in file access,
  CSRF protection that is missing or disabled""",
        "task": "Audit this codebase for security vulnerabilities. Report concrete findings with evidence.",
    },
    "architecture": {
        "role": "Architecture specialist",
        "focus": """Look ONLY for design and structure problems:
- layering violations (e.g. request handlers running raw SQL instead of
  going through a data layer)
- god classes/functions doing too many unrelated things
- tight coupling and circular dependencies (graph_traversal helps here)
- duplicated logic that should be shared
- global mutable state
Do not report security bugs or runtime-robustness issues; other specialists cover those.""",
        "task": "Audit this codebase for architectural and design problems. Report concrete findings with evidence.",
    },
    "production": {
        "role": "Production-readiness specialist",
        "focus": """Look ONLY for problems that would hurt this code when running in production:
- error handling: bare except, swallowed exceptions, unhandled errors on
  user input (e.g. int() on request data)
- resources not released: files, DB connections, sockets without close/with
- network calls without timeouts, unbounded retries or loops
- debug mode or dev settings enabled, config hardcoded instead of read from env
- missing logging around failures
Do not report security vulnerabilities or design problems; other specialists cover those.""",
        "task": "Audit this codebase for production-readiness problems. Report concrete findings with evidence.",
    },
}


def system_prompt_for(name: str) -> str:
    spec = SPECIALISTS[name]
    return f"You are the {spec['role']} in a team of code auditors.\n\n{spec['focus']}\n\n{TOOL_RULES}"
