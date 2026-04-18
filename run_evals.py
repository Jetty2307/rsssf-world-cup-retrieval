import json
import unicodedata
from pathlib import Path

from rag import ask_rag
from router import route_question
from sql_executor import execute_sql_route, select_operation


EVALS_DIR = Path(__file__).with_name("evals")


def load_jsonl(path):
    rows = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def normalize_text(value):
    if value is None:
        return None
    normalized = unicodedata.normalize("NFKD", str(value))
    normalized = normalized.encode("ascii", "ignore").decode("ascii")
    return " ".join(normalized.strip().lower().split())


def run_router_eval():
    dataset = load_jsonl(EVALS_DIR / "router_eval.jsonl")
    exact_matches = 0
    field_checks = 0
    field_matches = 0
    failures = []

    for item in dataset:
        actual = route_question(item["question"])
        expected = item["expected_route"]

        item_ok = True
        for field, expected_value in expected.items():
            field_checks += 1
            actual_value = actual.get(field)
            if actual_value == expected_value:
                field_matches += 1
            else:
                item_ok = False
                failures.append(
                    {
                        "question": item["question"],
                        "field": field,
                        "expected": expected_value,
                        "actual": actual_value,
                    }
                )

        if item_ok:
            exact_matches += 1

    return {
        "name": "router",
        "items": len(dataset),
        "exact_route_match": ratio(exact_matches, len(dataset)),
        "field_accuracy": ratio(field_matches, field_checks),
        "failures": failures[:10],
    }


def run_sql_eval(filename):
    dataset = load_jsonl(EVALS_DIR / filename)
    op_matches = 0
    exact_matches = 0
    normalized_matches = 0
    contains_matches = 0
    failures = []

    for item in dataset:
        question = item["question"]
        route = route_question(question)
        target_table = route.get("target_table")
        if target_table not in {"squads", "competition_results"}:
            failures.append(
                {
                    "question": question,
                    "expected_operation": item["expected_operation"],
                    "failure_type": "unexpected_target_table",
                    "actual_target_table": target_table,
                    "route": route,
                }
            )
            continue

        try:
            actual_operation = select_operation(question, route)
            if actual_operation == item["expected_operation"]:
                op_matches += 1

            result = execute_sql_route(question, route)
            answer = result["answer"]
        except Exception as exc:
            failures.append(
                {
                    "question": question,
                    "expected_operation": item["expected_operation"],
                    "failure_type": "execution_error",
                    "error": str(exc),
                    "route": route,
                }
            )
            continue

        if "expected_answer" in item:
            if answer == item["expected_answer"]:
                exact_matches += 1
            if normalize_text(answer) == normalize_text(item["expected_answer"]):
                normalized_matches += 1
            else:
                failures.append(
                    {
                        "question": question,
                        "expected_operation": item["expected_operation"],
                        "actual_operation": actual_operation,
                        "expected_answer": item["expected_answer"],
                        "actual_answer": answer,
                    }
                )

        if "expected_answer_contains" in item:
            if normalize_text(item["expected_answer_contains"]) in normalize_text(answer):
                contains_matches += 1
            else:
                failures.append(
                    {
                        "question": question,
                        "expected_operation": item["expected_operation"],
                        "actual_operation": actual_operation,
                        "expected_contains": item["expected_answer_contains"],
                        "actual_answer": answer,
                    }
                )

    return {
        "name": filename.replace("_eval.jsonl", ""),
        "items": len(dataset),
        "operation_accuracy": ratio(op_matches, len(dataset)),
        "exact_answer_match": ratio(exact_matches, count_items_with_key(dataset, "expected_answer")),
        "normalized_answer_match": ratio(normalized_matches, count_items_with_key(dataset, "expected_answer")),
        "contains_match": ratio(contains_matches, count_items_with_key(dataset, "expected_answer_contains")),
        "failures": failures[:10],
    }


def run_rag_smoke_eval():
    dataset = [
        {
            "question": "Describe the 1954 West Germany World Cup page section.",
            "year": 1954,
            "team": "West Germany",
            "competition": "World Cup",
        }
    ]

    results = []
    for item in dataset:
        output = ask_rag(
            query=item["question"],
            year=item["year"],
            team=item["team"],
            competition=item["competition"],
        )
        results.append(
            {
                "question": item["question"],
                "answer": output["answer"],
                "documents": len(output["documents"]),
            }
        )

    return {
        "name": "rag_smoke",
        "items": len(dataset),
        "results": results,
    }


def count_items_with_key(dataset, key):
    return sum(1 for item in dataset if key in item)


def ratio(numerator, denominator):
    if denominator == 0:
        return None
    return round(numerator / denominator, 3)


def main():
    reports = [
        run_router_eval(),
        run_sql_eval("competition_results_eval.jsonl"),
        run_sql_eval("squads_eval.jsonl"),
        run_rag_smoke_eval(),
    ]
    print(json.dumps(reports, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
