"""Evaluate the RAG pipeline on a workspace.

    python manage.py eval_rag                                   # retrieval only: no API calls
    python manage.py eval_rag --answer-provider groq --judge-provider gemini --category lookup_total

The judge must be a different provider than the answerer. Calls are paced (--min-interval seconds),
judge verdicts are cached on disk, and --category limits the run to one category per invocation.
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import yaml
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.evaluation.rag_eval import JudgeCache, answer_metrics, retrieval_metrics
from apps.llm.client import LLMClient, Provider
from apps.llm.pacing import Paced
from apps.workspaces.models import Workspace

KEYS = {"groq": ("groq", "GROQ_MODEL", "openai/gpt-oss-120b", "GROQ_API_KEY"),
        "gemini": ("google_genai", "GEMINI_MODEL", "gemini-3.1-flash-lite", "GOOGLE_API_KEY")}  # fmt: skip


def make_client(name: str, min_interval: float) -> LLMClient:
    from langchain.chat_models import init_chat_model

    provider, model_env, default_model, key_env = KEYS[name]
    if not os.environ.get(key_env):
        raise CommandError(f"{key_env} is not set (free-tier key for {name}).")
    chat = init_chat_model(
        os.environ.get(model_env, default_model), model_provider=provider, temperature=0
    )
    return LLMClient([Provider(name, Paced(chat, min_interval))], max_retries=4, max_wait=90)


def git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:  # noqa: BLE001
        return "unknown"


class Command(BaseCommand):
    help = "Evaluate retrieval (and optionally LLM answers with a cross-provider judge)."

    def add_arguments(self, parser):
        parser.add_argument("--workspace", default="demo-traders")
        parser.add_argument(
            "--questions",
            default=str(Path(settings.BASE_DIR).parent / "eval" / "rag_questions.yaml"),
        )
        parser.add_argument("--category")
        parser.add_argument("--answer-provider", choices=list(KEYS))
        parser.add_argument("--judge-provider", choices=list(KEYS))
        parser.add_argument("--min-interval", type=float, default=2.5)
        parser.add_argument(
            "--cache-dir", default=str(Path(settings.BASE_DIR).parent / "ml" / ".cache" / "judge")
        )
        parser.add_argument("--out")

    def handle(self, *args, **o):
        ws = Workspace.objects.filter(slug=o["workspace"]).first()
        if ws is None:
            raise CommandError(f"workspace {o['workspace']!r} not found (run seed_demo)")
        qs = yaml.safe_load(Path(o["questions"]).read_text(encoding="utf-8"))["questions"]
        if o["category"]:
            qs = [q for q in qs if q["category"] == o["category"]]
        if not qs:
            raise CommandError("no questions selected")

        metrics = {"retrieval": retrieval_metrics(ws.id, qs)}
        mode = "retrieval"
        if o["answer_provider"] or o["judge_provider"]:
            if not (o["answer_provider"] and o["judge_provider"]):
                raise CommandError("give both --answer-provider and --judge-provider")
            if o["answer_provider"] == o["judge_provider"]:
                raise CommandError("the judge must be a different provider than the answerer")
            metrics["answers"] = answer_metrics(
                ws.id, qs,
                make_client(o["answer_provider"], o["min_interval"]),
                make_client(o["judge_provider"], o["min_interval"]),
                judge_cache=JudgeCache(Path(o["cache_dir"])),
            )  # fmt: skip
            mode = f"answers-{o['answer_provider']}-judge-{o['judge_provider']}"
        from apps.rag.service import get_embedder, get_reranker

        payload = {
            "kind": "rag",
            "dataset": f"demo-workspace ({len(qs)} questions"
            + (f", {o['category']})" if o["category"] else ")"),
            "arm": f"{mode} | {get_embedder().name} + {get_reranker().name}",
            "n": len(qs),
            "git_sha": git_sha(),
            "created_at": datetime.now(UTC).isoformat(),
            "metrics": {
                **{k: v for k, v in metrics["retrieval"].items() if k != "per_question"},
                **(
                    {
                        "answers": {
                            k: v for k, v in metrics["answers"].items() if k != "per_question"
                        }
                    }
                    if "answers" in metrics
                    else {}
                ),
            },  # fmt: skip
            "docs": [],
        }
        out = Path(
            o["out"]
            or Path(settings.BASE_DIR).parent
            / "docs"
            / "eval-results"
            / f"rag-{mode}{('-' + o['category']) if o['category'] else ''}.json"
        )
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps({**payload, "per_question": metrics}, indent=1, ensure_ascii=False),
            encoding="utf-8",
        )
        r = metrics["retrieval"]
        self.stdout.write(
            f"hit@5={r['hit_at_5']} mrr={r['mrr']} gate-rejected={r['unanswerable_rejected_by_gate']} -> {out}"
        )
