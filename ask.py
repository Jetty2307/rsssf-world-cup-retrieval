import argparse
import json

from rag import ask_rag
from router import route_question


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("question")
    parser.add_argument("--llm-provider", choices=["ollama", "deepseek"], default="ollama")
    parser.add_argument("--llm-model")
    return parser.parse_args()


def main():
    args = parse_args()
    try:
        route = route_question(args.question)
    except Exception as exc:
        print(f"Router failed: {exc}")
        return

    print("=== route ===")
    print(json.dumps(route, ensure_ascii=False, indent=2))
    print()

    target_table = route.get("target_table")

    if target_table != "blocks":
        print("Execution for this route is not implemented yet.")
        return

    result = ask_rag(
        query=args.question,
        year=route.get("year"),
        team=route.get("team"),
        competition=route.get("competition"),
        llm_provider=args.llm_provider,
        llm_model=args.llm_model,
    )

    print("=== answer ===")
    print(result["answer"])


if __name__ == "__main__":
    main()
