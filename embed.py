import argparse
from pathlib import Path

from dotenv import load_dotenv
from rag import ensure_block_embeddings, fetch_blocks


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate and persist embeddings for RSSSF blocks."
    )
    parser.add_argument("--year", type=int)
    parser.add_argument("--team")
    parser.add_argument("--competition")
    parser.add_argument("--embedding-model", default="nomic-embed-text")
    return parser.parse_args()


def main():
    env_path = Path(__file__).with_name(".env")
    load_dotenv(env_path if env_path.exists() else None)

    args = parse_args()
    blocks = fetch_blocks(
        year=args.year,
        team=args.team,
        competition=args.competition,
    )
    inserted = ensure_block_embeddings(
        blocks,
        embedding_model=args.embedding_model,
    )
    print(
        f"Ensured embeddings for {len(blocks)} blocks; "
        f"inserted {inserted} new rows for model {args.embedding_model}."
    )


if __name__ == "__main__":
    main()
