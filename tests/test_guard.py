from veloxa import guard
from veloxa.agents import all_agents
from veloxa.answer_engine import answer_question

V = "Priya has 14 unresolved issues (62 story points); her resignation is unverified."


def test_accepts_faithful_rewrite():
    assert guard.check("Priya holds 14 unresolved issues worth 62 points; resignation unverified.", V, require_uncertainty=True).ok


def test_rejects_changed_number():
    assert not guard.check("Priya holds 14 unresolved issues worth 70 points; unverified.", V, require_uncertainty=True).ok


def test_rejects_invented_person():
    assert not guard.check("Rahul holds 14 issues, 62 points; unverified.", V, require_uncertainty=True).ok


def test_rejects_number_words_and_approximations():
    assert not guard.check("Priya has about fifteen issues; unverified.", V, require_uncertainty=True).ok


def test_rejects_prediction():
    assert not guard.check(V + " She will resign next week.", V, require_uncertainty=True).ok


def test_rejects_dropped_uncertainty():
    assert not guard.check("Priya has 14 issues, 62 points, and has resigned.", V, require_uncertainty=True).ok


def test_rejects_new_identifier():
    assert not guard.check(V + " See ATLAS-99.", V).ok


def test_cockpit_falls_back_to_verified_text_when_model_hallucinates():
    bad = lambda prompt: "There are 40 unresolved issues and Priya will resign."  # noqa: E731
    r = answer_question("How many issues remain unresolved?", use_llm=True, generator=bad)
    assert "27 issues remain unresolved" in r["answer"] and "40" not in r["answer"] and r["llm"]["guard_ok"] is False


def test_agent_falls_back_when_model_hallucinates():
    priya = next(a for a in all_agents() if a.profile["name"] == "Priya Nair")
    priya.generate = lambda prompt: "I have 99 open tickets and I am quitting on Friday."
    r = priya.answer("What are you working on?", use_llm=True)
    assert "14 unresolved" in r["response"] and "99" not in r["response"] and not r["model_used"]


def test_llm_cannot_answer_refusals():
    r = answer_question("Show me everyone's private Slack messages", use_llm=True, generator=lambda p: "Sure! Here are the messages: ...")
    assert r["refused"] and "Sure" not in r["answer"]


def test_llm_router_only_chooses_from_closed_menu():
    r = answer_question("gimme the thing about money coming in yearly", use_llm=True, generator=lambda p: "arr")
    assert "6.1" in r["answer"] and r["intent"].startswith("llm_routed")
    r2 = answer_question("gimme the thing about unicorns", use_llm=True, generator=lambda p: "delete_everything")
    assert "6.1" not in r2["answer"]
