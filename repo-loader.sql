-- Bronze
CREATE TABLE IF NOT EXISTS repo_files (
    id        SERIAL PRIMARY KEY,
    repo_url  TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_type VARCHAR(10),
    content   TEXT,
    CONSTRAINT uq_repo_file UNIQUE (repo_url, file_path)
);

-- Silver
CREATE TABLE IF NOT EXISTS repo_chunks (
    id          SERIAL PRIMARY KEY,
    file_id     INTEGER REFERENCES repo_files (id) ON DELETE CASCADE,
    chunk_index INTEGER,
    chunk_name  TEXT,    -- function name, section_N, or __file__
    content     TEXT,
    CONSTRAINT uq_repo_chunk UNIQUE (file_id, chunk_index)
);

-- Gold
CREATE TABLE IF NOT EXISTS repo_embeddings (
    id        SERIAL PRIMARY KEY,
    chunk_id  INTEGER REFERENCES repo_chunks (id) ON DELETE CASCADE,
    embedding vector(1024),
    model     VARCHAR(64)
);

CREATE INDEX IF NOT EXISTS repo_embeddings_idx
    ON repo_embeddings
    USING hnsw (embedding vector_cosine_ops);

-- Grants
GRANT SELECT, INSERT, UPDATE, DELETE ON repo_files       TO ragtime_db_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON repo_chunks      TO ragtime_db_user;
GRANT SELECT, INSERT, UPDATE, DELETE ON repo_embeddings  TO ragtime_db_user;
GRANT USAGE, SELECT ON SEQUENCE repo_files_id_seq        TO ragtime_db_user;
GRANT USAGE, SELECT ON SEQUENCE repo_chunks_id_seq       TO ragtime_db_user;
GRANT USAGE, SELECT ON SEQUENCE repo_embeddings_id_seq   TO ragtime_db_user;
