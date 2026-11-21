"""Unit tests for the ScheduleGenerator and RescheduleController (FR-13 to FR-20)."""
import datetime as dt
import unittest

from app.planning.reschedule import is_unmarked, reschedule_missed
from app.planning.scheduler import MIN_SESSION, build_free_slots, generate_plan

NOW = dt.datetime(2026, 11, 16, 8, 0)  # Monday morning
EVENINGS = [{"day_of_week": d, "start_time": "16:00", "end_time": "20:00"} for d in range(7)]


def task(tid, days, hours, ttype="assignment", weight=10, difficulty=3, hour=23):
    return {"task_id": tid, "task_type": ttype, "deadline": (NOW + dt.timedelta(days=days)).replace(hour=hour, minute=0),
            "grade_weight": weight, "difficulty": difficulty, "remaining_minutes": int(hours * 60)}


def overlaps(sessions):
    s = sorted(sessions, key=lambda x: x["start"])
    return any(a["end"] > b["start"] for a, b in zip(s, s[1:]))


class SchedulerTests(unittest.TestCase):
    def test_tc06_free_slots_respect_busy_events(self):
        """TC-06 free time = availability minus busy events"""
        busy = [(dt.datetime(2026, 11, 16, 17, 0), dt.datetime(2026, 11, 16, 18, 0))]
        slots = build_free_slots(NOW, NOW + dt.timedelta(hours=14), EVENINGS, busy)
        self.assertEqual(slots, [(dt.datetime(2026, 11, 16, 16, 0), dt.datetime(2026, 11, 16, 17, 0)),
                                 (dt.datetime(2026, 11, 16, 18, 0), dt.datetime(2026, 11, 16, 20, 0))])

    def test_tc07_all_work_placed_inside_free_time(self):
        """TC-07 every session is inside free time, before its deadline, with no overlaps and within the daily limit"""
        tasks = [task(1, 3, 4), task(2, 5, 3, weight=20), task(3, 6, 2)]
        sessions, at_risk = generate_plan(NOW, tasks, EVENINGS, daily_limit_hours=3)
        self.assertEqual(at_risk, {})
        for t in tasks:
            placed = sum((s["end"] - s["start"]).seconds // 60 for s in sessions if s["task_id"] == t["task_id"])
            # the last piece is rounded up to the 25-minute minimum, so up to 24 extra minutes are allowed
            self.assertGreaterEqual(placed, t["remaining_minutes"])
            self.assertLess(placed, t["remaining_minutes"] + MIN_SESSION)
        self.assertFalse(overlaps(sessions))
        per_day = {}
        for s in sessions:
            self.assertTrue(16 <= s["start"].hour and s["end"].hour * 60 + s["end"].minute <= 20 * 60)
            deadline = next(t["deadline"] for t in tasks if t["task_id"] == s["task_id"])
            self.assertLessEqual(s["end"], deadline)
            self.assertGreaterEqual((s["end"] - s["start"]).seconds // 60, MIN_SESSION)
            per_day[s["start"].date()] = per_day.get(s["start"].date(), 0) + (s["end"] - s["start"]).seconds // 60
        self.assertTrue(all(m <= 180 for m in per_day.values()))

    def test_tc08_review_sessions_before_exam(self):
        """TC-08 review sessions 7, 3 and 1 day before an exam"""
        exam = task(9, 10, 4, ttype="exam", weight=30, difficulty=4, hour=10)
        sessions, _ = generate_plan(NOW, [exam], EVENINGS)
        reviews = sorted(s["review_offset_days"] for s in sessions if s["session_type"] == "review")
        self.assertEqual(reviews, [1, 3, 7])
        for s in sessions:
            if s["session_type"] == "review":
                self.assertEqual((exam["deadline"].date() - s["start"].date()).days, s["review_offset_days"])

    def test_tc09_overload_flags_at_risk(self):
        """TC-09 work that cannot fit before the deadline is reported as at risk"""
        sessions, at_risk = generate_plan(NOW, [task(1, 1, 12)], EVENINGS, daily_limit_hours=4)
        self.assertIn(1, at_risk)
        self.assertGreater(at_risk[1], 0)
        self.assertTrue(sessions)  # whatever fits is still planned

    def test_tc10_urgent_task_not_starved(self):
        """TC-10 a high-priority later task does not push out an urgent early task"""
        tasks = [task(1, 1, 2, weight=5, difficulty=1), task(2, 6, 6, weight=40, difficulty=5)]
        _, at_risk = generate_plan(NOW, tasks, EVENINGS, daily_limit_hours=4)
        self.assertEqual(at_risk, {})

    def test_tc11_kept_sessions_not_overlapped(self):
        """TC-11 locked/completed sessions stay where they are and new ones avoid them"""
        kept = [(dt.datetime(2026, 11, 16, 16, 0), dt.datetime(2026, 11, 16, 20, 0))]
        sessions, _ = generate_plan(NOW, [task(1, 2, 2)], EVENINGS, kept=kept)
        self.assertTrue(all(s["start"].date() != NOW.date() for s in sessions))


class RescheduleTests(unittest.TestCase):
    def setUp(self):
        self.deadline = dt.datetime(2026, 11, 18, 23, 0)

    def test_tc12_moved_to_next_free_slot(self):
        """TC-12 a missed session moves to the next free slot"""
        slots = [(dt.datetime(2026, 11, 17, 16, 0), dt.datetime(2026, 11, 17, 18, 0))]
        r = reschedule_missed(50, slots, self.deadline, {}, 240)
        self.assertEqual(r["action"], "moved")
        self.assertEqual(r["start"], dt.datetime(2026, 11, 17, 16, 0))

    def test_tc13_split_into_two_parts(self):
        """TC-13 if no single slot fits, the session is split into two parts of at least 25 minutes"""
        slots = [(dt.datetime(2026, 11, 17, 16, 0), dt.datetime(2026, 11, 17, 16, 30)),
                 (dt.datetime(2026, 11, 18, 16, 0), dt.datetime(2026, 11, 18, 16, 30))]
        r = reschedule_missed(50, slots, self.deadline, {}, 240)
        self.assertEqual(r["action"], "split")
        self.assertEqual([(e - s).seconds // 60 for s, e in r["parts"]], [25, 25])

    def test_tc14_no_slot_left(self):
        """TC-14 if nothing fits before the deadline, the student is told (no change made)"""
        slots = [(dt.datetime(2026, 11, 17, 16, 0), dt.datetime(2026, 11, 17, 16, 20))]
        self.assertEqual(reschedule_missed(50, slots, self.deadline, {}, 240)["action"], "none")

    def test_tc15_unmarked_timeout(self):
        """TC-15 a session with no status 2 hours after it ends counts as missed"""
        s = {"status": "planned", "planned_end": dt.datetime(2026, 11, 16, 17, 0)}
        self.assertFalse(is_unmarked(s, dt.datetime(2026, 11, 16, 18, 59)))
        self.assertTrue(is_unmarked(s, dt.datetime(2026, 11, 16, 19, 0)))
        self.assertFalse(is_unmarked({**s, "status": "completed"}, dt.datetime(2026, 11, 17)))


if __name__ == "__main__":
    unittest.main()
