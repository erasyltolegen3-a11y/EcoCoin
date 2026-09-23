"""Apply AI audit decisions to EcoCOin user balances."""

from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from uuid import uuid4

# main.py is stored in outputs/, while db.py may live at the project root.
PROJECT_DIR = Path(__file__).resolve().parent.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

import db
from db import get_balance, init_db


def process_eco_task(
    user_id: int,
    ai_response: dict,
    submission_id: str | None = None,
) -> dict:
    """Record the AI decision and award coins once for a unique submission.

    Pass a stable submission_id (for example a hash of both uploaded photos)
    to prevent the same report from being credited more than once.
    """
    if not isinstance(ai_response, dict):
        raise ValueError("ai_response must be a dictionary")

    status = ai_response.get("status")
    if not isinstance(status, str) or status not in {"approved", "rejected"}:
        raise ValueError(f"Unsupported AI response status: {status!r}")

    reason = ai_response.get("reason", "")
    if not isinstance(reason, str):
        raise ValueError("reason must be a string")

    if status == "approved":
        coins_awarded = ai_response.get("coins_awarded")
        if (
            not isinstance(coins_awarded, int)
            or isinstance(coins_awarded, bool)
            or coins_awarded < 0
            or coins_awarded > db.MAX_TASK_AWARD
        ):
            raise ValueError(
                f"coins_awarded must be an integer between 0 and {db.MAX_TASK_AWARD}"
            )
    else:
        coins_awarded = 0

    # Legacy callers without an ID still work, while the UI passes a stable photo hash.
    task_id = submission_id or uuid4().hex
    return db.record_eco_task(
        user_id=user_id,
        task_id=task_id,
        status=status,
        reason=reason,
        coins_awarded=coins_awarded,
    )


if __name__ == "__main__":
    # Keep the console demo isolated from the persistent application database.
    with TemporaryDirectory(prefix="ecocoin-demo-") as temp_dir:
        db.DB_PATH = Path(temp_dir) / "ecocoin.db"
        init_db()
        test_user_id = 1

        approved_response = {
            "status": "approved",
            "reason": "Мусор успешно убран, мешки зафиксированы",
            "coins_awarded": 15,
        }
        print("Успешная задача:", process_eco_task(test_user_id, approved_response))

        rejected_response = {
            "status": "rejected",
            "reason": "На фото после уборки остался мусор",
        }
        print("Отклонённая задача:", process_eco_task(test_user_id, rejected_response))

        print("Финальный баланс:", get_balance(test_user_id))
