"""Integration tests: the Flask API with a temporary SQLite database loaded with the demo data."""
import datetime as dt
import logging
import os
import shutil
import tempfile
import unittest

from app import create_app
from app.db import init_schema
from app.notifications import NotificationGateway
from database.seed import seed

logging.getLogger("notifications").setLevel(logging.WARNING)  # keep the test log readable

PW = "Demo@1234"


class ApiTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        url = "sqlite:///" + os.path.join(self.tmp, "test.db")
        init_schema(url)
        seed(url)
        self.app = create_app({"TESTING": True, "ENABLE_JOBS": False, "DATABASE_URL": url})
        self.client = self.app.test_client()
        NotificationGateway.sent.clear()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def login(self, email, password=PW):
        return self.client.post("/api/auth/login", json={"email": email, "password": password})

    def auth(self, email):
        token = self.login(email).get_json()["token"]
        return {"Authorization": f"Bearer {token}"}

    def future(self, days=5):
        return (dt.datetime.now() + dt.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M")


class AccountTests(ApiTestCase):
    def test_tc16_register_and_login(self):
        """TC-16 a new student can register and then log in"""
        r = self.client.post("/api/auth/register", json={"full_name": "Test Student", "email": "new@test.ae",
                                                          "password": "Secret123"})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.get_json()["user"]["role"], "student")
        self.assertEqual(self.login("new@test.ae", "Secret123").status_code, 200)

    def test_tc17_register_validation(self):
        """TC-17 weak password, bad email and duplicate email are rejected"""
        r = self.client.post("/api/auth/register", json={"full_name": "", "email": "bad", "password": "short"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(set(r.get_json()["fields"]), {"full_name", "email", "password"})
        r = self.client.post("/api/auth/register", json={"full_name": "X", "email": "aisha@demo.adu.ac.ae",
                                                          "password": "Secret123"})
        self.assertIn("already exists", r.get_json()["fields"]["email"])

    def test_tc18_lockout_after_five_failures(self):
        """TC-18 five wrong passwords lock the account for 15 minutes"""
        for left in (4, 3, 2, 1):
            r = self.login("aisha@demo.adu.ac.ae", "wrong-pass1")
            self.assertEqual((r.status_code, r.get_json()["attempts_left"]), (401, left))
        self.assertEqual(self.login("aisha@demo.adu.ac.ae", "wrong-pass1").status_code, 423)
        r = self.login("aisha@demo.adu.ac.ae")  # even the right password is refused while locked
        self.assertEqual(r.status_code, 423)
        self.assertIn("minute", r.get_json()["error"])

    def test_tc19_password_reset_single_use(self):
        """TC-19 the reset link works once and then stops working"""
        self.client.post("/api/auth/forgot-password", json={"email": "omar@demo.adu.ac.ae"})
        token = NotificationGateway.sent[-1][1].split("reset=")[1]
        r = self.client.post("/api/auth/reset-password", json={"token": token, "password": "NewPass123"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.login("omar@demo.adu.ac.ae", "NewPass123").status_code, 200)
        r = self.client.post("/api/auth/reset-password", json={"token": token, "password": "Another123"})
        self.assertEqual(r.status_code, 400)

    def test_tc20_protected_routes_need_login(self):
        """TC-20 API calls without a valid token are refused"""
        self.assertEqual(self.client.get("/api/courses").status_code, 401)
        self.assertEqual(self.client.get("/api/courses", headers={"Authorization": "Bearer junk"}).status_code, 401)


class PlanningTests(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.h = self.auth("aisha@demo.adu.ac.ae")
        self.course = self.client.get("/api/courses", headers=self.h).get_json()[0]["course_id"]

    def test_tc21_task_validation(self):
        """TC-21 invalid task fields are rejected with a message for each field"""
        r = self.client.post(f"/api/courses/{self.course}/tasks", headers=self.h, json={
            "title": "Final report", "task_type": "project", "deadline": "", "grade_weight": 120,
            "difficulty": 3, "estimated_hours": 0})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(set(r.get_json()["fields"]), {"deadline", "grade_weight", "estimated_hours"})
        r = self.client.post(f"/api/courses/{self.course}/tasks", headers=self.h, json={
            "title": "Old", "task_type": "quiz", "deadline": "2020-01-01T10:00", "grade_weight": 5,
            "difficulty": 2, "estimated_hours": 1})
        self.assertIn("past", r.get_json()["fields"]["deadline"])

    def test_tc22_new_task_updates_plan(self):
        """TC-22 adding a valid task saves it and places study sessions for it"""
        r = self.client.post(f"/api/courses/{self.course}/tasks", headers=self.h, json={
            "title": "Extra lab", "task_type": "assignment", "deadline": self.future(8), "grade_weight": 5,
            "difficulty": 2, "estimated_hours": 2})
        self.assertEqual(r.status_code, 201)
        tid = r.get_json()["task"]["task_id"] if "task" in r.get_json() else r.get_json()["task_id"]
        ranked = self.client.get("/api/tasks/ranked", headers=self.h).get_json()
        self.assertIn(tid, [t["task_id"] for t in ranked])
        self.assertTrue(all(ranked[i]["score"] >= ranked[i + 1]["score"] for i in range(len(ranked) - 1)))
        ics = self.client.get("/api/plans/export.ics?week=" + self.future(8)[:10], headers=self.h).get_data(as_text=True)
        self.assertIn("Extra lab", ics)

    def test_tc23_generate_plan(self):
        """TC-23 generating the plan creates study and review sessions"""
        r = self.client.post("/api/plans/generate", headers=self.h)
        body = r.get_json()
        self.assertEqual(r.status_code, 200)
        self.assertGreater(body["sessions_created"], 0)
        self.assertEqual(body["review_sessions"], 3)
        self.assertEqual(body["at_risk"], [])

    def test_tc24_mark_missed_reschedules(self):
        """TC-24 marking a session as missed moves or splits it before the deadline"""
        # The demo plan is full up to the 4-hour daily limit, so allow more study time first.
        r = self.client.put("/api/availability", headers=self.h, json={"settings": {"daily_study_limit": 8}})
        self.assertEqual(r.status_code, 200)
        week = self.client.get("/api/plans", headers=self.h).get_json()
        planned = [s for s in week["sessions"] if s["status"] == "planned" and s["session_type"] == "study"]
        s = planned[0]
        r = self.client.patch(f"/api/sessions/{s['session_id']}/status", headers=self.h, json={"status": "missed"})
        self.assertEqual(r.status_code, 200)
        body = r.get_json()
        self.assertIn(body["action"], ("moved", "split"))
        new_start = body["new_start"] if body["action"] == "moved" else body["parts"][0][0]
        self.assertGreaterEqual(new_start, s["planned_end"])  # never put back into the missed slot

    def test_tc25_locked_session_not_moved(self):
        """TC-25 a locked session is only recorded as missed and keeps its time"""
        s = [x for x in self.client.get("/api/plans", headers=self.h).get_json()["sessions"] if x["status"] == "planned"][0]
        self.client.patch(f"/api/sessions/{s['session_id']}/lock", headers=self.h, json={"locked": True})
        r = self.client.patch(f"/api/sessions/{s['session_id']}/status", headers=self.h, json={"status": "missed"})
        self.assertEqual(r.get_json()["action"], "recorded")

    def test_tc26_ics_export(self):
        """TC-26 the weekly plan downloads as a calendar file"""
        r = self.client.get("/api/plans/export.ics", headers=self.h)
        self.assertEqual(r.status_code, 200)
        text = r.get_data(as_text=True)
        self.assertTrue(text.startswith("BEGIN:VCALENDAR"))
        self.assertIn("BEGIN:VEVENT", text)


class AccessTests(ApiTestCase):
    def advisor_students(self, h):
        return {s["full_name"]: s for s in self.client.get("/api/advisor/students", headers=h).get_json()}

    def test_tc27_advisor_sees_only_consenting_students(self):
        """TC-27 the advisor sees Aisha's summary but is refused Omar's (sharing turned off)"""
        h = self.auth("h.ali@demo.adu.ac.ae")
        students = self.advisor_students(h)
        aisha, omar = students["Aisha Khalid"]["user_id"], students["Omar Saeed"]["user_id"]
        r = self.client.get(f"/api/advisor/students/{aisha}/summary", headers=h)
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("tasks", r.get_json())  # summary only, no task details
        self.assertEqual(self.client.get(f"/api/advisor/students/{omar}/summary", headers=h).status_code, 403)

    def test_tc28_revoking_sharing_removes_access(self):
        """TC-28 when the student turns sharing off, the advisor loses access at once"""
        hs = self.auth("aisha@demo.adu.ac.ae")
        consent = [c for c in self.client.get("/api/sharing", headers=hs).get_json()["history"] if c["is_active"]][0]
        self.assertEqual(self.client.delete(f"/api/sharing/{consent['consent_id']}", headers=hs).status_code, 200)
        ha = self.auth("h.ali@demo.adu.ac.ae")
        aisha = self.advisor_students(ha)["Aisha Khalid"]["user_id"]
        self.assertEqual(self.client.get(f"/api/advisor/students/{aisha}/summary", headers=ha).status_code, 403)

    def test_tc29_role_checks(self):
        """TC-29 students cannot open admin or advisor pages; advisors cannot edit student data"""
        hs, ha = self.auth("aisha@demo.adu.ac.ae"), self.auth("h.ali@demo.adu.ac.ae")
        self.assertEqual(self.client.get("/api/admin/users", headers=hs).status_code, 403)
        self.assertEqual(self.client.get("/api/advisor/students", headers=hs).status_code, 403)
        self.assertEqual(self.client.post("/api/courses", headers=ha, json={"course_code": "X1", "course_name": "X"}).status_code, 403)

    def test_tc30_admin_deactivates_account(self):
        """TC-30 the admin can deactivate an account, which then cannot log in"""
        h = self.auth("admin@demo.adu.ac.ae")
        users = self.client.get("/api/admin/users?q=omar", headers=h).get_json()
        omar = users[0]["user_id"] if isinstance(users, list) else users["users"][0]["user_id"]
        r = self.client.patch(f"/api/admin/users/{omar}", headers=h, json={"status": "deactivated"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.login("omar@demo.adu.ac.ae").status_code, 403)

    def test_tc31_passwords_are_hashed(self):
        """TC-31 passwords are never stored in plain text"""
        from app.db import Database
        db = Database(self.app.config["DATABASE_URL"])
        row = db.query("SELECT password_hash FROM users WHERE email = 'aisha@demo.adu.ac.ae'", one=True)
        db.close()
        self.assertNotIn(PW, row["password_hash"])
        self.assertTrue(row["password_hash"].startswith(("$argon2id$", "scrypt:")))


    def test_tc32_export_and_delete_account(self):
        """TC-32 a student can download their data as CSV and delete the account with all its data"""
        h = self.auth("omar@demo.adu.ac.ae")
        r = self.client.get("/api/me/export", headers=h)
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/csv", r.content_type)
        self.assertEqual(self.client.delete("/api/me", headers=h).status_code, 200)
        self.assertEqual(self.login("omar@demo.adu.ac.ae").status_code, 401)


if __name__ == "__main__":
    unittest.main()
