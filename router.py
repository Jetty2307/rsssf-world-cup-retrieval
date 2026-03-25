import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI


ROUTER_PROMPT = """You are a query router for an RSSSF football QA system.

Convert the user question into JSON.
Do not answer the question.
Return only valid JSON.

Allowed intent values:
- squad_lookup
- competition_result_lookup
- comparison_or_temporal
- descriptive_rag

Allowed target_table values:
- squads
- competition_results
- blocks

Rules:
- If the question asks about players, shirt numbers, coaches, or squad membership, use intent "squad_lookup" and target_table "squads".
- If the question asks who won, who was runner-up, or asks for a tournament result fact, use intent "competition_result_lookup" and target_table "competition_results".
- If the question asks about last, latest, first, totals, earliest, before, after, between, how many years, most, or least, use intent "comparison_or_temporal".
- If the question needs open-ended explanation or narrative context, use intent "descriptive_rag" and target_table "blocks".
- If the competition is implied but not stated, assume "World Cup".
- If a field is unknown, return null.

Return JSON with exactly these keys:
intent: string, one of squad_lookup | competition_result_lookup | comparison_or_temporal | descriptive_rag
competition: string or null
year: integer or null
team: string or null
person: string or null
shirt_number: integer or null
time_relation: string or null
start_year: integer or null
end_year: integer or null
target_table: string, one of squads | competition_results | blocks
needs_sql: boolean
needs_rag: boolean

Return JSON in this exact shape:
{
  "intent": "descriptive_rag",
  "competition": "World Cup",
  "year": null,
  "team": null,
  "person": null,
  "shirt_number": null,
  "time_relation": null,
  "start_year": null,
  "end_year": null,
  "target_table": "blocks",
  "needs_sql": false,
  "needs_rag": true
}
"""


def load_env():
    env_path = Path(__file__).with_name(".env")
    load_dotenv(env_path if env_path.exists() else None)


def build_router_llm(model_name=None):
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY is not set.")

    return ChatOpenAI(
        api_key=api_key,
        model=model_name or "deepseek-chat",
        temperature=0,
        base_url="https://api.deepseek.com",
    )


def route_question(question, model_name=None):
    load_env()
    llm = build_router_llm(model_name)
    prompt = f"{ROUTER_PROMPT}\nQuestion: {question}"
    response = llm.invoke(prompt)
    content = response.content if hasattr(response, "content") else str(response)
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        fenced_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", content, re.DOTALL)
        if fenced_match:
            try:
                return json.loads(fenced_match.group(1))
            except json.JSONDecodeError:
                pass
        raise RuntimeError(
            "Router model did not return valid JSON. "
            f"Raw response: {content!r}"
        ) from exc
