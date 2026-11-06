"""Agent tools. Read-only by construction:

* `run_query` compiles a *structured spec* (never SQL) through the Django ORM, against a whitelist
  of tables/columns, with the workspace filter injected in code from trusted state.
* `build_chart` derives chart data from rows a previous query already returned (the model never
  types numbers into a chart).
* `price_changes` computes first-vs-latest unit price per vendor/item in code.
* `search_documents` reuses the cited RAG retrieval.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Literal

from django.db.models import Avg, Count, F, Max, Min, Sum
from pydantic import BaseModel, Field

from apps.analytics.detectors import item_key
from apps.documents.models import Invoice, InvoiceLineItem, Vendor

MAX_LIMIT = 200
MAX_FILTERS, MAX_GROUPS, MAX_AGGS = 6, 3, 4


class ToolError(Exception):
    """Invalid tool input: reported back to the model so it can correct itself."""


# --------------------------------------------------------------------------- whitelist
# public column name -> (ORM lookup, kind)
TABLES: dict[str, dict] = {
    "invoices": {
        "model": Invoice,
        "scope": "workspace_id",
        "columns": {
            "invoice_number": ("invoice_number", "str"),
            "invoice_date": ("invoice_date", "date"),
            "currency": ("currency", "str"),
            "subtotal": ("subtotal", "num"),
            "tax_rate": ("tax_rate", "num"),
            "sales_tax": ("sales_tax", "num"),
            "total": ("total", "num"),
            "category": ("category", "str"),
            "vendor_name": ("vendor__name", "str"),
            "ntn": ("ntn", "str"),
            "strn": ("strn", "str"),
        },
    },
    "line_items": {
        "model": InvoiceLineItem,
        "scope": "invoice__workspace_id",
        "columns": {
            "description": ("description", "str"),
            "quantity": ("quantity", "num"),
            "unit_price": ("unit_price", "num"),
            "amount": ("amount", "num"),
            "invoice_date": ("invoice__invoice_date", "date"),
            "vendor_name": ("invoice__vendor__name", "str"),
            "category": ("invoice__category", "str"),
            "invoice_number": ("invoice__invoice_number", "str"),
        },
    },
    "vendors": {
        "model": Vendor,
        "scope": "workspace_id",
        "columns": {"name": ("name", "str"), "ntn": ("ntn", "str")},
    },
}

OPS = {
    "=": "", "!=": "", ">": "__gt", ">=": "__gte", "<": "__lt", "<=": "__lte",
    "contains": "__icontains", "in": "__in",
}  # fmt: skip
AGGS = {"sum": Sum, "avg": Avg, "min": Min, "max": Max, "count": Count}


class Filter(BaseModel):
    column: str
    op: Literal["=", "!=", ">", ">=", "<", "<=", "contains", "in"] = "="
    value: str | float | int | list[str | float | int]


class Aggregation(BaseModel):
    fn: Literal["sum", "avg", "min", "max", "count"]
    column: str | None = Field(None, description="Column to aggregate (omit for count)")
    alias: str = Field(description="Output name, letters/digits/underscore")


class OrderBy(BaseModel):
    column: str = Field(description="A selected column or an aggregation alias")
    direction: Literal["asc", "desc"] = "desc"


class QuerySpec(BaseModel):
    """A read-only analytic query. Tables: invoices, line_items, vendors."""

    table: Literal["invoices", "line_items", "vendors"]
    select: list[str] = Field(default_factory=list, description="Plain columns (no aggregation)")
    filters: list[Filter] = Field(default_factory=list)
    group_by: list[str] = Field(default_factory=list)
    aggregations: list[Aggregation] = Field(default_factory=list)
    order_by: list[OrderBy] = Field(default_factory=list)
    limit: int = Field(50, description=f"Max rows (<= {MAX_LIMIT})")


# --------------------------------------------------------------------------- query
def _coerce(kind: str, v):
    try:
        if kind == "date":
            return v if isinstance(v, date) else date.fromisoformat(str(v))
        if kind == "num":
            return Decimal(str(v))
        return str(v)
    except Exception as exc:  # noqa: BLE001
        raise ToolError(f"Cannot use {v!r} as a {kind} value") from exc


def _jsonable(v):
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, date):
        return v.isoformat()
    return v


def run_query(spec: QuerySpec, workspace_id: int) -> dict:
    """Execute a spec. `workspace_id` comes from trusted agent state, never from the model."""
    table = TABLES[spec.table]
    cols = table["columns"]

    def col(name: str) -> tuple[str, str]:
        if name not in cols:
            raise ToolError(f"Unknown column {name!r} for {spec.table}. Allowed: {sorted(cols)}")
        return cols[name]

    if len(spec.filters) > MAX_FILTERS or len(spec.group_by) > MAX_GROUPS:
        raise ToolError("Too many filters or group_by columns")
    if len(spec.aggregations) > MAX_AGGS:
        raise ToolError("Too many aggregations")
    qs = table["model"].objects.filter(**{table["scope"]: workspace_id})  # enforced in code

    for f in spec.filters:
        lookup, kind = col(f.column)
        if f.op == "in":
            vals = f.value if isinstance(f.value, list) else [f.value]
            qs = qs.filter(**{f"{lookup}__in": [_coerce(kind, v) for v in vals]})
            continue
        if isinstance(f.value, list):
            raise ToolError("List values are only allowed with op 'in'")
        cond = {lookup + OPS[f.op]: _coerce(kind, f.value)}
        qs = qs.exclude(**cond) if f.op == "!=" else qs.filter(**cond)

    names: list[str] = []
    aliases = {}
    if spec.aggregations or spec.group_by:
        group_names = spec.group_by or []
        for g in group_names:
            col(g)
        annos = {}
        for a in spec.aggregations:
            if not a.alias.isidentifier() or a.alias in cols:
                raise ToolError(f"Bad alias {a.alias!r}")
            if a.fn == "count":
                annos[a.alias] = Count("id")
            else:
                if not a.column:
                    raise ToolError(f"{a.fn} needs a column")
                lookup, kind = col(a.column)
                if kind == "str" and a.fn in ("sum", "avg"):
                    raise ToolError(f"Cannot {a.fn} text column {a.column!r}")
                annos[a.alias] = AGGS[a.fn](lookup)
        values = {g: cols[g][0] for g in group_names}
        if values:
            qs = qs.annotate(**{f"g_{g}": F(lk) for g, lk in values.items()})
        if not group_names:  # a single aggregate row; never fall back to values() with no fields
            if not annos:
                raise ToolError("Give at least one aggregation or a group_by")
            row = qs.aggregate(**annos)
            return {
                "columns": list(annos),
                "rows": [{k: _jsonable(v) for k, v in row.items()}],
                "row_count": 1,
                "truncated": False,
            }
        qs = qs.values(*[f"g_{g}" for g in group_names]).annotate(**annos)
        names = [*group_names, *annos]
        aliases = {f"g_{g}": g for g in group_names}
    else:
        selected = spec.select or list(cols)
        for s in selected:
            col(s)
        qs = qs.values(*[cols[s][0] for s in selected])
        names = selected
        aliases = {cols[s][0]: s for s in selected}

    order = []
    allowed_sort = set(names) | set(spec.group_by)
    for o in spec.order_by:
        if o.column not in allowed_sort:
            raise ToolError(f"Cannot order by {o.column!r}; use a selected column or alias")
        key = f"g_{o.column}" if o.column in spec.group_by else (
            o.column if (spec.aggregations or spec.group_by) else cols[o.column][0]
        )  # fmt: skip
        order.append(("-" if o.direction == "desc" else "") + key)
    if order:
        qs = qs.order_by(*order)
    limit = max(1, min(int(spec.limit), MAX_LIMIT))
    rows = []
    for r in qs[:limit]:
        rows.append({aliases.get(k, k): _jsonable(v) for k, v in r.items()})
    return {"columns": names, "rows": rows, "row_count": len(rows), "truncated": len(rows) == limit}


# --------------------------------------------------------------------------- chart
class ChartArgs(BaseModel):
    query_step: int = Field(description="Index of an earlier query step to plot")
    x: str = Field(description="Column used for labels")
    y: str = Field(description="Numeric column used for bar length")
    title: str
    type: Literal["bar"] = "bar"


def build_chart(args: ChartArgs, step_results: dict[int, dict]) -> dict:
    res = step_results.get(args.query_step)
    if res is None:
        raise ToolError(f"No query result at step {args.query_step}")
    for c in (args.x, args.y):
        if c not in res["columns"]:
            raise ToolError(f"Column {c!r} not in that query result: {res['columns']}")
    points = []
    for r in res["rows"]:
        y = r[args.y]
        if not isinstance(y, int | float):
            raise ToolError(f"Column {args.y!r} is not numeric")
        points.append({"label": str(r[args.x]), "value": y})
    return {"type": args.type, "title": args.title, "points": points[:40]}


# --------------------------------------------------------------------------- price changes
class PriceChangeArgs(BaseModel):
    top_n: int = Field(5, description="How many biggest increases to return (<= 20)")
    vendor_name: str | None = None


def price_changes(args: PriceChangeArgs, workspace_id: int) -> dict:
    """First vs latest unit price per vendor + item (>= 2 observations), biggest increase first."""
    qs = InvoiceLineItem.objects.filter(
        invoice__workspace_id=workspace_id,
        unit_price__isnull=False,
        invoice__invoice_date__isnull=False,
    ).select_related("invoice__vendor")
    if args.vendor_name:
        qs = qs.filter(invoice__vendor__name__icontains=args.vendor_name)
    series: dict[tuple, list] = defaultdict(list)
    for li in qs.order_by("invoice__invoice_date", "id"):
        vendor = li.invoice.vendor.name if li.invoice.vendor_id else "Unknown vendor"
        series[(vendor, item_key(li.description))].append(
            (li.invoice.invoice_date, float(li.unit_price))
        )
    out = []
    for (vendor, item), pts in series.items():
        if len(pts) < 2 or pts[0][1] <= 0:
            continue
        first, last = pts[0], pts[-1]
        out.append(
            {
                "vendor": vendor, "item": item,
                "first_price": first[1], "first_date": first[0].isoformat(),
                "latest_price": last[1], "latest_date": last[0].isoformat(),
                "increase_pct": round((last[1] / first[1] - 1) * 100, 1), "observations": len(pts),
            }
        )  # fmt: skip
    out.sort(key=lambda r: -r["increase_pct"])
    rows = out[: max(1, min(args.top_n, 20))]
    return {
        "columns": list(rows[0]) if rows else [],
        "rows": rows,
        "row_count": len(rows),
        "truncated": False,
    }
