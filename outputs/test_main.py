import os
import tempfile
import unittest
from pathlib import Path

import db
from main import process_eco_task


class EcoCoinTaskTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix="ecocoin-tests-")
        db.DB_PATH = Path(self.temp_dir.name) / "ecocoin.db"
        db.init_db()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_approved_task_adds_coins(self):
        result = process_eco_task(
            42,
            {"status": "approved", "reason": "ok", "coins_awarded": 15},
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["new_balance"], 15)
        self.assertEqual(result["message"], "ok")

    def test_rejected_task_returns_current_balance(self):
        db.add_coins(42, 10)

        result = process_eco_task(
            42,
            {"status": "rejected", "reason": "not enough cleanup"},
        )

        self.assertFalse(result["success"])
        self.assertEqual(result["current_balance"], 10)
        self.assertEqual(result["message"], "not enough cleanup")

    def test_negative_award_is_rejected(self):
        with self.assertRaises(ValueError):
            process_eco_task(
                42,
                {"status": "approved", "reason": "bad", "coins_awarded": -5},
            )

    def test_unknown_status_is_rejected(self):
        with self.assertRaises(ValueError):
            process_eco_task(42, {"status": "pending", "reason": "later"})


if __name__ == "__main__":
    unittest.main()
