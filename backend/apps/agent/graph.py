"""LangGraph spending agent: decide -> run tool -> decide ... -> final answer.

Each loop costs one LLM request (free-tier friendly): max MAX_STEPS tool calls.
The decision is a structured object (works the same on Groq, Gemini and the offline fake).
"""

from __future__ import annotations

import json
from datetime import date
from typing import Annotated, Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field

from apps.llm import context as llm_context

from . import tools

MAX_STEPS = 6
PREVIEW_ROWS = 8


class Decision(BaseModel):
    """What to do next. Fill exactly the field that matches `action`."""

    action: Literal["query", "chart", "price_changes", "search", "final"]
    query: tools.QuerySpec | None = None
    chart: tools.ChartArgs | None = None
    price_changes: tools.PriceChangeArgs | None = None
    search: str | None = Field(None, description="Question to look up in document text")
    answer: str | None = Field(None, description="Final answer, only for action=final")


SYSTEM = """You are a spending analyst for one company's approved invoices. Use tools; never invent numbers.
Tools: query (structured read-only query over tables invoices[{invoice_columns}], line_items[{item_columns}], vendors[name, ntn]),
chart (plot rows of an earlier query step by index), price_changes (biggest unit-price increases per vendor/item),
search (look up text in the uploaded documents, returns cited snippets), final (answer).
Rules: amounts are PKR. Today is {today}; resolve phrases like "last quarter" into explicit invoice_date filters (>= and <=).
Quote numbers exactly as returned by tools. If the data cannot answer the question, say so in the final answer.
Step results so far are shown to you; query step indexes start at 0. Stop with action=final as soon as you can answer."""


class _Replace(list):
    """Marker: a node returns this to replace the whole steps list instead of appending."""


def _reduce_steps(old: list, new: list) -> list:
    return list(new) if isinstance(new, _Replace) else [*old, *new]


class State(TypedDict):
    question: str
    workspace_id: int
    steps: Annotated[list[dict], _reduce_steps]
    results: dict  # step index -> tool result (rows) for charts
    charts: list[dict]
    answer: str | None
    iterations: int


def _schema_hint() -> dict:
    return {
        "invoice_columns": ", ".join(tools.TABLES["invoices"]["columns"]),
        "item_columns": ", ".join(tools.TABLES["line_items"]["columns"]),
    }


def _history(state: State) -> str:
    lines = []
    for i, s in enumerate(state["steps"]):
        if s.get("error"):
            lines.append(f"step {i} [{s['type']}] ERROR: {s['error']}")
        else:
            lines.append(
                f"step {i} [{s['type']}] columns={s.get('columns')} rows={json.dumps(s.get('preview'))}"
                f" (total rows: {s.get('row_count')})"
            )
    return "\n".join(lines) or "(no steps yet)"


def build_graph(llm, retrieve_docs):
    """`retrieve_docs(workspace_id, question) -> list[dict]` is injected (RAG search tool)."""

    def decide(state: State) -> dict:
        system = SYSTEM.format(today=date.today().isoformat(), **_schema_hint())
        human = f"Question: {state['question']}\n\nSteps so far:\n{_history(state)}"
        with llm_context.usage_context(workspace_id=state["workspace_id"]):
            d = llm.structured(Decision, [("system", system), ("human", human)])
        step: dict = {"type": d.action, "input": d.model_dump(mode="json", exclude_none=True)}
        if d.action == "final":
            return {"answer": (d.answer or "").strip(), "iterations": state["iterations"] + 1,
                    "steps": [{**step, "input": {}}]}  # fmt: skip
        return {"steps": [step], "iterations": state["iterations"] + 1, "answer": None}

    def run_tool(state: State) -> dict:
        idx = len(state["steps"]) - 1
        step = dict(state["steps"][-1])
        d = Decision.model_validate({"action": step["type"], **step["input"]})
        results, charts = dict(state["results"]), list(state["charts"])
        try:
            if d.action == "query":
                out = tools.run_query(d.query or _missing("query"), state["workspace_id"])
            elif d.action == "price_changes":
                out = tools.price_changes(
                    d.price_changes or tools.PriceChangeArgs(), state["workspace_id"]
                )
            elif d.action == "chart":
                chart = tools.build_chart(d.chart or _missing("chart"), results)
                charts.append(chart)
                out = {
                    "columns": ["label", "value"],
                    "rows": chart["points"],
                    "row_count": len(chart["points"]),
                }
            else:  # search
                hits = retrieve_docs(state["workspace_id"], d.search or _missing("search"))
                out = {
                    "columns": ["document", "page", "text"],
                    "rows": hits,
                    "row_count": len(hits),
                }
            results[idx] = out
            step.update(columns=out["columns"], row_count=out["row_count"], preview=out["rows"][:PREVIEW_ROWS],
                        truncated=out.get("truncated", False))  # fmt: skip
        except tools.ToolError as exc:
            step["error"] = str(exc)
        new_steps = list(state["steps"])
        new_steps[-1] = step
        # replace (not append) the pending step with its executed version
        return {"results": results, "charts": charts, "_replace_last": new_steps}

    def after_decide(state: State) -> str:
        if state["answer"] is not None or state["iterations"] >= MAX_STEPS:
            return "end"
        return "tool"

    g = StateGraph(State)
    g.add_node("decide", decide)
    g.add_node("tool", _wrap_replace(run_tool))
    g.add_edge(START, "decide")
    g.add_conditional_edges("decide", after_decide, {"tool": "tool", "end": END})
    g.add_edge("tool", "decide")
    return g.compile()


def _missing(name: str):
    raise tools.ToolError(f"action {name!r} needs its {name} argument")


def _wrap_replace(fn):
    """run_tool updates the pending step in place; adapt it to the appending reducer."""

    def node(state: State) -> dict:
        out = fn(state)
        out["steps"] = _Replace(out.pop("_replace_last"))
        return out

    return node


def run_agent(question: str, workspace_id: int, llm, retrieve_docs) -> dict:
    graph = build_graph(llm, retrieve_docs)
    final = graph.invoke(
        {"question": question, "workspace_id": workspace_id, "steps": [], "results": {},
         "charts": [], "answer": None, "iterations": 0},
        {"recursion_limit": 4 * MAX_STEPS + 4},
    )  # fmt: skip
    steps = [s for s in final["steps"] if s["type"] != "final"]
    answer = final["answer"]
    if answer is None:  # hit the step budget without a final answer
        answer = (
            "I could not finish this analysis within the step limit. Here is what I found so far."
        )
    return {
        "answer": answer,
        "steps": steps,
        "charts": final["charts"],
        "iterations": final["iterations"],
    }
