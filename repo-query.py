import configparser
import io
import sys
import os
import psycopg2
import torch
from ollama import Client as OllamaClient
from sentence_transformers import SentenceTransformer

config = configparser.ConfigParser()
config.read('database_config.ini')

DB_CONFIG = {
    "host":     os.environ["DB_HOST"],
    "port":     int(os.environ["DB_PORT"]),
    "user":     os.environ["DB_USER"],
    "password": os.environ["DB_PASSWORD"],
    "dbname":   os.environ["DB_NAME"],
}

EMBEDDING_MODEL = "intfloat/multilingual-e5-large"
LLM_MODEL       = "qwen2.5:7b"
DEVICE          = "cuda" if torch.cuda.is_available() else "cpu"
TOP_K           = 6

SYSTEM_PROMPT = """You are a code assistant helping a developer understand an R package.
Always respond in English. The repo is probably in Japanese. Answer questions using only the provided source code and documentation excerpts.
When describing functions, include their parameters and what they return.
If the answer isn't in the excerpts, say so clearly — do not guess.
Always cite which file the information came from."""


def embed_query(model, question: str) -> list[float]:
    return model.encode(
        f"query: {question}",
        normalize_embeddings=True,
        convert_to_numpy=True,
    ).tolist()


def retrieve_chunks(conn, repo_url: str, query_embedding: list[float]) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                rf.file_path,
                rc.chunk_name,
                rc.content,
                re.embedding <=> %s::vector AS distance
            FROM repo_embeddings re
            JOIN repo_chunks rc ON rc.id = re.chunk_id
            JOIN repo_files  rf ON rf.id = rc.file_id
            WHERE rf.repo_url = %s
            ORDER BY distance ASC
            LIMIT %s;
        """, (query_embedding, repo_url, TOP_K))
        return [
            {"file": r[0], "name": r[1], "content": r[2], "distance": r[3]}
            for r in cur.fetchall()
        ]


def ask(ollama: OllamaClient, question: str, chunks: list[dict]) -> str:
    context = "\n\n---\n\n".join(
        f"[{c['file']} / {c['name']}]\n{c['content']}"
        for c in chunks
    )
    response = ollama.chat(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": f"Code excerpts:\n\n{context}\n\nQuestion: {question}"},
        ],
    )
    return response["message"]["content"]


def main():
    if len(sys.argv) < 2:
        print("Usage: python repo-query.py <github_url>")
        sys.exit(1)

    sys.stdin  = io.TextIOWrapper(sys.stdin.buffer, encoding='utf-8')
    repo_url   = sys.argv[1].rstrip('/')

    print(f"Loading {EMBEDDING_MODEL} on {DEVICE}...")
    model  = SentenceTransformer(EMBEDDING_MODEL, device=DEVICE)
#    ollama = OllamaClient(host="http://host.docker.internal:11434")
    ollama = OllamaClient(host=os.environ.get("OLLAMA_HOST", "http://localhost:11434"))
    conn   = psycopg2.connect(**DB_CONFIG)

    print(f"  ✓ Ready — querying {repo_url}\n")
    print("Type your question, or 'quit' to exit.\n")

    while True:
        try:
            question = input("Q: ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if not question:
            continue
        if question.lower() in ("quit", "exit", "q"):
            break

        vec    = embed_query(model, question)
        chunks = retrieve_chunks(conn, repo_url, vec)

        print(f"\n  Retrieved {len(chunks)} chunks "
              f"(closest: {chunks[0]['distance']:.4f})\n")

        print(f"A: {ask(ollama, question, chunks)}\n")

    conn.close()


if __name__ == "__main__":
    main()
