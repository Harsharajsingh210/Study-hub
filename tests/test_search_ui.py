import unittest

from app import app


class SmartSearchUiTests(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()
        with self.client.session_transaction() as session:
            session["user"] = "Student User"
            session["user_id"] = "demo-user"
            session["is_admin"] = False

    def test_notes_page_has_smart_search_ui(self):
        response = self.client.get("/notes")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("Smart Search", html)
        self.assertIn("smartSearchInput", html)
        self.assertIn("No notes found", html)

    def test_search_is_case_insensitive_for_subjects(self):
        response = self.client.get("/notes?search=chasm")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("CHASM", html)


if __name__ == "__main__":
    unittest.main()
