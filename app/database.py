import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATABASE_PATH = PROJECT_ROOT / "trust_engine.db"


def get_connection():
    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database():
    connection = get_connection()
    try:
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
        connection.execute("""
            CREATE TABLE IF NOT EXISTS verification_audits (
                audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                invoice_number TEXT NOT NULL,
                evidence_ids TEXT NOT NULL,
                decision TEXT NOT NULL,
                verification_score REAL NOT NULL,
                passed_checks INTEGER NOT NULL,
                total_checks INTEGER NOT NULL,
                failed_checks TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        connection.commit()
    finally:
        connection.close()


def record_verification_audit(invoice_number, evidence_ids, decision, verification_score, passed_checks, total_checks, failed_checks):
    connection = get_connection()
    try:
        cursor = connection.execute(
            """INSERT INTO verification_audits
            (invoice_number, evidence_ids, decision, verification_score,
             passed_checks, total_checks, failed_checks)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (invoice_number, evidence_ids, decision, verification_score, passed_checks, total_checks, failed_checks),
        )
        connection.commit()
        return cursor.lastrowid
    finally:
        connection.close()


def list_verification_audits(invoice_number, limit=50):
    connection = get_connection()
    try:
        rows = connection.execute(
            """SELECT audit_id, invoice_number, evidence_ids, decision,
                      verification_score, passed_checks, total_checks,
                      failed_checks, created_at
               FROM verification_audits
               WHERE invoice_number = ?
               ORDER BY audit_id DESC
               LIMIT ?""",
            (invoice_number, limit),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()
