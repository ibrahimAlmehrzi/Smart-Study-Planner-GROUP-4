"""Unit tests for the PriorityEngine (FR-11, FR-12)."""
import datetime as dt
import unittest

from app.planning.priority import days_until, explain_priority, priority_score, rank_tasks

TODAY = dt.datetime(2026, 11, 16, 9, 0)  # a Monday


class PriorityTests(unittest.TestCase):
    def test_tc01_formula(self):
        """TC-01 score = weight x difficulty x 1/(days left + 1)"""
        self.assertEqual(priority_score(30, 4, TODAY + dt.timedelta(days=3), TODAY), 30.0)   # 30*4/4
        self.assertEqual(priority_score(10, 2, TODAY + dt.timedelta(days=9), TODAY), 2.0)    # 10*2/10

    def test_tc02_due_today_and_overdue(self):
        """TC-02 tasks due today or overdue get the highest urgency (days left = 0)"""
        self.assertEqual(days_until(TODAY - dt.timedelta(days=2), TODAY), 0)
        self.assertEqual(priority_score(10, 3, TODAY, TODAY), 30.0)

    def test_tc03_invalid_input(self):
        """TC-03 out-of-range weight or difficulty is rejected"""
        with self.assertRaises(ValueError):
            priority_score(120, 3, TODAY, TODAY)
        with self.assertRaises(ValueError):
            priority_score(20, 6, TODAY, TODAY)

    def test_tc04_ranking_and_ties(self):
        """TC-04 ranking is highest score first; ties go to the earlier deadline"""
        tasks = [
            {"id": "low", "grade_weight": 5, "difficulty": 1, "deadline": TODAY + dt.timedelta(days=5)},
            {"id": "late", "grade_weight": 20, "difficulty": 2, "deadline": TODAY + dt.timedelta(days=3, hours=5)},
            {"id": "early", "grade_weight": 20, "difficulty": 2, "deadline": TODAY + dt.timedelta(days=3)},
            {"id": "high", "grade_weight": 30, "difficulty": 5, "deadline": TODAY + dt.timedelta(days=1)},
        ]
        self.assertEqual([t["id"] for t in rank_tasks(tasks, TODAY)], ["high", "early", "late", "low"])

    def test_tc05_explanation(self):
        """TC-05 each ranked task shows a short reason"""
        task = {"grade_weight": 15, "difficulty": 4, "deadline": TODAY + dt.timedelta(days=3)}
        self.assertEqual(explain_priority(task, TODAY), "due in 3 days · 15% of grade · hard")
        late = {"grade_weight": 5, "difficulty": 2, "deadline": TODAY - dt.timedelta(hours=3)}
        self.assertEqual(explain_priority(late, TODAY), "overdue · 5% of grade")


if __name__ == "__main__":
    unittest.main()
