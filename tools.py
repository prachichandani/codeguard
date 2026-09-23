from vectorstore import semantic_search, symbol_search

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
                    "n_results": {"type": "integer", "description": "How many results (default 5)"},
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
                    "n_results": {"type": "integer", "description": "How many results (default 5)"},
                },
                "required": ["name"],
            },
        },
    },
]

def execute_tool(tool_name: str, tool_input: dict, collection) -> list[dict]:
    if tool_name == "semantic_search":
        return semantic_search(collection, query=tool_input["query"], n_results=tool_input.get("n_results", 5))
    if tool_name == "symbol_search":
        return symbol_search(collection, name=tool_input["name"], n_results=tool_input.get("n_results", 5))
    raise ValueError(f"Unknown tool: {tool_name}")
