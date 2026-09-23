import operator
from typing import Annotated, Any, TypedDict
from langgraph.graph import StateGraph, START, END
from agent import run_agent, parse_findings
from embedder import get_model
from judge import judge
from specialists import SPECIALISTS, system_prompt_for


class AuditState(TypedDict):
    collection: Any
    # Parallel specialists write to these at the same time; the reducers
    # (dict merge / list concat) combine their updates instead of overwriting.
    reports: Annotated[dict[str, str], operator.or_]  # raw text, for debugging
    findings: Annotated[list[dict], operator.add]
    judged: dict


def make_specialist_node(name: str):
    def node(state: AuditState) -> dict:
        spec = SPECIALISTS[name]
        try:
            report = run_agent(spec["task"], state["collection"], system_prompt_for(name), label=name)
        except Exception as e:
            # One specialist failing (e.g. rate limit) shouldn't lose the others' reports
            print(f"[{name}] failed: {e}")
            return {"reports": {name: f"Specialist failed: {e}"}, "findings": []}

        findings = parse_findings(report)
        if findings is None:
            print(f"[{name}] could not parse findings JSON; report starts: {report[:200]!r}")
            findings = []
        print(f"[{name}] done: {len(findings)} findings")
        return {
            "reports": {name: report},
            "findings": [{**f, "specialist": name} for f in findings],
        }
    return node


def judge_node(state: AuditState) -> dict:
    return {"judged": judge(state["collection"], state["findings"])}


def build_graph():
    # START fans out to every specialist in parallel; the judge runs once
    # all of them have finished.
    graph = StateGraph(AuditState)
    graph.add_node("judge", judge_node)
    for name in SPECIALISTS:
        graph.add_node(name, make_specialist_node(name))
        graph.add_edge(START, name)
        graph.add_edge(name, "judge")
    graph.add_edge("judge", END)
    return graph.compile()


def run_pipeline(collection) -> dict:
    get_model()  # load the embedding model once, before parallel agents race to load it
    result = build_graph().invoke({"collection": collection, "reports": {}, "findings": []})
    return result["judged"]
