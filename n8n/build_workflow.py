"""Generates n8n/invoice-intake.workflow.json (importable via n8n: Workflows > Import from file).

    python n8n/build_workflow.py

Two chains in one workflow:
  A) Email with attachment  -> DocSense inbound API (processing is asynchronous)
  B) DocSense webhook       -> verify HMAC -> append row to Google Sheets
                               -> if document.flagged -> Slack alert (email alternative disabled)
"""

import json
from pathlib import Path

SPLIT_ATTACHMENTS = """\
// One output item per supported attachment, with the file under binary.data
const ok = /\\.(pdf|png|jpe?g|webp)$/i;
const out = [];
for (const item of $input.all()) {
  for (const [key, bin] of Object.entries(item.binary || {})) {
    if (!ok.test(bin.fileName || '')) continue;
    out.push({
      json: { subject: item.json.subject || '', from: item.json.from?.text || '' },
      binary: { data: bin },
    });
  }
}
return out;
"""

VERIFY_SIGNATURE = """\
// Verify X-DocSense-Signature = HMAC-SHA256(secret, `${timestamp}.${rawBody}`) and reject replays.
// Needs: Webhook node option "Raw Body" = on, env DOCSENSE_WEBHOOK_SECRET,
//        NODE_FUNCTION_ALLOW_BUILTIN=crypto
const crypto = require('crypto');
const item = $input.first();
const headers = item.json.headers || {};
const secret = $env.DOCSENSE_WEBHOOK_SECRET;
if (!secret) throw new Error('DOCSENSE_WEBHOOK_SECRET is not set');
const ts = headers['x-docsense-timestamp'];
const sig = headers['x-docsense-signature'] || '';
const raw = Buffer.from(item.binary.data.data, 'base64');
const expected = 'sha256=' + crypto.createHmac('sha256', secret).update(ts + '.').update(raw).digest('hex');
const a = Buffer.from(sig), b = Buffer.from(expected);
if (a.length !== b.length || !crypto.timingSafeEqual(a, b)) throw new Error('Bad DocSense signature');
if (Math.abs(Date.now() / 1000 - Number(ts)) > 300) throw new Error('Stale DocSense webhook (replay?)');
return [{ json: JSON.parse(raw.toString('utf8')) }];
"""


def if_event(name: str, node_id: str, event: str, pos):
    return {
        "id": node_id,
        "name": name,
        "type": "n8n-nodes-base.if",
        "typeVersion": 2,
        "position": pos,
        "parameters": {
            "conditions": {
                "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict"},
                "conditions": [
                    {
                        "id": f"cond-{node_id}",
                        "leftValue": "={{ $json.event }}",
                        "rightValue": event,
                        "operator": {"type": "string", "operation": "equals"},
                    }
                ],
                "combinator": "and",
            },
            "options": {},
        },
    }


COLUMNS = {
    "Added": "={{ $json.created_at }}",
    "Document": "={{ $json.document.name }}",
    "Vendor": "={{ $json.extraction.vendor_name }}",
    "NTN": "={{ $json.extraction.ntn }}",
    "STRN": "={{ $json.extraction.strn }}",
    "Invoice No": "={{ $json.extraction.invoice_number }}",
    "Invoice Date": "={{ $json.extraction.invoice_date }}",
    "Subtotal": "={{ $json.extraction.subtotal }}",
    "Sales Tax": "={{ $json.extraction.sales_tax }}",
    "Total": "={{ $json.extraction.total }}",
    "Needs Review": "={{ $json.document.needs_review }}",
    "Confidence": "={{ $json.document.overall_confidence }}",
    "Issues": "={{ $json.issues.join(', ') }}",
    "Link": "={{ $json.document.url }}",
}

