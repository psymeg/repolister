import configparser
import sys
import time

import psycopg2
import torch
from sentence_transformers import SentenceTransformer

config = configparser.ConfigParser()
config.read('database_config.ini')

DB_CONFIG = {
    "host":     config['database']['db_host'],
    "port":     int(config['database']['db_port']),
    "user":     config['database']['db_username'],
    "password": config['database']['db_password'],
    "dbname":   config['database']['db_name'],
}

EMBEDDING_MODEL = "intfloat/multilingual-e5-large"
BATCH_SIZE      = 64
DEVICE          = "cuda" if torch.cuda.is_available() else "cpu"


def get_unembedded_chunks(conn, repo_url: str) -> list[tuple]:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT rc.id, rc.content
            FROM repo_chunks rc
            JOIN repo_files  rf ON rf.id = rc.file_id
            LEFT JOIN repo_embeddings re ON re.chunk_id = rc.id
            WHERE rf.repo_url = %s
              AND re.id IS NULL
            ORDER BY rc.id;
        """, (repo_url,))
        return cur.fetchall()


def embed_batch(model, texts: list[str]) -> list[list[float]]:
    prefixed = [f"passage: {t}" for t in texts]
    return model.encode(
        prefixed,
        batch_size=BATCH_SIZE,
        normalize_embeddings=True,
        show_progress_bar=False,
        convert_to_numpy=True,
    ).tolist()


def insert_embeddings(conn, chunk_ids: list[int], embeddings: list[list[float]]) -> None:
    with conn.cursor() as cur:
        cur.executemany(
            """
            INSERT INTO repo_embeddings (chunk_id, embedding, model)
            VALUES (%s, %s, %s)
            ON CONFLICT DO NOTHING
            """,
            [(cid, emb, EMBEDDING_MODEL)
             for cid, emb in zip(chunk_ids, embeddings)],
        )


def main():
    if len(sys.argv) < 2:
        print("Usage: python repo-embedder.py <github_url>")
        sys.exit(1)

    repo_url = sys.argv[1].rstrip('/')

    print(f"Loading {EMBEDDING_MODEL} on {DEVICE}...")
    model = SentenceTransformer(EMBEDDING_MODEL, device=DEVICE)
    print("  ✓ Ready\n")

    conn        = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False

    try:
        chunks      = get_unembedded_chunks(conn, repo_url)
        total       = len(chunks)
        batch_total = (total + BATCH_SIZE - 1) // BATCH_SIZE
        print(f"Embedding {total} chunks from {repo_url}\n")

        t_start = time.time()
        for batch_num, batch_start in enumerate(range(0, total, BATCH_SIZE), 1):
            batch      = chunks[batch_start:batch_start + BATCH_SIZE]
            chunk_ids  = [r[0] for r in batch]
            texts      = [r[1] for r in batch]

            t0         = time.time()
            embeddings = embed_batch(model, texts)
            insert_embeddings(conn, chunk_ids, embeddings)
            conn.commit()

            elapsed   = time.time() - t0
            remaining = (total - batch_start - len(batch))
            eta       = (elapsed / len(batch)) * remaining
            print(f"  Batch {batch_num}/{batch_total} — "
                  f"{len(batch)} chunks in {elapsed:.1f}s — ETA {eta:.0f}s")

        print(f"\nDone — {total} chunks in {time.time() - t_start:.0f}s")

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
