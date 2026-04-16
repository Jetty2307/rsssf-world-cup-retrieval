# Evals

Minimal gold sets for routing and end-to-end QA checks.

## Files

- `router_eval.jsonl`: expected route fields for representative questions
- `competition_results_eval.jsonl`: factual QA examples for `competition_results`
- `squads_eval.jsonl`: factual QA examples for `squads`

## Format

Each line is a JSON object.

Common fields:

- `question`: user question
- `expected_route`: expected normalized route fields
- `expected_operation`: expected SQL operation when relevant
- `expected_answer`: expected answer text for exact or near-exact checks

## Usage

These files are meant to be a stable baseline while routing, ingestion, and SQL execution are still changing.

Recommended first checks:

1. Verify route fields match `expected_route`
2. Verify SQL executor selects `expected_operation`
3. Verify final answer matches or is acceptably close to `expected_answer`