nodes = [
    # ---------------- A) email intake
    {
        "id": "a1", "name": "New Email (IMAP)", "type": "n8n-nodes-base.emailReadImap",
        "typeVersion": 2, "position": [0, 0],
        "parameters": {"mailbox": "INBOX", "postProcessAction": "read", "format": "resolved",
                       "downloadAttachments": True, "options": {}},
        "credentials": {"imap": {"id": "REPLACE_ME", "name": "Invoices mailbox (IMAP)"}},
    },  # fmt: skip
    {
        "id": "a2", "name": "Split Attachments", "type": "n8n-nodes-base.code",
        "typeVersion": 2, "position": [240, 0],
        "parameters": {"jsCode": SPLIT_ATTACHMENTS},
    },  # fmt: skip
    {
        "id": "a3", "name": "Send to DocSense", "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2, "position": [480, 0],
        "parameters": {
            "method": "POST",
            "url": "={{ $env.DOCSENSE_URL }}/api/v1/integrations/inbound/",
            "authentication": "genericCredentialType",
            "genericAuthType": "httpHeaderAuth",
            "sendBody": True,
            "contentType": "multipart-form-data",
            "bodyParameters": {
                "parameters": [
                    {"parameterType": "formBinaryData", "name": "files", "inputDataFieldName": "data"},
                    {"name": "source", "value": "n8n-email"},
                    {"name": "sender", "value": "={{ $json.from }}"},
                    {"name": "subject", "value": "={{ $json.subject }}"},
                ]
            },
            "options": {"timeout": 60000},
        },
        "credentials": {"httpHeaderAuth": {"id": "REPLACE_ME", "name": "DocSense API key (X-API-Key)"}},
    },  # fmt: skip
    # ---------------- B) webhook receiver
    {
        "id": "b1", "name": "DocSense Webhook", "type": "n8n-nodes-base.webhook",
        "typeVersion": 2, "position": [0, 360], "webhookId": "docsense-events",
        "parameters": {"httpMethod": "POST", "path": "docsense", "responseMode": "onReceived",
                       "options": {"rawBody": True}},
    },  # fmt: skip
    {
        "id": "b2", "name": "Verify Signature", "type": "n8n-nodes-base.code",
        "typeVersion": 2, "position": [240, 360],
        "parameters": {"jsCode": VERIFY_SIGNATURE},
    },  # fmt: skip
    if_event("Is Processed?", "b3", "document.processed", [480, 300]),
    {
        "id": "b4", "name": "Append to Google Sheet", "type": "n8n-nodes-base.googleSheets",
        "typeVersion": 4.5, "position": [720, 220],
        "parameters": {
            "operation": "append",
            "documentId": {"__rl": True, "mode": "id", "value": "REPLACE_WITH_SPREADSHEET_ID"},
            "sheetName": {"__rl": True, "mode": "name", "value": "Invoices"},
            "columns": {"mappingMode": "defineBelow", "value": COLUMNS, "matchingColumns": [],
                        "schema": []},
            "options": {},
        },
        "credentials": {"googleSheetsOAuth2Api": {"id": "REPLACE_ME", "name": "Google Sheets"}},
    },  # fmt: skip
    if_event("Is Flagged?", "b5", "document.flagged", [480, 460]),
    {
        "id": "b6", "name": "Alert on Slack", "type": "n8n-nodes-base.slack",
        "typeVersion": 2.2, "position": [720, 400],
        "parameters": {
            "authentication": "oAuth2",
            "select": "channel",
            "channelId": {"__rl": True, "mode": "name", "value": "#finance-alerts"},
            "text": ("=:warning: *DocSense flagged an invoice*\n"
                     "{{ $json.document.name }} ({{ $json.extraction.vendor_name }}, total "
                     "{{ $json.extraction.total }})\n"
                     "{{ $json.flags.map(f => f.kind + ' (' + f.severity + ')').join(', ') }}\n"
                     "{{ $json.document.url }}"),
            "otherOptions": {},
        },
        "credentials": {"slackOAuth2Api": {"id": "REPLACE_ME", "name": "Slack"}},
    },  # fmt: skip
    {
        "id": "b7", "name": "Alert by Email (alternative)", "type": "n8n-nodes-base.emailSend",
        "typeVersion": 2.1, "position": [720, 560], "disabled": True,
        "parameters": {
            "fromEmail": "docsense@example.com",
            "toEmail": "finance@example.com",
            "subject": "=DocSense flagged {{ $json.document.name }}",
            "emailFormat": "text",
            "text": ("={{ $json.document.name }} from {{ $json.extraction.vendor_name }} was flagged: "
                     "{{ $json.flags.map(f => f.kind).join(', ') }}\n{{ $json.document.url }}"),
            "options": {},
        },
        "credentials": {"smtp": {"id": "REPLACE_ME", "name": "SMTP"}},
    },  # fmt: skip
]


def link(src: str, dst: str, idx: int = 0):
    return {"node": dst, "type": "main", "index": idx}


connections = {
    "New Email (IMAP)": {"main": [[link("", "Split Attachments")]]},
    "Split Attachments": {"main": [[link("", "Send to DocSense")]]},
    "DocSense Webhook": {"main": [[link("", "Verify Signature")]]},
    "Verify Signature": {"main": [[link("", "Is Processed?"), link("", "Is Flagged?")]]},
    "Is Processed?": {"main": [[link("", "Append to Google Sheet")], []]},
    "Is Flagged?": {"main": [[link("", "Alert on Slack"), link("", "Alert by Email (alternative)")], []]},
}

workflow = {
    "name": "DocSense invoice intake",
    "nodes": nodes,
    "connections": connections,
    "active": False,
    "settings": {"executionOrder": "v1"},
    "pinData": {},
    "meta": {"templateCredsSetupCompleted": False},
    "tags": [],
}

if __name__ == "__main__":
    out = Path(__file__).parent / "invoice-intake.workflow.json"
    out.write_text(json.dumps(workflow, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("wrote", out)
