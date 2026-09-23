"""SQLite storage for EcoCOin balances and processed cleanup submissions."""

import sqlite3
from pathlib import Path


DB_PATH = Path(__file__).with_name("ecocoin.db")
MAX_TASK_AWARD = 15


def _validate_user_id(user_id: int) -> None:
    """Reject invalid user identifiers before touching the database."""
    if not isinstance(user_id, int) or isinstance(user_id, bool) or user_id < 0:
        raise ValueError("user_id must be a non-negative integer")


def _validate_amount(amount: int) -> None:
    """Reject invalid coin amounts before applying them to a balance."""
    if (
        not isinstance(amount, int)
        or isinstance(amount, bool)
        or amount < 0
        or amount > MAX_TASK_AWARD
    ):
        raise ValueError(f"amount must be an integer between 0 and {MAX_TASK_AWARD}")


def init_db() -> None:
    """Create the balance and task ledger tables if they do not exist."""
    connection = sqlite3.connect(DB_PATH)
    try:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS user_balances (
                user_id INTEGER PRIMARY KEY,
                balance INTEGER NOT NULL DEFAULT 0 CHECK (balance >= 0)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS eco_tasks (
                task_id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('approved', 'rejected')),
                reason TEXT NOT NULL,
                coins_awarded INTEGER NOT NULL CHECK (coins_awarded >= 0),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_eco_tasks_user_id ON eco_tasks(user_id)"
        )
        connection.commit()
    finally:
        connection.close()


def get_balance(user_id: int) -> int:
    """Return a user's coin balance, or zero if the user has no row yet."""
    _validate_user_id(user_id)
    connection = sqlite3.connect(DB_PATH)
    try:
        row = connection.execute(
            "SELECT balance FROM user_balances WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        return row[0] if row is not None else 0
    finally:
        connection.close()


def add_coins(user_id: int, amount: int) -> None:
    """Add coins to a user's balance, creating their row when needed."""
    _validate_user_id(user_id)
    _validate_amount(amount)
    connection = sqlite3.connect(DB_PATH)
    try:
        connection.execute(
            """
            INSERT INTO user_balances (user_id, balance)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET balance = balance + excluded.balance
            """,
            (user_id, amount),
        )
        connection.commit()
    finally:
        connection.close()


def record_eco_task(
    user_id: int,
    task_id: str,
    status: str,
    reason: str,
    coins_awarded: int,
) -> dict:
    """Record a decision and update a balance once in the same transaction."""
    _validate_user_id(user_id)
    if not isinstance(task_id, str) or not task_id.strip():
        raise ValueError("task_id must be a non-empty string")
    if not isinstance(status, str) or status not in {"approved", "rejected"}:
        raise ValueError(f"Unsupported task status: {status!r}")
    if not isinstance(reason, str):
        raise ValueError("reason must be a string")

    if status == "approved":
        _validate_amount(coins_awarded)
    else:
        # A rejected report never awards coins, regardless of model output.
        coins_awarded = 0

    connection = sqlite3.connect(DB_PATH, isolation_level=None)
    try:
        connection.execute("BEGIN IMMEDIATE")

        previous = connection.execute(
            "SELECT task_id FROM eco_tasks WHERE task_id = ?",
            (task_id,),
        ).fetchone()
        if previous is not None:
            balance_row = connection.execute(
                "SELECT balance FROM user_balances WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            balance = balance_row[0] if balance_row is not None else 0
            connection.execute("COMMIT")
            return {
                "success": False,
                "already_processed": True,
                "current_balance": balance,
                "message": "Этот отчёт уже обработан; повторное начисление не выполнено.",
            }

        connection.execute(
            "INSERT OR IGNORE INTO user_balances (user_id, balance) VALUES (?, 0)",
            (user_id,),
        )
        connection.execute(
            """
            INSERT INTO eco_tasks (task_id, user_id, status, reason, coins_awarded)
            VALUES (?, ?, ?, ?, ?)
            """,
            (task_id, user_id, status, reason, coins_awarded),
        )

        if status == "approved":
            connection.execute(
                "UPDATE user_balances SET balance = balance + ? WHERE user_id = ?",
                (coins_awarded, user_id),
            )

        balance_row = connection.execute(
            "SELECT balance FROM user_balances WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        balance = balance_row[0]
        connection.execute("COMMIT")

        if status == "approved":
            return {
                "success": True,
                "already_processed": False,
                "new_balance": balance,
                "message": reason,
            }
        return {
            "success": False,
            "already_processed": False,
            "current_balance": balance,
            "message": reason,
        }
    except Exception:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise
    finally:
        connection.close()
