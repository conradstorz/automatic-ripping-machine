"""Regression tests: /history and /database must not 500 when the DB file is
missing. Both routes previously passed jobs={} -> render_template(jobs=jobs.items,
pages=jobs), which raised in the template (dict.items method + pages.page on a
bare dict). The routes now pass a template-safe missing-DB state
(jobs=[], pages=None, db_missing=True); these tests render the templates with
that exact state and assert they render without raising and show the notice.

Runs in-container like the other arm.ui tests (imports build the Flask app).
"""
import sys
import unittest

sys.path.insert(0, '/opt/arm')
from arm.ui import app   # noqa: E402

NOTICE = "No database found"


def _render(template_name, **context):
    """Render a template under a request context (so url_for works)."""
    with app.test_request_context("/"):
        return app.jinja_env.get_template(template_name).render(**context)


class TestMissingDbRender(unittest.TestCase):

    def test_history_renders_empty_state_without_pagination(self):
        html = _render(
            "history.html",
            jobs=[], pages=None, db_missing=True,
            date_format="%Y-%m-%d %H:%M:%S",
            status="all", date_from="", date_to="", page_args={},
        )
        self.assertIn(NOTICE, html)
        # pagination must be skipped when there is no Pagination object
        self.assertNotIn("Showing page", html)

    def test_database_renders_empty_state_without_pagination(self):
        html = _render(
            "databaseview.html",
            jobs=[], pages=None, db_missing=True,
            date_format="%Y-%m-%d %H:%M:%S",
        )
        self.assertIn(NOTICE, html)
        self.assertNotIn("Showing page", html)


if __name__ == '__main__':
    unittest.main()
