import json

import pytest
import yaml
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.evaluation.models import EvalRun
from apps.evaluation.rag_eval import JudgeCache, answer_metrics, contains_all, retrieval_metrics
from apps.llm.client import LLMClient, Provider
from apps.llm.fake import FakeChatModel
from apps.rag.embedding import HashEmbedder
from apps.rag.rerank import OverlapReranker
from apps.rag.tests.test_rag import make_doc

pytestmark = pytest.mark.django_db
EMB, RER = HashEmbedder(), OverlapReranker()

QUESTIONS = [
    {
        "id": "q1",
        "category": "lookup",
        "question": "What is the warranty period for LED panels?",
        "gold_docs": ["policy.pdf"],
        "gold_contains": ["24 months"],
        "answerable": True,
    },
    {
        "id": "q2",
        "category": "lookup",
        "question": "How much was the fuel purchase of petrol?",
        "gold_docs": ["fuel.png"],
        "gold_contains": ["12000"],
        "answerable": True,
    },
    {
        "id": "q3",
        "category": "lookup",
        "question": "Returns are accepted within how many days with the original receipt?",
        "gold_docs": ["wrong.pdf"],
        "gold_contains": ["7 days"],
        "answerable": True,
    },  # gold doc not in workspace
    {
        "id": "q4",
        "category": "unanswerable",
        "question": "Who won the cricket world cup in 1992?",
        "gold_docs": [],
        "gold_contains": [],
        "answerable": False,
    },
]


@pytest.fixture
def ws_docs(world):
    ws = world["ws"]
    make_doc(
        ws,
        "policy.pdf",
        [
            "Warranty terms for LED panels",
            "The warranty period is 24 months from purchase",
            "Returns are accepted within 7 days with the original receipt",
        ],
    )
    make_doc(
        ws,
        "fuel.png",
        ["Petrol pump receipt", "Fuel purchase 40 litres of petrol", "Total fuel cost 12000"],
    )
    return world


def llm(*script):
    return LLMClient([Provider("fake", FakeChatModel(list(script)))])


def test_contains_all_normalises_punctuation_and_case():
    assert contains_all("The total is PKR 3,540.00 only", ["3,540.00"])
    assert contains_all("Dated 2025-03-12.", ["2025-03-12"])
    assert not contains_all("The total is 3,500", ["3,540"])
    assert contains_all("anything", [])


def test_retrieval_metrics_hit_mrr_and_gate(ws_docs):
    m = retrieval_metrics(ws_docs["ws"].id, QUESTIONS, embedder=EMB, reranker=RER)
    assert m["n_questions"] == 4 and m["n_answerable"] == 3 and m["n_unanswerable"] == 1
    assert m["hit_at_5"] == pytest.approx(2 / 3, abs=1e-3)  # q3's gold doc does not exist
    assert 0.6 <= m["mrr"] <= 0.67 and m["unanswerable_rejected_by_gate"] == 1.0
    ranks = {p["id"]: p.get("rank") for p in m["per_question"]}
    assert ranks["q1"] == 1 and ranks["q2"] == 1 and ranks["q3"] is None
    assert m["hit_at_5_by_category"]["lookup"] == pytest.approx(2 / 3, abs=1e-3)


def test_answer_metrics_citations_facts_abstention_and_judge_cache(ws_docs, tmp_path):
    answerer = llm(
        {"answerable": True, "answer": "24 months.", "citations": [1]},  # q1 correct + cited
        {"answerable": True, "answer": "It was 9999.", "citations": [1]},  # q2 wrong fact
        {
            "answerable": True,
            "answer": "7 days.",
            "citations": [1],
        },  # q3 right fact, wrong doc cited
    )
    judge = FakeChatModel(
        [
            {"score": 5, "reason": "ok"},
            {"score": 1, "reason": "wrong"},
            {"score": 4, "reason": "ok"},
        ]
    )
    cache = JudgeCache(tmp_path)
    kw = dict(embedder=EMB, reranker=RER, judge_cache=cache)
    m = answer_metrics(
        ws_docs["ws"].id, QUESTIONS, answerer, LLMClient([Provider("j", judge)]), **kw
    )
    assert m["n_answerable"] == 3 and m["n_unanswerable"] == 1
    assert m["judge_score_mean_1_5"] == pytest.approx(10 / 3, abs=1e-3)
    assert m["exact_fact_rate"] == pytest.approx(2 / 3, abs=1e-3)
    assert m["citation_accuracy"] == pytest.approx(
        2 / 3, abs=1e-3
    )  # q3 cites policy.pdf, not its gold doc
    assert m["abstention_accuracy"] == 1.0  # q4 was gated: not grounded
    calls = len(judge.calls)
    answerer2 = llm(
        {"answerable": True, "answer": "24 months.", "citations": [1]},
        {"answerable": True, "answer": "It was 9999.", "citations": [1]},
        {"answerable": True, "answer": "7 days.", "citations": [1]},
    )
    answer_metrics(
        ws_docs["ws"].id, QUESTIONS, answerer2, LLMClient([Provider("j", FakeChatModel([]))]), **kw
    )
    assert len(judge.calls) == calls  # verdicts came from the cache: zero judge requests


def write_questions(tmp_path):
    p = tmp_path / "q.yaml"
    p.write_text(yaml.safe_dump({"questions": QUESTIONS}))
    return str(p)


def test_command_runs_retrieval_only_without_api_keys_and_result_is_importable(ws_docs, tmp_path):
    ws_docs["ws"].slug = "demo-traders"
    ws_docs["ws"].save()
    out = tmp_path / "rag.json"
    call_command("eval_rag", "--questions", write_questions(tmp_path), "--out", str(out))
    payload = json.loads(out.read_text())
    assert payload["kind"] == "rag" and payload["metrics"]["n_answerable"] == 3
    assert "hash-256" in payload["arm"] and "overlap" in payload["arm"]
    call_command("import_eval", str(out))
    run = EvalRun.objects.get(kind="rag")
    assert run.metrics["hit_at_5"] == pytest.approx(2 / 3, abs=1e-3)
    call_command(
        "eval_rag",
        "--questions",
        write_questions(tmp_path),
        "--category",
        "unanswerable",
        "--out",
        str(tmp_path / "u.json"),
    )
    assert json.loads((tmp_path / "u.json").read_text())["metrics"]["n_questions"] == 1


def test_command_refuses_same_provider_missing_pair_and_missing_keys(
    ws_docs, tmp_path, monkeypatch
):
    ws_docs["ws"].slug = "demo-traders"
    ws_docs["ws"].save()
    q = write_questions(tmp_path)
    with pytest.raises(CommandError, match="different provider"):
        call_command(
            "eval_rag", "--questions", q, "--answer-provider", "groq", "--judge-provider", "groq"
        )
    with pytest.raises(CommandError, match="both"):
        call_command("eval_rag", "--questions", q, "--answer-provider", "groq")
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    with pytest.raises(CommandError, match="GROQ_API_KEY"):
        call_command(
            "eval_rag", "--questions", q, "--answer-provider", "groq", "--judge-provider", "gemini"
        )
    with pytest.raises(CommandError, match="not found"):
        call_command("eval_rag", "--workspace", "nope", "--questions", q)
