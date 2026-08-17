import unittest

from app import app


class TimetableTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.client.get('/login', follow_redirects=True)

    def test_timetable_page_renders_for_logged_in_user(self):
        with self.client.session_transaction() as sess:
            sess['user'] = 'Student User'
            sess['user_id'] = 'abc123'
            sess['is_admin'] = False

        response = self.client.get('/timetable')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('College Timetable', html)
        self.assertIn('Class 5A', html)
        self.assertIn('Class 5B', html)
        self.assertIn('Department: Computer Engineering', html)

    def test_class_switching_is_available(self):
        with self.client.session_transaction() as sess:
            sess['user'] = 'Student User'
            sess['user_id'] = 'abc123'
            sess['is_admin'] = False

        response = self.client.get('/timetable?class_name=5B')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('5B', html)
        self.assertIn('Department: Computer Engineering', html)


if __name__ == '__main__':
    unittest.main()
