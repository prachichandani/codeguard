from vectorstore import semantic_search, symbol_search, graph_traversal, text_search

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "semantic_search",
            "description": (
                "Search the codebase for functions/classes semantically related to a "
                "natural language description. Use full phrases describing behaviour "
                "(e.g. 'building SQL queries from user input', 'password hashing on login'), "
                "NOT single keywords - use text_search for exact words or code."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Description of the code you're looking for"},
                    "n_results": {"type": "integer", "description": "How many results (default and max 3)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "text_search",
            "description": (
                "Find exact text in the code, like grep (case-insensitive). Use this for "
                "specific code patterns, e.g. 'execute(', 'md5', 'autoescape', 'except:', "
                "'debug=True', 'pickle.loads'. Returns matching lines with line numbers and "
                "which function they are in - use symbol_search to read the full function."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Text to find (or a regex if regex=true)"},
                    "regex": {"type": "boolean", "description": "Treat pattern as a Python regex (default false)"},
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "symbol_search",
            "description": (
                "Read a function, method or class by name. Use this when you know the "
                "name (from an earlier result or a call you saw) and want its code. "
                "Accepts 'name' or 'ClassName.method'. Case-insensitive; exact matches "
                "come first. Code lines are prefixed with their line numbers. For long "
                "functions, pass `line` to see the part around that line."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Function/class name, or ClassName.method"},
                    "line": {"type": "integer", "description": "Optional: show the code around this line number"},
                    "n_results": {"type": "integer", "description": "How many results (default and max 3)"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "graph_traversal",
            "description": (
                "Explore the call graph around a function/method. direction='callers' "
                "lists code that calls it (e.g. to trace where user input reaches a "
                "dangerous function); direction='callees' lists what it calls. Returns "
                "locations only, not code - use symbol_search to read any result. "
                "Calls are matched by name, so same-named methods in different classes "
                "can appear together."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Function name, or ClassName.method"},
                    "direction": {
                        "type": "string",
                        "enum": ["callers", "callees"],
                        "description": "callers = who calls it, callees = what it calls (default callees)",
                    },
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "report_finding",
            "description": (
                "Record one problem as soon as you have confirmed it, while its code is in "
                "front of you. Older tool results get shortened later, so don't wait until "
                "the end. The finding is checked immediately: if the evidence isn't found "
                "at that location you'll be told, and can fix it and report again."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "severity": {"type": "string", "enum": ["low", "medium", "high"]},
                    "file_path": {"type": "string", "description": "Exact file_path from a tool result"},
                    "start_line": {"type": "integer", "description": "First line of the problematic code"},
                    "end_line": {"type": "integer", "description": "Last line of the problematic code"},
                    "evidence": {
                        "type": "string",
                        "description": "The problematic code copied verbatim from a tool result, WITHOUT the line-number prefixes",
                    },
                    "explanation": {"type": "string", "description": "Why this is a problem"},
                },
                "required": ["title", "severity", "file_path", "start_line", "end_line", "evidence", "explanation"],
            },
        },
    },
]

MAX_RESULTS = 3
MAX_CODE_LINES = 40


def _cap_n_results(tool_input: dict) -> int:
    return max(1, min(int(tool_input.get("n_results", MAX_RESULTS)), MAX_RESULTS))


def _format_code(hits: list[dict], around_line: int | None = None) -> list[dict]:
    # Prefix each line with its real line number (so the model can cite lines
    # without counting), and keep requests small: long entities are cut to a
    # MAX_CODE_LINES window - the start, or centred on `around_line`.
    for hit in hits:
        lines = hit["code"].splitlines()
        first = hit["start_line"]
        lo = 0
        if len(lines) > MAX_CODE_LINES and around_line is not None:
            lo = min(max(0, around_line - first - MAX_CODE_LINES // 2), len(lines) - MAX_CODE_LINES)
        shown = lines[lo:lo + MAX_CODE_LINES]
        text = "\n".join(f"{first + lo + i}| {line}" for i, line in enumerate(shown))
        if len(shown) < len(lines):
            text += (f"\n... [showing lines {first + lo}-{first + lo + len(shown) - 1} of "
                     f"{first}-{first + len(lines) - 1}; call symbol_search with `line` to see other parts]")
        hit["code"] = text
    return hits


def execute_tool(tool_name: str, tool_input: dict, collection) -> list[dict] | dict:
    if tool_name == "semantic_search":
        hits = semantic_search(collection, query=tool_input["query"], n_results=_cap_n_results(tool_input))
        return _format_code(hits)
    if tool_name == "text_search":
        return text_search(collection, pattern=tool_input["pattern"], regex=bool(tool_input.get("regex", False)))
    if tool_name == "symbol_search":
        hits = symbol_search(collection, name=tool_input["name"], n_results=_cap_n_results(tool_input))
        line = tool_input.get("line")
        return _format_code(hits, around_line=int(line) if line is not None else None)
    if tool_name == "graph_traversal":
        return graph_traversal(collection, name=tool_input["name"], direction=tool_input.get("direction", "callees"))
    raise ValueError(f"Unknown tool: {tool_name}")
