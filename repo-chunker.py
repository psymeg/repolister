import configparser
import re
import sys
import os
import psycopg2

config = configparser.ConfigParser()
config.read('database_config.ini')

DB_CONFIG = {
    "host":     os.environ["DB_HOST"],
    "port":     int(os.environ["DB_PORT"]),
    "user":     os.environ["DB_USER"],
    "password": os.environ["DB_PASSWORD"],
    "dbname":   os.environ["DB_NAME"],
}

# Matches optional roxygen block + function definition
R_FUNCTION_PATTERN = re.compile(
    r"((?:#'[^\n]*\n)*)?"           # optional roxygen2 block (#' lines)
    r"(\w+)\s*<-\s*function\s*\(",  # fname <- function(
    re.MULTILINE
)


def find_matching_brace(text: str, start: int) -> int:
    """Return index of the closing brace matching the opening brace at start."""
    depth = 0
    i     = start
    while i < len(text):
        if text[i] == '{':
            depth += 1
        elif text[i] == '}':
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return len(text) - 1  # fallback: rest of file


def extract_r_chunks(content: str, file_path: str) -> list[dict]:
    """
    Extract function-level chunks from an R file.
    Each chunk includes the roxygen block + full function body.
    Falls back to the whole file if no functions found.
    """
    chunks = []

    for match in R_FUNCTION_PATTERN.finditer(content):
        roxygen   = (match.group(1) or "").strip()
        func_name = match.group(2)

        # find opening brace
        brace_pos = content.find('{', match.end())
        if brace_pos == -1:
            continue

        end_pos = find_matching_brace(content, brace_pos)
        body    = content[match.start():end_pos + 1]

        # build a context-rich chunk: roxygen + signature + body
        chunk_text = f"# File: {file_path}\n# Function: {func_name}\n\n{body}"
        if roxygen:
            chunk_text = f"{roxygen}\n\n{chunk_text}"

        chunks.append({
            "name":    func_name,
            "content": chunk_text,
        })

    # fallback — file has no functions (constants, sourced scripts)
    if not chunks:
        chunks.append({
            "name":    "__file__",
            "content": f"# File: {file_path}\n\n{content}",
        })

    return chunks


def extract_rmd_chunks(content: str, file_path: str) -> list[dict]:
    """
    Split Rmd files by code fences and prose sections.
    Each chunk gets a header identifying its file + position.
    """
    parts   = re.split(r'(```(?:r|R|{r[^}]*})?.*?```)', content, flags=re.DOTALL)
    chunks  = []
    section = 0

    for part in parts:
        part = part.strip()
        if not part:
            continue
        chunk_text = f"# File: {file_path}\n# Section: {section}\n\n{part}"
        chunks.append({"name": f"section_{section}", "content": chunk_text})
        section += 1

    return chunks


def get_files(conn, repo_url: str) -> list[tuple]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, file_path, file_type, content FROM repo_files WHERE repo_url = %s ORDER BY id;",
            (repo_url,)
        )
        return cur.fetchall()


def insert_chunks(conn, file_id: int, chunks: list[dict]) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM repo_chunks WHERE file_id = %s", (file_id,))
        cur.executemany(
            """
            INSERT INTO repo_chunks (file_id, chunk_index, chunk_name, content)
            VALUES (%s, %s, %s, %s)
            """,
            [(file_id, idx, c['name'], c['content'])
             for idx, c in enumerate(chunks)],
        )


def main():
    if len(sys.argv) < 2:
        print("Usage: python repo-chunker.py <github_url>")
        sys.exit(1)

    repo_url = sys.argv[1].rstrip('/')
    conn     = psycopg2.connect(**DB_CONFIG)

    with conn:
        files = get_files(conn, repo_url)
        print(f"Chunking {len(files)} files from {repo_url}\n")

        for file_id, file_path, file_type, content in files:
            if file_type == '.rmd':
                chunks = extract_rmd_chunks(content, file_path)
            else:
                chunks = extract_r_chunks(content, file_path)

            insert_chunks(conn, file_id, chunks)
            print(f"  ✓ {file_path} → {len(chunks)} chunks")

    conn.close()
    print("\nDone.")


if __name__ == "__main__":
    main()
