# Repolister

This python application implements a RAG pipeline for interrogating GitHub repositories. Clone a repo, chunk it at function level, embed it locally, and query it in plain English (or Japanese, or Chinese - depending on how you set up the prompt).

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
- [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) for GPU passthrough

## Setup

## Docker setup (recommended)
 
Docker Compose runs three containers: PostgreSQL with pgvector, Ollama for LLM inference, and the Python app. All model weights persist in named volumes — nothing is re-downloaded between runs.
 
**1. Clone the repo**
 
```bash
git clone https://github.com/psymeg/repolister.git
cd repolister
```
 
**2. Create a `.env` file** (keep this out of version control):
 
```bash
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your_postgres_password
POSTGRES_DB=ragtime_db
 
DB_HOST=db
DB_PORT=5432
DB_NAME=ragtime_db
DB_USER=ragtime_db_user
DB_PASSWORD=your_app_password
 
OLLAMA_HOST=http://ollama:11434
```
 
**3. Install the NVIDIA Container Toolkit** (first time only):
 
```bash
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
    sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
    sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```
 
**4. Start the database and Ollama:**
 
```bash
docker compose up -d db ollama
```
 
**5. Pull the LLM** (first time only — stored in a named volume):
 
```bash
docker compose exec ollama ollama pull qwen2.5:7b
```
 
## Usage
 
Each script takes a GitHub URL as its only argument. Run them in order:
 
```bash
# 1. Clone and load raw files → bronze
docker compose run --rm app python repo-loader.py https://github.com/owner/repo
 
# 2. Chunk by function → silver
docker compose run --rm app python repo-chunker.py https://github.com/owner/repo
 
# 3. Embed chunks → gold
docker compose run --rm app python repo-embedder.py https://github.com/owner/repo
 
# 4. Query
docker compose run --rm app python repo-query.py https://github.com/owner/repo
```
 
The pipeline is re-run safe — the loader upserts, the chunker deletes and re-inserts, the embedder skips already-embedded chunks. Multiple repos can coexist in the same database, each keyed by URL.
 
### Example session
 
```
Loading intfloat/multilingual-e5-large on cuda...
  ✓ Ready — querying https://github.com/UchidaMizuki/jpstat
 
Q: how do I filter data by prefecture?
 
  Retrieved 6 chunks (closest: 0.1664)
 
A: To filter data by prefecture, use the `activate()` function to select
   the area key, then `filter()` to specify the prefecture name or code.
   For example, to filter for Tokyo and Osaka (R/estat.R):
 
   census |>
     activate(area) |>
     rekey("pref") |>
     filter(name %in% c("東京都", "大阪府")) |>
     select(code, name)
```
 
## Manual setup (without Docker)
 
If you prefer to run without Docker:
 
```bash
pip install psycopg2-binary torch sentence-transformers ollama
```
 
Create `database_config.ini` (keep out of version control):
 
```ini
[database]
db_host     = localhost
db_port     = 5432
db_name     = ragtime_db
db_username = ragtime_db_user
db_password = your_password
```
 
Run the schema as a superuser:
 
```bash
psql -U postgres -d ragtime_db -f sql/02-create-repolister.sql
```
 
Pull the LLM and start Ollama:
 
```bash
ollama pull qwen2.5:7b
ollama serve
```
 
Then run the scripts directly with `python` instead of `docker compose run --rm app`.
 
## Configuration
 
| Variable | Default | Description |
|---|---|---|
| `EMBEDDING_MODEL` | `intfloat/multilingual-e5-large` | Sentence transformer model |
| `LLM_MODEL` | `qwen2.5:7b` | Ollama model for generation |
| `BATCH_SIZE` | `64` | Embedding batch size (raise to 128 on >12GB VRAM) |
| `TOP_K` | `6` | Number of chunks retrieved per query |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama server URL |
 
## Supported file types
 
| Extension | Chunking strategy |
|---|---|
| `.r` | Per function — roxygen2 docs + full body |
| `.rmd` | Per code fence / prose section |
 
Adding support for Python (`.py`) or other languages means adding an extraction function in `repo-chunker.py` and extending `SUPPORTED_EXTENSIONS` in `repo-loader.py`.
 
## Database schema
 
```
repo_files        ← bronze: one row per file per repo
repo_chunks       ← silver: one row per function/section
repo_embeddings   ← gold:   one row per chunk, vector(1024)
```
 
## Troubleshooting
 
**`permission denied for table repo_*`**
Run the grants in `sql/02-create-repolister.sql` as the `postgres` superuser.
 
**LLM responds in Chinese/Japanese**
The system prompt instructs the model to respond in English. If it slips, check `SYSTEM_PROMPT` in `repo-query.py` includes `"Always respond in English"`.
 
**Poor retrieval quality**
Check `distance` in the query output. Values above `~0.4` suggest the question isn't landing near the indexed content — try rephrasing with more specific function or domain terminology.
 
**Re-embedding after re-chunking**
The embedder only processes chunks with no existing embedding. If you re-chunk, delete the old embeddings first:
 
```sql
DELETE FROM repo_embeddings re
USING repo_chunks rc JOIN repo_files rf ON rf.id = rc.file_id
WHERE rc.id = re.chunk_id AND rf.repo_url = 'https://github.com/owner/repo';
```
 
**Resetting the database**
```bash
docker compose down
docker volume rm repolister_pgdata
docker compose up -d db ollama
```

