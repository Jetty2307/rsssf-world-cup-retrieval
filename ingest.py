import argparse
import os
import re
from datetime import date
from pathlib import Path

import psycopg2
from bs4 import BeautifulSoup
from dotenv import load_dotenv


YEAR_HEADING_RE = re.compile(r"^\s*(\d{4})\s+(.+?)\s*$")
BIRTHDATE_RE = re.compile(r"\b(\d{2})\.(\d{2})\.(\d{2})\b")
HEIGHT_WEIGHT_RE = re.compile(r"\b(\d{3})/(\d{2,3})\b")
LEADING_SHIRT_RE = re.compile(r"^\s*\(?(\d+)\)?\s+")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Ingest a local RSSSF HTML file into Postgres documents/blocks tables."
    )
    parser.add_argument("html_path", help="Path to a local HTML file")
    parser.add_argument(
        "--source-url",
        default=None,
        help="Original source URL, if known",
    )
    parser.add_argument(
        "--doc-type",
        default="html_page",
        help="Document type label stored in documents.doc_type",
    )

    return parser.parse_args()


def read_html(html_path: Path) -> str:
    return html_path.read_text(encoding="utf-8", errors="ignore")


def extract_title(soup: BeautifulSoup, html_path: Path) -> str:
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    return html_path.name


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n")
    lines = [line.rstrip() for line in text.splitlines()]
    normalized_lines = []
    blank_streak = 0

    for line in lines:
        if line.strip():
            normalized_lines.append(line)
            blank_streak = 0
            continue

        blank_streak += 1
        if blank_streak <= 2:
            normalized_lines.append("")

    return "\n".join(normalized_lines).strip()


def detect_heading(line: str):
    match = YEAR_HEADING_RE.match(line)
    if not match:
        return None
    return {
        "year": int(match.group(1)),
        "section_title": match.group(0).strip(),
        "team": match.group(2).strip(),
    }


def split_into_blocks(text: str, default_competition=None):
    lines = text.splitlines()
    blocks = []

    current_lines = []
    current_heading = None

    for raw_line in lines:
        line = raw_line.rstrip()
        heading = detect_heading(line)

        if heading:
            if current_lines:
                blocks.append(build_block(len(blocks), current_lines, current_heading, default_competition))
            current_lines = [line]
            current_heading = heading
            continue

        if current_lines or line.strip():
            current_lines.append(line)

    if current_lines:
        blocks.append(build_block(len(blocks), current_lines, current_heading, default_competition))

    return blocks


def build_block(block_index: int, lines, heading, default_competition=None):
    text_content = "\n".join(lines).strip()
    metadata = {}

    if heading:
        metadata["year_heading"] = True
        block_type = "year_section"
        year = heading["year"]
        section_title = heading["section_title"]
        team = heading["team"]
    else:
        block_type = "preamble"
        year = None
        section_title = "preamble"
        team = None

    return {
        "block_index": block_index,
        "section_title": section_title,
        "block_type": block_type,
        "year": year,
        "competition": infer_competition(text_content, default_competition),
        "team": team,
        "text_content": text_content,
        "metadata": metadata,
    }


def infer_competition(text_content: str, default_competition=None):
    lowered = text_content.lower()
    if "world cup" in lowered:
        return "World Cup"
    return default_competition


def get_connection():
    dsn = os.getenv("DATABASE_URL")
    if dsn:
        return psycopg2.connect(dsn)

    required = {
        "dbname": os.getenv("PGDATABASE"),
        "user": os.getenv("PGUSER"),
        "password": os.getenv("PGPASSWORD"),
        "host": os.getenv("PGHOST", "localhost"),
        "port": os.getenv("PGPORT", "5432"),
    }

    missing = [key.upper() for key, value in required.items() if not value and key != "password"]
    if missing:
        raise RuntimeError(
            "Postgres connection is not configured. Set DATABASE_URL or PGDATABASE/PGUSER/PGHOST/PGPORT."
        )

    return psycopg2.connect(**required)


def insert_document(cur, html_path: Path, args, title: str):
    cur.execute(
        """
        insert into documents (
            source_url,
            source_path,
            title,
            doc_type,
            raw_html_path
        )
        values (%s, %s, %s, %s, %s)
        returning id
        """,
        (
            args.source_url,
            str(html_path),
            title,
            args.doc_type,
            str(html_path),
        ),
    )
    return cur.fetchone()[0]


def delete_existing_document(cur, html_path: Path, source_url):
    html_path_str = str(html_path)

    if source_url:
        cur.execute(
            """
            delete from documents
            where source_path = %s or source_url = %s
            """,
            (html_path_str, source_url),
        )
        return

    cur.execute(
        """
        delete from documents
        where source_path = %s
        """,
        (html_path_str,),
    )


