import json
import os
import re
from collections import Counter
from pathlib import Path

import yaml


BASE_DIR = Path(__file__).resolve().parent
MANUAL_PATH = BASE_DIR / "hospital_operations_manual.txt"
PROFILES_PATH = BASE_DIR / "agent_profiles.yaml"
DEFAULT_AGENTS = ["hospital", "doctor", "nurse"]

AGENT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "summary": {"type": "string"},
        "findings": {"type": "array", "items": {"type": "string"}},
        "next_actions": {"type": "array", "items": {"type": "string"}},
        "risk_level": {"type": "string", "enum": ["low", "medium", "high", "critical"]},
        "citations": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "findings", "next_actions", "risk_level", "citations"],
}

FINAL_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "case_summary": {"type": "string"},
        "agent_consensus": {"type": "string"},
        "recommended_actions": {"type": "array", "items": {"type": "string"}},
        "monitoring_priorities": {"type": "array", "items": {"type": "string"}},
        "escalation_level": {"type": "string", "enum": ["routine", "urgent", "emergent"]},
        "handoff": {"type": "string"},
        "disclaimer": {"type": "string"},
    },
    "required": [
        "case_summary",
        "agent_consensus",
        "recommended_actions",
        "monitoring_priorities",
        "escalation_level",
        "handoff",
        "disclaimer",
    ],
}


def http_response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {"content-type": "application/json", "access-control-allow-origin": "*"},
        "body": json.dumps(body),
    }


def parse_event(event):
    body = event.get("body", event)
    if isinstance(body, str):
        return json.loads(body or "{}")
    return body or {}


def tokenize(text):
    return re.findall(r"[a-z0-9]+", text.lower())


def load_manual(path=MANUAL_PATH):
    content = Path(path).read_text(encoding="utf-8").strip()
    sections = [section.strip() for section in re.split(r"\n\s*\n", content) if section.strip()]
    documents = []
    for index, section in enumerate(sections, start=1):
        title = section.splitlines()[0].lstrip("# ").strip()
        documents.append(
            {
                "id": f"manual-{index}",
                "title": title,
                "source": Path(path).name,
                "content": section,
            }
        )
    return documents


def build_query(payload):
    return json.dumps(
        {
            "task": payload.get("task", ""),
            "chief_concern": payload.get("chief_concern", ""),
            "patient_context": payload.get("patient_context", {}),
            "vitals": payload.get("vitals", {}),
            "signals": payload.get("signals", {}),
            "notes": payload.get("notes", []),
            "question": payload.get("question", ""),
        },
        sort_keys=True,
    )


def retrieve(payload, documents=None):
    documents = documents or load_manual(payload.get("manual_path") or os.getenv("RAG_MANUAL_PATH", MANUAL_PATH))
    query_terms = Counter(tokenize(build_query(payload)))
    scored = []
    for document in documents:
        document_terms = Counter(tokenize(document["title"] + "\n" + document["content"]))
        score = sum(query_terms[term] * document_terms.get(term, 0) for term in query_terms)
        scored.append((score, document))

    scored.sort(key=lambda item: item[0], reverse=True)
    selected = [document for score, document in scored if score > 0]
    if not selected:
        selected = [document for _, document in scored]
    top_k = int(payload.get("top_k") or os.getenv("RAG_TOP_K", "4"))
    return selected[:top_k]


def load_profiles():
    return yaml.safe_load(PROFILES_PATH.read_text(encoding="utf-8"))


def get_openai_api_key():
    direct_key = os.getenv("OPENAI_API_KEY")
    if direct_key:
        return direct_key

    secret_arn = os.getenv("OPENAI_API_KEY_SECRET_ARN")
    if not secret_arn:
        raise RuntimeError("Set OPENAI_API_KEY or OPENAI_API_KEY_SECRET_ARN.")

    import boto3

    return boto3.client("secretsmanager").get_secret_value(SecretId=secret_arn)["SecretString"]


def response_text(result):
    if hasattr(result, "output_text"):
        return result.output_text
    return json.dumps(result)


def call_openai_agent(client, agent_name, profile, payload, retrieved_context, prior_outputs):
    model = payload.get("model") or profile.get("model") or os.getenv("OPENAI_MODEL", "gpt-5.2")
    result = client.responses.create(
        model=model,
        instructions=profile["instructions"],
        input=json.dumps(
            {
                "patient_event": payload,
                "retrieved_context": retrieved_context,
                "prior_agent_outputs": prior_outputs,
            },
            indent=2,
        ),
        text={
            "format": {
                "type": "json_schema",
                "name": f"{agent_name}_agent_output",
                "schema": AGENT_SCHEMA,
                "strict": True,
            }
        },
        max_output_tokens=int(payload.get("max_output_tokens") or os.getenv("MAX_OUTPUT_TOKENS", "1200")),
    )
    return json.loads(response_text(result))


