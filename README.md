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
- stores block embeddings in `block_embeddings` using `pgvector`
- routes user questions into retrieval-oriented intents
- answers descriptive questions with RAG over filtered blocks

## Main Files

- [`downloader.py`](/Users/victor/Desktop/DS/rsssf_retrieval/downloader.py): crawl and save RSSSF HTML pages
- [`ingest.py`](/Users/victor/Desktop/DS/rsssf_retrieval/ingest.py): parse one local HTML file into Postgres
- [`schema.sql`](/Users/victor/Desktop/DS/rsssf_retrieval/schema.sql): database schema, including `pgvector`
- [`embed.py`](/Users/victor/Desktop/DS/rsssf_retrieval/embed.py): backfill embeddings for blocks
- [`router.py`](/Users/victor/Desktop/DS/rsssf_retrieval/router.py): classify questions into intents
- [`rag.py`](/Users/victor/Desktop/DS/rsssf_retrieval/rag.py): retrieval and answer generation
- [`ask.py`](/Users/victor/Desktop/DS/rsssf_retrieval/ask.py): CLI entry point

## Current Architecture

1. Download HTML pages into `rsssf_worldcup/`
2. Ingest pages into Postgres `documents`, `blocks`, and `squads`
3. Generate embeddings for each block and store them in `block_embeddings`
4. Route incoming questions
5. For descriptive questions, filter candidate blocks by metadata and rank them by vector similarity
6. Send retrieved context to the LLM for final answering

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

## Typical Workflow

Ingest one page:

```bash
python3 ingest.py rsssf_worldcup/tables/54f.html
```

Backfill embeddings:

```bash
python3 embed.py --embedding-model nomic-embed-text
```

Ask a question:

```bash
python3 ask.py "Describe the 1954 West Germany World Cup page section."
```

## Current Limitations

- `competition_results` exists in schema but is not populated yet
- temporal and comparison questions are routed, but not fully executed via SQL
- descriptive RAG works better than fact/aggregation questions
- router expects JSON output from the model and still depends on prompt compliance
