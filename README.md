# Repolister

A RAG pipeline for interrogating GitHub repositories. Clone a repo, chunk it at function level, embed it locally, and query it in plain English (or Japanese).

Built on top of the Ragtime document pipeline — shares the same PostgreSQL database, embedding model, and Ollama LLM.

<img width="1043" height="962" alt="Screenshot_20260610_224519" src="https://github.com/user-attachments/assets/270b8a96-2211-4c91-8604-9a1b23fe3ea0" />


## What it does

Repolister loads an R (or Rmd) repository into a bronze/silver/gold pipeline:

- **Bronze** — raw source files, keyed by repo URL + file path
- **Silver** — function-level chunks, with roxygen2 docs attached
- **Gold** — embeddings via `intfloat/multilingual-e5-large`, stored in pgvector

At query time it embeds your question, retrieves the most relevant function chunks, and asks a local LLM to synthesise an answer — citing the source files.

## Requirements

- Python 3.9+
- PostgreSQL with [pgvector](https://github.com/pgvector/pgvector)
- [Ollama](https://ollama.com) with `qwen2.5:7b` pulled
- NVIDIA GPU recommended (tested on RTX 3060 12GB)
- `git` on your PATH

```bash
pip install psycopg2-binary torch sentence-transformers ollama
```

## Setup

**1. Database**

Run the schema SQL as a superuser:

```bash
psql -U postgres -d ragtime_db -f create-repolister.sql
```

**2. Credentials**

Create a `database_config.ini` (keep this out of version control):

```ini
[database]
db_host     = localhost
db_port     = 5432
db_name     = ragtime_db
db_username = ragtime_db_user
db_password = your_password
```

**3. Pull the LLM**

```bash
ollama pull qwen2.5:7b
```

## Usage

Each script takes a GitHub URL as its only argument. Run them in order:

```bash
# 1. Clone and load raw files → bronze
python repo-loader.py https://github.com/owner/repo

# 2. Chunk by function → silver
python repo-chunker.py https://github.com/owner/repo

# 3. Embed chunks → gold
python repo-embedder.py https://github.com/owner/repo

# 4. Query
python repo-query.py https://github.com/owner/repo
```

The pipeline is re-run safe — the loader upserts, the chunker deletes and re-inserts, the embedder skips already-embedded chunks.