def insert_blocks(cur, document_id: int, blocks):
    inserted_blocks = []
    for block in blocks:
        cur.execute(
            """
            insert into blocks (
                document_id,
                block_index,
                section_title,
                block_type,
                year,
                competition,
                team,
                text_content,
                metadata
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            returning id
            """,
            (
                document_id,
                block["block_index"],
                block["section_title"],
                block["block_type"],
                block["year"],
                block["competition"],
                block["team"],
                block["text_content"],
                json_dumps(block["metadata"]),
            ),
        )
        inserted_blocks.append({**block, "id": cur.fetchone()[0]})
    return inserted_blocks


def extract_squad_rows(block):
    if block["block_type"] != "year_section":
        return []

    rows = []
    reserve_mode = False
    lines = block["text_content"].splitlines()[1:]

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        if stripped.startswith("Reserve:"):
            reserve_mode = True
            continue

        if reserve_mode:
            continue

        parsed = parse_squad_line(stripped, block["year"])
        if not parsed:
            continue

        rows.append(
            {
                "block_id": block["id"],
                "competition": block["competition"],
                "year": block["year"],
                "team": block["team"],
                "person_name": parsed["person_name"],
                "birthdate": parsed["birthdate"],
                "height_cm": parsed["height_cm"],
                "weight_kg": parsed["weight_kg"],
                "role": parsed["role"],
                "shirt_number": parsed["shirt_number"],
                "club": parsed["club"],
                "is_reserve": False,
                "minutes": None,
                "goals": None,
            }
        )

    return rows


def parse_squad_line(line: str, reference_year: int):
    if "coach" not in line.lower() and not BIRTHDATE_RE.search(line):
        return None

    shirt_number = None
    leading_match = LEADING_SHIRT_RE.match(line)
    if leading_match:
        shirt_number = int(leading_match.group(1))
        line = line[leading_match.end():]

    birthdate_match = BIRTHDATE_RE.search(line)
    if not birthdate_match:
        return None

    person_name = line[:birthdate_match.start()].strip()
    if not person_name:
        return None

    birthdate = parse_birthdate(birthdate_match, reference_year)
    tail = line[birthdate_match.end():].strip()

    height_cm = None
    weight_kg = None
    hw_match = HEIGHT_WEIGHT_RE.search(tail)
    if hw_match and hw_match.start() == 0:
        height_cm = int(hw_match.group(1))
        weight_kg = int(hw_match.group(2))
        tail = tail[hw_match.end():].strip()

    parts = [part.strip() for part in re.split(r"\s{2,}", tail) if part.strip()]
    role = "coach" if "coach" in line.lower() else "player"
    club = None

    if parts:
        first_part = parts[0].lower()
        if first_part == "coach":
            role = "coach"
        else:
            club = parts[0]

    return {
        "person_name": normalize_person_name(person_name),
        "birthdate": birthdate,
        "height_cm": height_cm,
        "weight_kg": weight_kg,
        "role": role,
        "shirt_number": shirt_number,
        "club": club,
    }


def parse_birthdate(match, reference_year: int):
    day = int(match.group(1))
    month = int(match.group(2))
    year_suffix = int(match.group(3))

    if reference_year is None:
        year = 1900 + year_suffix
    else:
        year = (reference_year // 100) * 100 + year_suffix
        if year > reference_year:
            year -= 100

    return date(year, month, day)


def normalize_person_name(name: str) -> str:
    return " ".join(name.split())


def insert_squads(cur, squad_rows):
    for row in squad_rows:
        cur.execute(
            """
            insert into squads (
                block_id,
                competition,
                year,
                team,
                person_name,
                birthdate,
                height_cm,
                weight_kg,
                role,
                shirt_number,
                club,
                is_reserve,
                minutes,
                goals
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                row["block_id"],
                row["competition"],
                row["year"],
                row["team"],
                row["person_name"],
                row["birthdate"],
                row["height_cm"],
                row["weight_kg"],
                row["role"],
                row["shirt_number"],
                row["club"],
                row["is_reserve"],
                row["minutes"],
                row["goals"],
            ),
        )


def json_dumps(payload):
    import json

    return json.dumps(payload, ensure_ascii=True)


def main():
    load_dotenv()
    args = parse_args()
    html_path = Path(args.html_path).expanduser().resolve()

    if not html_path.exists():
        raise FileNotFoundError(f"HTML file not found: {html_path}")

    html = read_html(html_path)
    soup = BeautifulSoup(html, "html.parser")
    title = extract_title(soup, html_path)
    text = html_to_text(html)
    default_competition = infer_competition(f"{title}\n{text[:1000]}")
    blocks = split_into_blocks(text, default_competition=default_competition)

    if not blocks:
        raise RuntimeError(f"No blocks extracted from {html_path}")

    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                delete_existing_document(cur, html_path, args.source_url)
                document_id = insert_document(cur, html_path, args, title)
                inserted_blocks = insert_blocks(cur, document_id, blocks)
                squad_rows = []
                for block in inserted_blocks:
                    squad_rows.extend(extract_squad_rows(block))
                insert_squads(cur, squad_rows)
    finally:
        conn.close()

    print(
        f"Inserted document_id={document_id} with {len(blocks)} blocks "
        f"and {len(squad_rows)} squad rows from {html_path}"
    )


if __name__ == "__main__":
    main()
