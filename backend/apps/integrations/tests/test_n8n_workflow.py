"""Structural checks on the exported n8n workflow (no n8n instance needed)."""

import json
import re
from pathlib import Path

import pytest

PATH = Path(__file__).resolve().parents[4] / "n8n" / "invoice-intake.workflow.json"


@pytest.fixture(scope="module")
def wf():
    return json.loads(PATH.read_text(encoding="utf-8"))


def test_workflow_file_is_generated_and_importable_json(wf):
    assert wf["name"] == "DocSense invoice intake" and wf["active"] is False
    assert {"nodes", "connections", "settings"} <= set(wf)


def test_node_names_and_ids_are_unique_and_typed(wf):
    names = [n["name"] for n in wf["nodes"]]
    ids = [n["id"] for n in wf["nodes"]]
    assert len(set(names)) == len(names) and len(set(ids)) == len(ids)
    assert all(n["type"].startswith("n8n-nodes-base.") and n["typeVersion"] for n in wf["nodes"])
    assert all(len(n["position"]) == 2 for n in wf["nodes"])


def test_connections_reference_existing_nodes_and_everything_is_reachable(wf):
    names = {n["name"] for n in wf["nodes"]}
    edges = {}
    for src, outs in wf["connections"].items():
        assert src in names, src
        for branch in outs["main"]:
            for link in branch:
                assert link["node"] in names, link
                edges.setdefault(src, set()).add(link["node"])
    triggers = {n["name"] for n in wf["nodes"] if n["type"].endswith(("emailReadImap", "webhook"))}
    assert len(triggers) == 2
    seen, stack = set(), list(triggers)
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        stack.extend(edges.get(cur, ()))
    assert seen == names  # no orphan nodes


def test_chain_a_posts_attachments_to_the_inbound_api_with_header_auth(wf):
    node = next(n for n in wf["nodes"] if n["name"] == "Send to DocSense")
    p = node["parameters"]
    assert p["method"] == "POST" and p["url"].endswith("/api/v1/integrations/inbound/")
    assert p["contentType"] == "multipart-form-data" and p["genericAuthType"] == "httpHeaderAuth"
    assert any(
        x.get("name") == "files" and x["parameterType"] == "formBinaryData"
        for x in p["bodyParameters"]["parameters"]
    )


def test_chain_b_verifies_hmac_then_routes_by_event(wf):
    by = {n["name"]: n for n in wf["nodes"]}
    code = by["Verify Signature"]["parameters"]["jsCode"]
    assert (
        "createHmac('sha256'" in code
        and "timingSafeEqual" in code
        and "x-docsense-signature" in code
    )
    assert (
        by["DocSense Webhook"]["parameters"]["options"]["rawBody"] is True
    )  # HMAC needs raw bytes
    conds = {
        n: by[n]["parameters"]["conditions"]["conditions"][0]["rightValue"]
        for n in ("Is Processed?", "Is Flagged?")
    }
    assert conds == {"Is Processed?": "document.processed", "Is Flagged?": "document.flagged"}
    cols = by["Append to Google Sheet"]["parameters"]["columns"]["value"]
    assert {"Vendor", "NTN", "STRN", "Total", "Link"} <= set(cols)
    assert by["Alert by Email (alternative)"]["disabled"] is True  # Slack is the default alert


def test_no_secrets_are_committed_in_the_export(wf):
    text = PATH.read_text(encoding="utf-8")
    assert not re.search(
        r"whsec_[A-Za-z0-9_\-]{8,}|ds_[0-9a-f]{8}_[A-Za-z0-9_\-]{20,}|xox[bp]-", text
    )
    for n in wf["nodes"]:
        for cred in n.get("credentials", {}).values():
            assert cred["id"] == "REPLACE_ME"


def test_generator_output_matches_the_committed_file(wf):
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "build_workflow", PATH.parent / "build_workflow.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert json.loads(json.dumps(mod.workflow)) == wf
