import sqlite3
from pathlib import Path
import json

DB_PATH = Path("sixel_db/database.sqlite3")
DB_PATH.parent.mkdir(exist_ok=True)

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hash TEXT UNIQUE,
            filename TEXT,
            original_filename TEXT,
            received_at TEXT DEFAULT CURRENT_TIMESTAMP,
            processed_at TEXT DEFAULT CURRENT_TIMESTAMP,
            client_code TEXT,
            tipo TEXT,
            periodo TEXT,
            target_path TEXT,
            solved INTEGER DEFAULT 0,
            meta_json TEXT
        )
    """)
    return conn


def file_already_processed(hash_value: str) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM documents WHERE hash = ?", (hash_value,))
    return cur.fetchone() is not None


def register_file(hash_value: str, filename: str, client_code: str, tipo: str, periodo: str, target_path: str, meta: dict):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT OR IGNORE INTO documents (
            hash,
            filename,
            original_filename,
            client_code,
            tipo,
            periodo,
            target_path,
            meta_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        hash_value,
        filename,
        filename,
        client_code,
        tipo,
        periodo,
        target_path,
        json.dumps(meta, ensure_ascii=False)
    ))

    conn.commit()
