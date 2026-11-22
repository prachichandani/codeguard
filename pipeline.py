import operator
from typing import Annotated, Any, TypedDict
from langgraph.graph import StateGraph, START, END
from agent import REPO_MAP_HEADER, run_agent
from embedder import get_model
from events import emit
from judge import judge
from specialists import SPECIALISTS, system_prompt_for
from vectorstore import repo_map


class AuditState(TypedDict):
    collection: Any
    repo_map: str  # files and their functions, given to every specialist up front
    # Parallel specialists write to these at the same time; the reducers
    # (dict merge / list concat) combine their updates instead of overwriting.
    reports: Annotated[dict[str, str], operator.or_]  # raw text, for debugging
    findings: Annotated[list[dict], operator.add]
    judged: dict


def make_specialist_node(name: str):
    def node(state: AuditState) -> dict:
        spec = SPECIALISTS[name]
        task = f"{spec['task']}{REPO_MAP_HEADER}{state['repo_map']}"
        emit("agent_started", agent=name, role=spec["role"])
        try:
            result = run_agent(task, state["collection"], system_prompt_for(name), label=name)
        except Exception as e:
            # One specialist failing shouldn't lose the others' reports
            print(f"[{name}] failed: {e}")
            emit("agent_finished", agent=name, findings=0, error=str(e))
            return {"reports": {name: f"Specialist failed: {e}"}, "findings": []}

        findings = result["findings"]  # kept even if the agent stopped early
        status = f"stopped early ({result['error']})" if result["error"] else "done"
        print(f"[{name}] {status}: {len(findings)} findings")
        emit("agent_finished", agent=name, findings=len(findings), error=result["error"])
        return {
            "reports": {name: result["report"] or result["error"] or ""},
            "findings": [{**f, "specialist": name} for f in findings],
        }
    return node


def judge_node(state: AuditState) -> dict:
    emit("stage", stage="judge", findings=len(state["findings"]))
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
    emit("stage", stage="agents", agents=list(SPECIALISTS))
    result = build_graph().invoke({"collection": collection, "repo_map": repo_map(collection),
                                   "reports": {}, "findings": []})
    return result["judged"]
