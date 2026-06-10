import configparser
import os
import shutil
import subprocess
import sys

import psycopg2

config = configparser.ConfigParser()
config.read('database_config.ini')

DB_CONFIG = {
    "host":     config['database']['db_host'],
    "port":     int(config['database']['db_port']),
    "user":     config['database']['db_username'],
    "password": config['database']['db_password'],
    "dbname":   config['database']['db_name'],
}

SUPPORTED_EXTENSIONS = {'.r', '.rmd'}
MAX_FILE_BYTES       = 500_000  # skip minified/generated files


def clone_repo(url: str, target_dir: str) -> str:
    """Clone a GitHub repo to a temp directory, return the path."""
    if os.path.exists(target_dir):
        shutil.rmtree(target_dir)
    print(f"Cloning {url}...")
    subprocess.run(["git", "clone", "--depth=1", url, target_dir], check=True)
    return target_dir


def iter_files(repo_dir: str) -> list[dict]:
    """Walk the repo and collect supported source files."""
    files = []
    for root, dirs, filenames in os.walk(repo_dir):
        # skip hidden dirs (.git etc)
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for filename in filenames:
            ext = os.path.splitext(filename)[1].lower()
            if ext not in SUPPORTED_EXTENSIONS:
                continue
            filepath = os.path.join(root, filename)
            if os.path.getsize(filepath) > MAX_FILE_BYTES:
                print(f"  skipping large file: {filepath}")
                continue
            rel_path = os.path.relpath(filepath, repo_dir)
            files.append({
                "path": rel_path,
                "ext":  ext,
            })
    return files


def upsert_source_file(cur, repo_url: str, path: str, ext: str, content: str) -> int:
    """Insert or update a source file, return its id."""
    cur.execute(
        """
        INSERT INTO repo_files (repo_url, file_path, file_type, content)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (repo_url, file_path)
        DO UPDATE SET
            content   = EXCLUDED.content,
            file_type = EXCLUDED.file_type
        RETURNING id
        """,
        (repo_url, path, ext, content),
    )
    return cur.fetchone()[0]


def main():
    if len(sys.argv) < 2:
        print("Usage: python repo-loader.py <github_url>")
        sys.exit(1)

    repo_url   = sys.argv[1].rstrip('/')
    repo_name  = repo_url.split('/')[-1]
    clone_dir  = f"/tmp/ragtime_repo_{repo_name}"

    clone_repo(repo_url, clone_dir)
    files = iter_files(clone_dir)
    print(f"Found {len(files)} source files\n")

    conn = psycopg2.connect(**DB_CONFIG)
    with conn:
        with conn.cursor() as cur:
            for f in files:
                filepath = os.path.join(clone_dir, f['path'])
                with open(filepath, 'r', encoding='utf-8', errors='replace') as fh:
                    content = fh.read()
                file_id = upsert_source_file(
                    cur, repo_url, f['path'], f['ext'], content
                )
                print(f"  ✓ [{file_id}] {f['path']}")

    conn.close()
    shutil.rmtree(clone_dir)
    print(f"\nDone — {len(files)} files loaded to bronze.")


if __name__ == "__main__":
    main()
