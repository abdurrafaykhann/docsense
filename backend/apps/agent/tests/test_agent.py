from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core.files.base import ContentFile
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.agent import tools
from apps.agent.graph import MAX_STEPS, run_agent
from apps.agent.tools import (
    Aggregation,
    ChartArgs,
    Filter,
    OrderBy,
    PriceChangeArgs,
    QuerySpec,
    ToolError,
    build_chart,
    price_changes,
    run_query,
)
from apps.documents.models import Document, Invoice, InvoiceLineItem, Vendor
from apps.llm.client import LLMClient, Provider
from apps.llm.fake import FakeChatModel
from apps.pipeline import services as pipeline_services
from conftest import client_for

pytestmark = pytest.mark.django_db


def mk(ws, vendor, n, total, d, category="grocery", items=()):
    doc = Document(
        workspace=ws,
        original_name=f"i{n}.png",
        content_type="image/png",
        size=1,
        sha256=f"{ws.id}-{n}",
        status="done",
    )
    doc.file.save(f"i{n}.png", ContentFile(b"x"), save=True)
    inv = Invoice.objects.create(
        document=doc,
        workspace=ws,
        vendor=vendor,
        invoice_number=f"N{n}",
        invoice_date=d,
        total=Decimal(total),
        category=category,
    )
    for i, (desc, price) in enumerate(items):
        InvoiceLineItem.objects.create(
            invoice=inv, position=i, description=desc, quantity=1, unit_price=price, amount=price
        )
    return inv


@pytest.fixture
def data(world):
    ws, other = world["ws"], world["other"]
    a = Vendor.objects.create(workspace=ws, name="Al-Mart")
    b = Vendor.objects.create(workspace=ws, name="Noor Pharmacy")
    spy = Vendor.objects.create(workspace=other, name="Secret Vendor")
    mk(ws, a, 1, 1000, date(2025, 1, 15), items=[("Cooking Oil 1L", 500)])
    mk(ws, a, 2, 2000, date(2025, 2, 15), items=[("Cooking Oil 1L", 550)])
    mk(ws, a, 3, 3000, date(2025, 4, 15), items=[("Cooking Oil 1L", 700), ("Sugar 1kg", 150)])
    mk(ws, b, 4, 500, date(2025, 2, 20), category="pharmacy", items=[("Syrup", 200)])
    mk(other, spy, 5, 99999, date(2025, 2, 20), items=[("Gold bar", 1000000)])
    return world


# ---------------------------------------------------------------- safe query tool
def test_group_by_vendor_with_sum_and_ordering_matches_manual_totals(data):
    spec = QuerySpec(
        table="invoices",
        group_by=["vendor_name"],
        aggregations=[
            Aggregation(fn="sum", column="total", alias="spend"),
            Aggregation(fn="count", alias="n"),
        ],
        order_by=[OrderBy(column="spend", direction="desc")],
    )
    out = run_query(spec, data["ws"].id)
    assert out["columns"] == ["vendor_name", "spend", "n"]
    assert out["rows"] == [
        {"vendor_name": "Al-Mart", "spend": 6000.0, "n": 3},
        {"vendor_name": "Noor Pharmacy", "spend": 500.0, "n": 1},
    ]


def test_filters_dates_in_contains_and_not_equal(data):
    ws = data["ws"].id
    q1 = QuerySpec(
        table="invoices",
        select=["invoice_number", "total"],
        order_by=[OrderBy(column="total", direction="asc")],
        filters=[
            Filter(column="invoice_date", op=">=", value="2025-02-01"),
            Filter(column="invoice_date", op="<=", value="2025-03-31"),
        ],
    )
    assert [r["invoice_number"] for r in run_query(q1, ws)["rows"]] == ["N4", "N2"]
    q2 = QuerySpec(
        table="invoices",
        select=["invoice_number"],
        filters=[Filter(column="vendor_name", op="in", value=["Noor Pharmacy"])],
    )
    assert run_query(q2, ws)["rows"] == [{"invoice_number": "N4"}]
    q3 = QuerySpec(
        table="invoices",
        select=["invoice_number"],
        filters=[Filter(column="vendor_name", op="contains", value="mart")],
    )
    assert len(run_query(q3, ws)["rows"]) == 3
    q4 = QuerySpec(
        table="invoices",
        select=["invoice_number"],
        filters=[Filter(column="category", op="!=", value="grocery")],
    )
    assert run_query(q4, ws)["rows"] == [{"invoice_number": "N4"}]


