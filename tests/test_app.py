import json
import os

from src.app import lambda_handler, load_manual, retrieve


def test_retrieve_chest_pain_manual_sections():
    payload = {
        "chief_concern": "Chest pressure with oxygen saturation 90 and pain score 8",
        "notes": ["left arm pain", "needs ECG"],
        "top_k": 3,
    }

    titles = [document["title"] for document in retrieve(payload, load_manual())]

    assert "Emergency Department Chest Pain Intake" in titles
    assert "Doctor Clinical Review Standard" in titles or "Nurse Handoff Standard" in titles


def test_lambda_handler_local_mode_runs_three_agents(monkeypatch):
    monkeypatch.setitem(os.environ, "APP_MODE", "local")
    response = lambda_handler({"body": json.dumps({"chief_concern": "possible stroke", "top_k": 2})}, None)
    body = json.loads(response["body"])

    assert response["statusCode"] == 200
    assert [agent["agent"] for agent in body["agents"]] == ["hospital", "doctor", "nurse"]
    assert body["inference"]["escalation_level"] == "emergent"
    assert body["retrieved_context"]


def test_lambda_handler_local_mode_escalates_stroke_symptoms(monkeypatch):
    monkeypatch.setitem(os.environ, "APP_MODE", "local")
    response = lambda_handler(
        {"body": json.dumps({"chief_concern": "facial droop arm weakness speech difficulty", "top_k": 2})},
        None,
    )
    body = json.loads(response["body"])

    assert response["statusCode"] == 200
    assert body["inference"]["escalation_level"] == "emergent"


def test_unknown_agent_returns_400(monkeypatch):
    monkeypatch.setitem(os.environ, "APP_MODE", "local")
    response = lambda_handler({"body": json.dumps({"agents": ["pharmacy"]})}, None)
    body = json.loads(response["body"])

    assert response["statusCode"] == 400
    assert body["unknown_agents"] == ["pharmacy"]
