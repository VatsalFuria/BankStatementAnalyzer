import os
import sqlite3

DB_PATH = "statements.db"
INPUT_FOLDER = "InputStatements"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.executescript("""
    CREATE TABLE IF NOT EXISTS transactions (
        txn_id       INTEGER PRIMARY KEY AUTOINCREMENT,
        import_id    TEXT NOT NULL,
        bank         TEXT NOT NULL,
        account      TEXT NOT NULL,
        txn_date     TEXT NOT NULL,
        description  TEXT NOT NULL,
        amount       REAL NOT NULL,
        dr_cr        TEXT NOT NULL,
        balance      REAL,
        reference    TEXT,
        payment_mode TEXT,
        category     TEXT,
        category_src TEXT,
        rule_id      INTEGER,
        match_id     TEXT,
        source_file  TEXT,
        source_row   INTEGER,
        FOREIGN KEY (rule_id) REFERENCES rules(id),
        FOREIGN KEY (match_id) REFERENCES matches(match_id)
    );

    CREATE TABLE IF NOT EXISTS import_log (
        import_id   TEXT PRIMARY KEY,
        filename    TEXT NOT NULL,
        bank        TEXT NOT NULL,
        account     TEXT NOT NULL,
        imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        row_count   INTEGER
    );

    CREATE TABLE IF NOT EXISTS rules (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        priority     INTEGER NOT NULL,
        match_field  TEXT NOT NULL,
        match_op     TEXT NOT NULL,
        match_value  TEXT NOT NULL,
        category     TEXT NOT NULL,
        source       TEXT NOT NULL DEFAULT 'manual',
        created_at   TEXT DEFAULT CURRENT_TIMESTAMP
    );

    CREATE TABLE IF NOT EXISTS manual_overrides (
        txn_id    INTEGER PRIMARY KEY,
        category  TEXT NOT NULL,
        reason    TEXT,
        FOREIGN KEY (txn_id) REFERENCES transactions(txn_id)
    );

    CREATE TABLE IF NOT EXISTS matches (
        match_id   TEXT PRIMARY KEY,
        debit_txn  INTEGER NOT NULL,
        credit_txn INTEGER NOT NULL,
        confidence INTEGER NOT NULL,
        status     TEXT DEFAULT 'suggested',
        FOREIGN KEY (debit_txn) REFERENCES transactions(txn_id),
        FOREIGN KEY (credit_txn) REFERENCES transactions(txn_id)
    );

    CREATE INDEX IF NOT EXISTS idx_txn_date ON transactions(txn_date);
    CREATE INDEX IF NOT EXISTS idx_txn_account ON transactions(bank, account);
    CREATE INDEX IF NOT EXISTS idx_txn_category ON transactions(category);
    """)
    conn.commit()
    conn.close()


def reset_database(remove_files=False):
    """Remove all imported transactions and import history, and optionally clear the input files folder."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("DELETE FROM manual_overrides")
    cursor.execute("DELETE FROM matches")
    cursor.execute("DELETE FROM transactions")
    cursor.execute("DELETE FROM import_log")
    cursor.execute("DELETE FROM rules")
    cursor.execute("DELETE FROM sqlite_sequence WHERE name IN ('transactions', 'rules')")

    conn.commit()
    conn.close()

    if remove_files:
        if os.path.isdir(INPUT_FOLDER):
            for file_name in os.listdir(INPUT_FOLDER):
                file_path = os.path.join(INPUT_FOLDER, file_name)
                if os.path.isfile(file_path):
                    os.remove(file_path)