def test_workspace_isolation_is_enforced_in_code(data):
    ws, other = data["ws"].id, data["other"].id
    everything = QuerySpec(table="invoices", select=["vendor_name", "total"])
    names = {r["vendor_name"] for r in run_query(everything, ws)["rows"]}
    assert "Secret Vendor" not in names
    assert {r["vendor_name"] for r in run_query(everything, other)["rows"]} == {"Secret Vendor"}
    # the model cannot widen scope through filters on workspace/ids, nor by naming other tables
    for bad_col in ("workspace", "workspace_id", "id", "vendor__workspace__id"):
        with pytest.raises(ToolError):
            run_query(
                QuerySpec(table="invoices", filters=[Filter(column=bad_col, value=other)]), ws
            )
    items = run_query(QuerySpec(table="line_items", select=["description"]), ws)
    assert "Gold bar" not in {r["description"] for r in items["rows"]}
    assert run_query(QuerySpec(table="vendors", select=["name"]), ws)["rows"] != []
    assert "Secret Vendor" not in {
        r["name"] for r in run_query(QuerySpec(table="vendors", select=["name"]), ws)["rows"]
    }


def test_unknown_things_are_rejected_and_values_are_never_executed_as_sql(data):
    ws = data["ws"].id
    with pytest.raises(ToolError, match="Unknown column"):
        run_query(QuerySpec(table="invoices", select=["password"]), ws)
    with pytest.raises(ToolError):
        run_query(
            QuerySpec(
                table="invoices",
                group_by=["nope"],
                aggregations=[Aggregation(fn="count", alias="n")],
            ),
            ws,
        )
    with pytest.raises(ToolError, match="Cannot sum text"):
        run_query(
            QuerySpec(
                table="invoices",
                group_by=["category"],
                aggregations=[Aggregation(fn="sum", column="vendor_name", alias="s")],
            ),
            ws,
        )
    with pytest.raises(ToolError, match="Bad alias"):
        run_query(
            QuerySpec(
                table="invoices", aggregations=[Aggregation(fn="count", alias="x; DROP TABLE")]
            ),
            ws,
        )
    with pytest.raises(ToolError):
        run_query(
            QuerySpec(table="invoices", filters=[Filter(column="invoice_date", value="yesterday")]),
            ws,
        )
    with pytest.raises(ToolError, match="Cannot order"):
        run_query(
            QuerySpec(table="invoices", select=["total"], order_by=[OrderBy(column="vendor_name")]),
            ws,
        )
    with pytest.raises(ToolError):
        run_query(QuerySpec(table="invoices", filters=[Filter(column="total", value=1)] * 7), ws)
    evil = QuerySpec(
        table="invoices",
        select=["invoice_number"],
        filters=[
            Filter(column="vendor_name", op="contains", value="'; DROP TABLE documents_invoice; --")
        ],
    )
    assert run_query(evil, ws)["rows"] == []
    assert Invoice.objects.count() == 5  # still there


def test_only_select_statements_are_ever_executed(data):
    specs = [
        QuerySpec(
            table="invoices",
            group_by=["category"],
            aggregations=[Aggregation(fn="sum", column="total", alias="t")],
        ),
        QuerySpec(table="line_items", select=["description", "vendor_name"]),
        QuerySpec(table="vendors"),
    ]
    with CaptureQueriesContext(connection) as ctx:
        for s in specs:
            run_query(s, data["ws"].id)
    assert ctx.captured_queries and all(
        q["sql"].lstrip().upper().startswith("SELECT") for q in ctx.captured_queries
    )


