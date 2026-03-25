import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_ollama import OllamaEmbeddings, OllamaLLM
from langchain_openai import ChatOpenAI

from ingest import get_connection


def load_env():
    env_path = Path(__file__).with_name(".env")
    load_dotenv(env_path if env_path.exists() else None)


def fetch_blocks(year=None, team=None, competition=None):
    clauses = []
    params = []

    if year is not None:
        clauses.append("b.year = %s")
        params.append(year)
    if team:
        clauses.append("b.team ILIKE %s")
        params.append(f"%{team}%")
    if competition:
        clauses.append("b.competition ILIKE %s")
        params.append(f"%{competition}%")

    where_sql = ""
    if clauses:
        where_sql = "where " + " and ".join(clauses)

    sql = f"""
        select
            b.id,
            b.block_index,
            b.section_title,
            b.block_type,
            b.year,
            b.competition,
            b.team,
            b.text_content,
            d.title
        from blocks b
        join documents d on d.id = b.document_id
        {where_sql}
        order by b.document_id, b.block_index
    """

    conn = get_connection()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
    finally:
        conn.close()

    return [build_document(row) for row in rows]


def build_document(row):
    block_id, block_index, section_title, block_type, row_year, row_competition, row_team, text_content, title = row
    return Document(
        page_content=text_content,
        metadata={
            "block_id": block_id,
            "block_index": block_index,
            "section_title": section_title,
            "block_type": block_type,
            "year": row_year,
            "competition": row_competition,
            "team": row_team,
            "title": title,
        },
    )


def get_embedding_client(model_name):
    load_env()
    return OllamaEmbeddings(model=model_name)


def serialize_vector(vector):
    return "[" + ",".join(f"{value:.12g}" for value in vector) + "]"


def fetch_existing_embedding_block_ids(cur, block_ids, embedding_model):
    cur.execute(
        """
        select block_id
        from block_embeddings
        where model_name = %s and block_id = any(%s)
        """,
        (embedding_model, block_ids),
    )
    return {row[0] for row in cur.fetchall()}


def ensure_block_embeddings(documents, embedding_model="nomic-embed-text"):
    if not documents:
        return 0

    block_ids = [doc.metadata["block_id"] for doc in documents]
    conn = get_connection()
    try:
        with conn, conn.cursor() as cur:
            existing_ids = fetch_existing_embedding_block_ids(cur, block_ids, embedding_model)

            missing_docs = [
                doc for doc in documents if doc.metadata["block_id"] not in existing_ids
            ]
            if not missing_docs:
                return 0

            embedding_client = get_embedding_client(embedding_model)
            vectors = embedding_client.embed_documents(
                [doc.page_content for doc in missing_docs]
            )

            for doc, vector in zip(missing_docs, vectors):
                cur.execute(
                    """
                    insert into block_embeddings (
                        block_id,
                        model_name,
                        embedding
                    )
                    values (%s, %s, %s::vector)
                    on conflict (block_id, model_name) do nothing
                    """,
                    (
                        doc.metadata["block_id"],
                        embedding_model,
                        serialize_vector(vector),
                    ),
                )
    finally:
        conn.close()

    return len(missing_docs)


def retrieve_blocks(query, year=None, team=None, competition=None, k=5, embedding_model="nomic-embed-text"):
    candidate_docs = fetch_blocks(year=year, team=team, competition=competition)
    if not candidate_docs:
        raise RuntimeError("No blocks found in the database for the selected filters.")

    ensure_block_embeddings(candidate_docs, embedding_model=embedding_model)

    clauses = ["be.model_name = %s"]
    params = [embedding_model]

    if year is not None:
        clauses.append("b.year = %s")
        params.append(year)
    if team:
        clauses.append("b.team ILIKE %s")
        params.append(f"%{team}%")
    if competition:
        clauses.append("b.competition ILIKE %s")
        params.append(f"%{competition}%")

    query_embedding = get_embedding_client(embedding_model).embed_query(query)
    vector_literal = serialize_vector(query_embedding)

    sql = f"""
        select
            b.id,
            b.block_index,
            b.section_title,
            b.block_type,
            b.year,
            b.competition,
            b.team,
            b.text_content,
            d.title
        from block_embeddings be
        join blocks b on b.id = be.block_id
        join documents d on d.id = b.document_id
        where {" and ".join(clauses)}
        order by be.embedding <=> %s::vector
        limit %s
    """

    conn = get_connection()
    try:
        with conn, conn.cursor() as cur:
            cur.execute(sql, [*params, vector_literal, k])
            rows = cur.fetchall()
    finally:
        conn.close()

    return [build_document(row) for row in rows]


def build_llm(provider="ollama", model_name=None):
    load_env()

    if provider == "ollama":
        return OllamaLLM(model=model_name or "llama3", temperature=0)

    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY is not set.")

    return ChatOpenAI(
        api_key=api_key,
        model=model_name or "deepseek-chat",
        temperature=0,
        base_url="https://api.deepseek.com",
    )


def build_prompt(query, documents):
    context_parts = []
    for doc in documents:
        meta = doc.metadata
        context_parts.append(
            f"title={meta.get('title')} | section={meta.get('section_title')} | "
            f"year={meta.get('year')} | team={meta.get('team')}\n{doc.page_content}"
        )

    context = "\n\n---\n\n".join(context_parts)

    return f"""Answer the question using only the provided context.
If the answer is not explicitly in the context, reply exactly: I don't know.

Question:
{query}

Context:
{context}
"""


def ask_rag(
    query,
    year=None,
    team=None,
    competition=None,
    k=5,
    embedding_model="nomic-embed-text",
    llm_provider="ollama",
    llm_model=None,
):
    retrieved_docs = retrieve_blocks(
        query=query,
        year=year,
        team=team,
        competition=competition,
        k=k,
        embedding_model=embedding_model,
    )
    llm = build_llm(provider=llm_provider, model_name=llm_model)
    prompt = build_prompt(query, retrieved_docs)
    response = llm.invoke(prompt)
    answer = response.content if hasattr(response, "content") else str(response)
    return {
        "answer": answer,
        "documents": retrieved_docs,
    }
