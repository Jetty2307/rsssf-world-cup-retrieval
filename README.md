# RSSSF Retrieval

RAG and SQL-oriented retrieval project for RSSSF World Cup pages.

Status: in development.

Source data:
[RSSSF World Cup index](https://www.rsssf.org/tablesw/worldcup.html)

## What It Does

- downloads RSSSF World Cup HTML pages locally
- ingests HTML into Postgres tables
- stores text blocks in `blocks`
- stores squad rows in `squads`
- stores final results in `competition_results`
- stores block embeddings in `block_embeddings` using `pgvector`
- routes user questions into retrieval-oriented intents
- answers descriptive questions with RAG over filtered blocks
- answers factual questions with SQL over `squads` and `competition_results`

## Main Files

- [`downloader.py`](/Users/victor/Desktop/DS/rsssf_retrieval/downloader.py): crawl and save RSSSF HTML pages
- [`ingest.py`](/Users/victor/Desktop/DS/rsssf_retrieval/ingest.py): parse one local HTML file into Postgres
- [`schema.sql`](/Users/victor/Desktop/DS/rsssf_retrieval/schema.sql): database schema, including `pgvector`
- [`embed.py`](/Users/victor/Desktop/DS/rsssf_retrieval/embed.py): backfill embeddings for blocks
- [`router.py`](/Users/victor/Desktop/DS/rsssf_retrieval/router.py): classify questions into intents
- [`rag.py`](/Users/victor/Desktop/DS/rsssf_retrieval/rag.py): retrieval and answer generation
- [`sql_executor.py`](/Users/victor/Desktop/DS/rsssf_retrieval/sql_executor.py): execute SQL-backed question types
- [`ask.py`](/Users/victor/Desktop/DS/rsssf_retrieval/ask.py): CLI entry point
- [`run_evals.py`](/Users/victor/Desktop/DS/rsssf_retrieval/run_evals.py): minimal eval runner for router, SQL, and RAG smoke checks

## Current Architecture

1. Download HTML pages into `rsssf_worldcup/`
2. Ingest pages into Postgres `documents`, `blocks`, `squads`, and `competition_results`
3. Generate embeddings for each block and store them in `block_embeddings`
4. Route incoming questions
5. For descriptive questions, filter candidate blocks by metadata and rank them by vector similarity
6. For factual questions, execute SQL against normalized tables
7. Use small gold-set evals to catch routing, extraction, and execution regressions

## Database Setup

This project expects PostgreSQL with `pgvector` enabled.

Apply the schema:

```bash
psql "$DATABASE_URL" -f schema.sql
```

If you use `PGDATABASE` / `PGUSER` / `PGHOST` / `PGPORT` instead:

```bash
psql -f schema.sql
```

The project reads connection settings from `.env` through `dotenv`.

## Typical Workflow

Ingest one page:

```bash
python3 ingest.py rsssf_worldcup/tables/54f.html
```

Ingest World Cup finals overview to populate `competition_results`:

```bash
python3 ingest.py rsssf_worldcup/tablesw/worldcup.html --source-url https://www.rsssf.org/tablesw/worldcup.html
```

Ingest champions' squads page to populate `squads`:

```bash
python3 ingest.py rsssf_worldcup/miscellaneous/wcwinners.html --source-url https://www.rsssf.org/miscellaneous/wcwinners.html
```

Backfill embeddings:

```bash
python3 embed.py --embedding-model nomic-embed-text
```

Ask a question:

```bash
python3 ask.py "Describe the 1954 West Germany World Cup page section."
```

Run evals:

```bash
python3 run_evals.py
```

## Current Limitations

- `competition_results` currently comes from the World Cup overview page, not from every detailed tournament page
- SQL coverage is still partial; compositional questions are not fully handled yet
- descriptive RAG still depends on router quality and retrieved context quality
- router expects JSON output from the model and still depends on prompt compliance
