from rest_framework.response import Response

from apps.workspaces.views import WorkspaceScoped

from . import service
from .models import UniversePoint


class Points(WorkspaceScoped):
    def get(self, request, workspace_id):
        pts = UniversePoint.objects.filter(workspace_id=workspace_id).select_related(
            "document", "document__invoice", "document__invoice__vendor"
        )
        rows = []
        clusters: dict[int, dict] = {}
        for p in pts:
            inv = getattr(p.document, "invoice", None)
            rows.append(
                {
                    "id": p.document_id,
                    "name": p.document.original_name,
                    "x": p.x, "y": p.y, "z": p.z,
                    "cluster": p.cluster,
                    "vendor": inv.vendor.name if inv and inv.vendor_id else None,
                    "category": inv.category if inv else None,
                    "total": float(inv.total) if inv and inv.total is not None else None,
                    "date": inv.invoice_date.isoformat() if inv and inv.invoice_date else None,
                    "status": p.document.status,
                }
            )  # fmt: skip
            if p.cluster >= 0:
                c = clusters.setdefault(
                    p.cluster,
                    {"id": p.cluster, "label": p.cluster_label, "n": 0, "sum": [0.0, 0.0, 0.0]},
                )
                c["n"] += 1
                for i, v in enumerate((p.x, p.y, p.z)):
                    c["sum"][i] += v
        centroids = [
            {
                "id": c["id"],
                "label": c["label"],
                "n": c["n"],
                "centroid": [s / c["n"] for s in c["sum"]],
            }
            for c in clusters.values()
        ]
        return Response({"points": rows, "clusters": centroids})


class Rebuild(WorkspaceScoped):
    def post(self, request, workspace_id):
        return Response(service.rebuild(workspace_id))
