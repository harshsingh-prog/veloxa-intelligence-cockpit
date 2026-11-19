"""Accuracy gate: every golden / held-out / fresh question must pass, with no ungrounded numbers and no salary leakage."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import evaluate_accuracy as E  # noqa: E402
from eval import fresh, golden, heldout  # noqa: E402

CORPUS = None


def _all():
    for mod in (golden, heldout, fresh):
        for c in mod.cases():
            for q in c["qs"]:
                yield pytest.param(c, q, id=f"{c['id']}::{q[:50]}")


@pytest.fixture(scope="module")
def corpus():
    return E.source_corpus()


@pytest.mark.parametrize("case,q", list(_all()))
def test_question(case, q, corpus):
    r = E.check_case(case, q, corpus)
    assert r["ok"], f"{r['fails']} -> {r['answer'][:200]}"
    assert not r["ungrounded"], f"numbers not traceable to cited sources: {r['ungrounded']}"
    assert not r["leak"]


def test_llm_guard_blocks_every_hostile_output():
    blocked, total, details = E.llm_attack()
    assert blocked == total, details
    assert details[0][1], "a faithful rewrite must be accepted"