def test_limit_is_clamped(data):
    out = run_query(QuerySpec(table="invoices", select=["total"], limit=10**6), data["ws"].id)
    assert out["row_count"] == 4 and tools.MAX_LIMIT == 200
    assert (
        run_query(QuerySpec(table="invoices", select=["total"], limit=2), data["ws"].id)[
            "truncated"
        ]
        is True
    )


# ---------------------------------------------------------------- chart + price tools
def test_chart_is_built_from_query_rows_not_model_numbers(data):
    res = run_query(
        QuerySpec(
            table="invoices",
            group_by=["category"],
            aggregations=[Aggregation(fn="sum", column="total", alias="spend")],
        ),
        data["ws"].id,
    )
    chart = build_chart(
        ChartArgs(query_step=0, x="category", y="spend", title="By category"), {0: res}
    )
    assert {(p["label"], p["value"]) for p in chart["points"]} == {
        ("grocery", 6000.0),
        ("pharmacy", 500.0),
    }
    with pytest.raises(ToolError, match="No query result"):
        build_chart(ChartArgs(query_step=3, x="category", y="spend", title="t"), {0: res})
    with pytest.raises(ToolError, match="not in that query"):
        build_chart(ChartArgs(query_step=0, x="vendor", y="spend", title="t"), {0: res})
    with pytest.raises(ToolError, match="not numeric"):
        build_chart(ChartArgs(query_step=0, x="spend", y="category", title="t"), {0: res})


def test_price_changes_ranks_first_vs_latest_per_vendor_item(data):
    out = price_changes(PriceChangeArgs(top_n=5), data["ws"].id)
    top = out["rows"][0]
    assert (top["vendor"], top["item"]) == ("Al-Mart", "cooking oil 1l")
    assert top["first_price"] == 500 and top["latest_price"] == 700 and top["increase_pct"] == 40.0
    assert all(r["item"] != "gold bar" for r in out["rows"])  # other workspace never leaks
    assert (
        price_changes(PriceChangeArgs(vendor_name="noor"), data["ws"].id)["rows"] == []
    )  # 1 obs only


# ---------------------------------------------------------------- the graph
def decisions(*items):
    return LLMClient([Provider("fake", FakeChatModel(list(items)))])


def no_search(ws, q):
    return []


def test_agent_queries_charts_and_answers_with_a_step_trace(data):
    llm = decisions(
        {
            "action": "query",
            "query": {
                "table": "invoices",
                "group_by": ["vendor_name"],
                "aggregations": [{"fn": "sum", "column": "total", "alias": "spend"}],
                "order_by": [{"column": "spend", "direction": "desc"}],
            },
        },
        {
            "action": "chart",
            "chart": {
                "query_step": 0,
                "x": "vendor_name",
                "y": "spend",
                "title": "Spend by vendor",
            },
        },
        {"action": "final", "answer": "Al-Mart: PKR 6,000; Noor Pharmacy: PKR 500."},
    )
    out = run_agent("How much did we spend with each vendor?", data["ws"].id, llm, no_search)
    assert out["answer"].startswith("Al-Mart")
    assert [s["type"] for s in out["steps"]] == ["query", "chart"]
    assert out["steps"][0]["preview"][0] == {"vendor_name": "Al-Mart", "spend": 6000.0}
    assert out["charts"][0]["points"][0] == {"label": "Al-Mart", "value": 6000.0}
    assert out["iterations"] == 3


