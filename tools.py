from vectorstore import semantic_search, symbol_search, graph_traversal

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "semantic_search",
            "description": (
                "Search the codebase for functions/classes semantically related to a "
                "natural language query. Use this to find code relevant to a concept "
                "(e.g. 'user authentication', 'SQL query construction') even if you "
                "don't know the exact function name."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "What you're looking for"},
                    "n_results": {"type": "integer", "description": "How many results (default and max 5)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "symbol_search",
            "description": (
                "Look up a function, method or class by its exact name. Use this when "
                "you already know the name (e.g. from a previous search result or a "
                "call you saw in the code) and want its definition. Accepts 'name' or "
                "'ClassName.method'. Case-insensitive; exact matches come first, then "
                "names containing the query."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Function/class name, or ClassName.method"},
                    "n_results": {"type": "integer", "description": "How many results (default and max 5)"},
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
]

MAX_RESULTS = 5
MAX_CODE_LINES = 100


def _cap_n_results(tool_input: dict) -> int:
    return max(1, min(int(tool_input.get("n_results", MAX_RESULTS)), MAX_RESULTS))


def _truncate_code(hits: list[dict]) -> list[dict]:
    # Keep the LLM request small: long functions/classes are cut to the first
    # MAX_CODE_LINES lines. start_line/end_line still describe the full entity.
    for hit in hits:
        lines = hit["code"].splitlines()
        if len(lines) > MAX_CODE_LINES:
            hit["code"] = "\n".join(lines[:MAX_CODE_LINES]) + (
                f"\n... [truncated: showing {MAX_CODE_LINES} of {len(lines)} lines]"
            )
    return hits


def execute_tool(tool_name: str, tool_input: dict, collection) -> list[dict] | dict:
    if tool_name == "semantic_search":
        hits = semantic_search(collection, query=tool_input["query"], n_results=_cap_n_results(tool_input))
        return _truncate_code(hits)
    if tool_name == "symbol_search":
        hits = symbol_search(collection, name=tool_input["name"], n_results=_cap_n_results(tool_input))
        return _truncate_code(hits)
    if tool_name == "graph_traversal":
        return graph_traversal(collection, name=tool_input["name"], direction=tool_input.get("direction", "callees"))
    raise ValueError(f"Unknown tool: {tool_name}")
