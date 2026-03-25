create extension if not exists vector;

create table if not exists documents (
    id bigserial primary key,
    source_url text,
    source_path text,
    title text,
    doc_type text,
    raw_html_path text,
    created_at timestamptz not null default now()
);

create table if not exists blocks (
    id bigserial primary key,
    document_id bigint not null references documents(id) on delete cascade,
    block_index integer not null,
    section_title text,
    block_type text,
    year integer,
    competition text,
    team text,
    text_content text not null,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    unique (document_id, block_index)
);

create index if not exists idx_blocks_document_id on blocks(document_id);
create index if not exists idx_blocks_year on blocks(year);
create index if not exists idx_blocks_competition on blocks(competition);
create index if not exists idx_blocks_team on blocks(team);
create index if not exists idx_blocks_metadata on blocks using gin(metadata);

create table if not exists block_embeddings (
    id bigserial primary key,
    block_id bigint not null references blocks(id) on delete cascade,
    model_name text not null,
    embedding vector not null,
    created_at timestamptz not null default now(),
    unique (block_id, model_name)
);

create index if not exists idx_block_embeddings_block_id
    on block_embeddings(block_id);
create index if not exists idx_block_embeddings_model_name
    on block_embeddings(model_name);
create index if not exists idx_block_embeddings_embedding_cosine
    on block_embeddings using hnsw (embedding vector_cosine_ops);

create table if not exists competition_results (
    id bigserial primary key,
    block_id bigint not null references blocks(id) on delete cascade,
    competition text not null,
    season_label text,
    year integer,
    winner text,
    runner_up text,
    host text,
    final_score text,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create index if not exists idx_competition_results_competition
    on competition_results(competition);
create index if not exists idx_competition_results_year
    on competition_results(year);
create index if not exists idx_competition_results_winner
    on competition_results(winner);

create table if not exists squads (
    id bigserial primary key,
    block_id bigint not null references blocks(id) on delete cascade,
    competition text,
    year integer,
    team text,
    person_name text not null,
    birthdate date,
    height_cm integer,
    weight_kg integer,
    role text,
    shirt_number integer,
    club text,
    is_reserve boolean,
    minutes integer,
    goals integer,
    --stats jsonb not null default '{}'::jsonb,
    -- raw_line text,
    created_at timestamptz not null default now()
);

create index if not exists idx_squads_year on squads(year);
create index if not exists idx_squads_team on squads(team);
create index if not exists idx_squads_person_name on squads(person_name);
create index if not exists idx_squads_shirt_number on squads(shirt_number);