def test_agent_recovers_from_a_tool_error_and_sees_the_message(data):
    model = FakeChatModel(
        [
            {
                "action": "query",
                "query": {"table": "invoices", "select": ["vendor"]},
            },  # wrong column
            {
                "action": "query",
                "query": {"table": "invoices", "select": ["vendor_name"], "limit": 1},
            },
            {"action": "final", "answer": "Done."},
        ]
    )
    out = run_agent("list vendors", data["ws"].id, LLMClient([Provider("f", model)]), no_search)
    assert "Unknown column" in out["steps"][0]["error"] and "error" not in out["steps"][1]
    second_prompt = model.calls[1][1][1]
    assert "ERROR: Unknown column" in second_prompt  # the model was told what went wrong


def test_agent_uses_price_changes_and_search_tools(data):
    seen = []

    def search(ws, q):
        seen.append((ws, q))
        return [{"document": "policy.pdf", "page": 1, "text": "warranty 24 months"}]

    llm = decisions(
        {"action": "price_changes", "price_changes": {"top_n": 3}},
        {"action": "search", "search": "warranty"},
        {"action": "final", "answer": "Al-Mart raised cooking oil by 40%."},
    )
    out = run_agent("Which vendor raised prices the most?", data["ws"].id, llm, search)
    assert out["steps"][0]["preview"][0]["vendor"] == "Al-Mart"
    assert out["steps"][1]["preview"][0]["document"] == "policy.pdf"
    assert seen == [(data["ws"].id, "warranty")]  # workspace id comes from state, not the model


def test_agent_stops_at_the_step_budget(data):
    loop = {"action": "query", "query": {"table": "vendors"}}
    model = FakeChatModel([loop] * 20)
    out = run_agent("forever", data["ws"].id, LLMClient([Provider("f", model)]), no_search)
    assert out["iterations"] == MAX_STEPS and len(model.calls) == MAX_STEPS
    assert "step limit" in out["answer"]


# ---------------------------------------------------------------- API
@pytest.fixture
def fake_llm(monkeypatch):
    model = FakeChatModel(
        [
            {
                "action": "query",
                "query": {
                    "table": "invoices",
                    "aggregations": [{"fn": "sum", "column": "total", "alias": "s"}],
                },
            },
            {"action": "final", "answer": "Total spend is PKR 6,500."},
        ]
        * 5
    )
    monkeypatch.setattr(pipeline_services, "get_llm", lambda: LLMClient([Provider("f", model)]))
    return model


def test_api_returns_answer_and_trace_and_enforces_access(data, fake_llm):
    url = f"/api/v1/workspaces/{data['ws'].id}/agent/ask/"
    res = client_for(data["users"]["viewer"]).post(url, {"question": "total spend?"}, format="json")
    assert res.status_code == 200
    body = res.json()
    assert body["answer"] == "Total spend is PKR 6,500." and body["steps"][0]["preview"] == [
        {"s": 6500.0}
    ]
    assert (
        client_for(data["users"]["outsider"])
        .post(url, {"question": "x"}, format="json")
        .status_code
        == 404
    )
    assert client_for().post(url, {"question": "x"}, format="json").status_code == 401
    assert (
        client_for(data["users"]["member"]).post(url, {"question": ""}, format="json").status_code
        == 400
    )
    # the other workspace's agent only ever sees its own data
    other = f"/api/v1/workspaces/{data['other'].id}/agent/ask/"
    out = (
        client_for(data["users"]["outsider"])
        .post(other, {"question": "total"}, format="json")
        .json()
    )
    assert out["steps"][0]["preview"] == [{"s": 99999.0}]
    assert date.today() - timedelta(days=0) == date.today()


def test_results_only_ever_contain_whitelisted_columns(data):
    """Regression: an aggregation without group_by once leaked every model field (ids, FKs)."""
    ws = data["ws"].id
    agg = run_query(
        QuerySpec(
            table="invoices", aggregations=[Aggregation(fn="sum", column="total", alias="s")]
        ),
        ws,
    )
    assert agg["rows"] == [{"s": 6500.0}]
    for table in ("invoices", "line_items", "vendors"):
        out = run_query(QuerySpec(table=table), ws)
        assert set(out["rows"][0]) <= set(tools.TABLES[table]["columns"]), table
