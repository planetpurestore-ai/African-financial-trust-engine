import sqlite3
from pathlib import Path

# Always keep the SQLite database beside the repository's app package,
# regardless of the directory from which Uvicorn is started.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATABASE_PATH = PROJECT_ROOT / "trust_engine.db"


def get_connection():
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database():
    connection = get_connection()

    connection.execute("""
        CREATE TABLE IF NOT EXISTS invoices (
            invoice_number TEXT PRIMARY KEY,
            supplier_name TEXT NOT NULL,
            buyer_name TEXT NOT NULL,
            amount TEXT NOT NULL,
            currency TEXT NOT NULL,
            issue_date TEXT NOT NULL,
            due_date TEXT NOT NULL
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS evidence (
            evidence_id TEXT PRIMARY KEY,
            evidence_type TEXT NOT NULL,
            reference_number TEXT NOT NULL,
            supplier_name TEXT,
            buyer_name TEXT,
            amount TEXT,
            currency TEXT,
            evidence_date TEXT,
            description TEXT
        )
    """)

    connection.commit()
    connection.close()
