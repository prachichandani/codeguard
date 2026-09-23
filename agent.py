import os
import json
from groq import Groq
from tools import TOOL_SCHEMAS, execute_tool

MODEL = "openai/gpt-oss-120b"
MAX_ITERATIONS = 5

SYSTEM_PROMPT = """You are a code security and quality auditor. You have two tools
over a codebase:
- semantic_search: find code related to a concept when you don't know names.
- symbol_search: fetch a specific function/class by name (e.g. one you saw
  called in earlier results) to inspect its actual implementation.
Investigate the repository by making targeted searches, then report concrete
findings.

For each finding include: title, severity (low/medium/high), exact file path
and line range from tool results (never invent these), a short explanation,
and the evidence that supports it.

Only report findings you have actual evidence for. If you find nothing after
reasonable searching, say so honestly.

When done, respond with plain text findings (not a tool call) and stop.
"""

def run_agent(task: str, collection) -> str:
    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": task},
    ]

    for i in range(MAX_ITERATIONS):
        print(f"Iteration {i+1}/{MAX_ITERATIONS}")
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOL_SCHEMAS,
            tool_choice="auto",
            max_tokens=2000,
        )

        message = response.choices[0].message

        if not message.tool_calls:
            return message.content

        messages.append(message)

        for tool_call in message.tool_calls:
            tool_name = tool_call.function.name
            tool_input = json.loads(tool_call.function.arguments)
            print(f"  -> {tool_name}({tool_input})")
            try:
                result = execute_tool(tool_name, tool_input, collection)
                content = json.dumps(result, indent=2)
            except Exception as e:
                content = f"Tool error: {e}"

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": content,
            })

    return "Hit iteration limit without a final answer."