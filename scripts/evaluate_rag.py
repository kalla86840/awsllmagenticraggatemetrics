import argparse
import json
import os
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.app import lambda_handler, load_manual, retrieve


CASES = [
    {
        "name": "chest_pain",
        "payload": {"chief_concern": "chest pain sweating low oxygen left arm pain", "top_k": 4},
        "expected": {"Emergency Department Chest Pain Intake"},
    },
    {
        "name": "sepsis",
        "payload": {"chief_concern": "suspected infection fever low blood pressure sepsis fluids", "top_k": 4},
        "expected": {"Sepsis Screening And Escalation"},
    },
    {
        "name": "stroke",
        "payload": {"chief_concern": "facial droop arm weakness speech difficulty last known well", "top_k": 4},
        "expected": {"Stroke Alert Workflow"},
    },
    {
        "name": "handoff",
        "payload": {"question": "What should a nurse handoff include for an unstable patient?", "top_k": 4},
        "expected": {"Nurse Handoff Standard"},
    },
]


AGENTIC_CASES = [
    {
        "name": "chest_pain_agentic",
        "payload": {
            "local_mode": True,
            "chief_concern": "chest pain sweating low oxygen left arm pain",
            "vitals": {"oxygen_saturation": 90, "systolic_bp": 88},
            "top_k": 4,
            "agents": ["hospital", "doctor", "nurse"],
        },
        "expected_escalation": "emergent",
    },
    {
        "name": "stroke_agentic",
        "payload": {
            "local_mode": True,
            "chief_concern": "facial droop arm weakness speech difficulty last known well",
            "top_k": 4,
            "agents": ["hospital", "doctor", "nurse"],
        },
        "expected_escalation": "emergent",
    },
]


def evaluate_retrieval_cases():
    documents = load_manual()
    results = []
    passed = 0
    for case in CASES:
        titles = {document["title"] for document in retrieve(case["payload"], documents)}
        matched = bool(case["expected"] & titles)
        passed += int(matched)
        status = "PASS" if matched else "FAIL"
        print(f"{status} {case['name']}: retrieved={sorted(titles)} expected={sorted(case['expected'])}")
        results.append(
            {
                "name": case["name"],
                "passed": matched,
                "retrieved_titles": sorted(titles),
                "expected_titles": sorted(case["expected"]),
            }
        )

    score = passed / len(CASES)
    print(f"RAG retrieval score: {score:.2%}")
    return {
        "score": score,
        "passed": passed,
        "total": len(CASES),
        "cases": results,
    }


def evaluate_agentic_cases():
    results = []
    passed = 0
    required_agents = ["hospital", "doctor", "nurse"]
    for case in AGENTIC_CASES:
        response = lambda_handler({"body": json.dumps(case["payload"])}, None)
        body = json.loads(response["body"])
        agent_names = [agent["agent"] for agent in body.get("agents", [])]
        citations = [
            citation
            for agent in body.get("agents", [])
            for citation in agent.get("result", {}).get("citations", [])
        ]
        escalation = body.get("inference", {}).get("escalation_level")
        matched = (
            response["statusCode"] == 200
            and agent_names == required_agents
            and bool(citations)
            and escalation == case["expected_escalation"]
        )
        passed += int(matched)
        status = "PASS" if matched else "FAIL"
        print(
            f"{status} {case['name']}: agents={agent_names} "
            f"escalation={escalation} citations={len(citations)}"
        )
        results.append(
            {
                "name": case["name"],
                "passed": matched,
                "agents": agent_names,
                "expected_agents": required_agents,
                "escalation": escalation,
                "expected_escalation": case["expected_escalation"],
                "citation_count": len(citations),
            }
        )

    score = passed / len(AGENTIC_CASES)
    print(f"Agentic RAG score: {score:.2%}")
    return {
        "score": score,
        "passed": passed,
        "total": len(AGENTIC_CASES),
        "cases": results,
    }


def evaluate_scorecard():
    retrieval = evaluate_retrieval_cases()
    agentic = evaluate_agentic_cases()
    overall_score = round((retrieval["score"] * 0.6) + (agentic["score"] * 0.4), 4)
    print(f"Overall agentic RAG score: {overall_score:.2%}")
    return {
        "metric_namespace": os.getenv("RAG_METRICS_NAMESPACE", "hospital-agentic-rag/RAG"),
        "metrics": {
            "RagRetrievalScore": retrieval["score"],
            "AgenticRagScore": agentic["score"],
            "OverallAgenticRagScore": overall_score,
        },
        "retrieval": retrieval,
        "agentic": agentic,
        "overall_score": overall_score,
    }


def write_metrics(metrics, output_path):
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote RAG metrics to {path}")


def main():
    parser = argparse.ArgumentParser(description="Evaluate local RAG retrieval quality and enforce a gate.")
    parser.add_argument(
        "--min-score",
        type=float,
        default=float(os.getenv("RAG_GATE_MIN_SCORE", "0.25")),
        help="Minimum retrieval score required to pass the CI gate. Defaults to RAG_GATE_MIN_SCORE or 0.25.",
    )
    parser.add_argument(
        "--output",
        default=os.getenv("RAG_METRICS_PATH", "dist/rag-metrics.json"),
        help="Path for the JSON metrics artifact.",
    )
    args = parser.parse_args()

    metrics = evaluate_scorecard()
    metrics["gate_min_score"] = args.min_score
    metrics["gate_passed"] = metrics["overall_score"] >= args.min_score
    write_metrics(metrics, args.output)

    if not metrics["gate_passed"]:
        print(f"RAG gate failed: score {metrics['overall_score']:.2%} is below minimum {args.min_score:.2%}")
        raise SystemExit(1)
    print(f"RAG gate passed: score {metrics['overall_score']:.2%} is at or above minimum {args.min_score:.2%}")


if __name__ == "__main__":
    main()