def call_final_synthesis(client, payload, retrieved_context, agent_outputs):
    result = client.responses.create(
        model=payload.get("model") or os.getenv("OPENAI_MODEL", "gpt-5.2"),
        instructions=(
            "Synthesize Agent 1 hospital, Agent 2 doctor, and Agent 3 nurse outputs "
            "into one grounded hospital decision-support response. Use retrieved "
            "manual sections as citations. Do not provide a final diagnosis."
        ),
        input=json.dumps(
            {
                "patient_event": payload,
                "retrieved_context": retrieved_context,
                "agent_outputs": agent_outputs,
            },
            indent=2,
        ),
        text={
            "format": {
                "type": "json_schema",
                "name": "agentic_hospital_rag_output",
                "schema": FINAL_SCHEMA,
                "strict": True,
            }
        },
        max_output_tokens=int(payload.get("max_output_tokens") or os.getenv("MAX_OUTPUT_TOKENS", "1200")),
    )
    return json.loads(response_text(result))


def local_agent_result(agent_name, retrieved_context, payload):
    titles = [document["title"] for document in retrieved_context]
    concern = payload.get("chief_concern") or payload.get("question") or "hospital event"
    risk_level = "critical" if any(term in build_query(payload).lower() for term in ["hypotension", "stroke", "chest", "sepsis", "oxygen"]) else "medium"
    return {
        "summary": f"{agent_name} reviewed {concern} against the hospital manual.",
        "findings": [f"Relevant manual section: {title}" for title in titles[:3]],
        "next_actions": [f"{agent_name} should follow the retrieved policy sections before escalation."],
        "risk_level": risk_level,
        "citations": titles,
    }


def local_synthesis(payload, retrieved_context, agent_outputs):
    query = build_query(payload).lower()
    emergent_terms = [
        "stroke",
        "facial droop",
        "arm weakness",
        "speech difficulty",
        "last known well",
        "chest",
        "oxygen",
        "hypotension",
        "sepsis",
    ]
    escalation = "emergent" if any(term in query for term in emergent_terms) else "urgent"
    return {
        "case_summary": payload.get("chief_concern") or payload.get("question") or "Hospital RAG request",
        "agent_consensus": "Hospital, doctor, and nurse agents agree to use the retrieved manual sections as the operating basis.",
        "recommended_actions": [
            "Route the event according to the highest acuity retrieved policy.",
            "Record manual citations and final human reviewer in the encounter.",
        ],
        "monitoring_priorities": [document["title"] for document in retrieved_context[:3]],
        "escalation_level": escalation,
        "handoff": "Use bedside handoff for unstable patients and repeat back the two highest risk issues.",
        "disclaimer": "Decision support only; clinicians remain responsible for assessment, diagnosis, treatment, and disposition.",
    }


def lambda_handler(event, context):
    try:
        payload = parse_event(event)
        profiles = load_profiles()
        requested_agents = payload.get("agents") or DEFAULT_AGENTS
        unknown_agents = [agent for agent in requested_agents if agent not in profiles]
        if unknown_agents:
            return http_response(400, {"error": "Unknown agent requested.", "unknown_agents": unknown_agents})

        retrieved_context = retrieve(payload)
        use_local = payload.get("local_mode") or os.getenv("APP_MODE", "").lower() == "local"
        agent_outputs = []

        if use_local:
            for agent_name in requested_agents:
                agent_outputs.append({"agent": agent_name, "result": local_agent_result(agent_name, retrieved_context, payload)})
            final = local_synthesis(payload, retrieved_context, agent_outputs)
        else:
            from openai import OpenAI

            client = OpenAI(api_key=get_openai_api_key())
            for agent_name in requested_agents:
                agent_outputs.append(
                    {
                        "agent": agent_name,
                        "result": call_openai_agent(
                            client,
                            agent_name,
                            profiles[agent_name],
                            payload,
                            retrieved_context,
                            agent_outputs,
                        ),
                    }
                )
            final = call_final_synthesis(client, payload, retrieved_context, agent_outputs)

        return http_response(
            200,
            {
                "retrieved_context": retrieved_context,
                "agents": agent_outputs,
                "inference": final,
            },
        )
    except Exception as exc:
        return http_response(500, {"error": str(exc)})
