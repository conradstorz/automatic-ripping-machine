"""Regression tests: /history and /database must not 500 when the DB file is
missing. Both routes previously passed jobs={} -> render_template(jobs=jobs.items,
pages=jobs), which raised in the template (dict.items method + pages.page on a
bare dict). The routes now pass a template-safe missing-DB state
(jobs=[], pages=None, db_missing=True).

Two layers of coverage:
- Template-level: render each template with the missing-DB context directly.
- Route-level: drive the actual routes with the DB file pointed at a
  nonexistent path and assert a 200 + notice. This guards the whole chain,
  including that arm_db_cfg()/check_db_version() no longer raise when the DB
  is absent (they previously blew up with UnboundLocalError before the route
  branch was ever reached).

Runs in-container like the other arm.ui tests (imports build the Flask app).
"""
import sys
import unittest
from contextlib import contextmanager

sys.path.insert(0, '/opt/arm')
from arm.ui import app   # noqa: E402
import arm.config.config as cfg   # noqa: E402

NOTICE = "No database found"


def _render(template_name, **context):
    """Render a template under a request context (so url_for works)."""
    with app.test_request_context("/"):
        return app.jinja_env.get_template(template_name).render(**context)


@contextmanager
def missing_db_no_login():
    """Point DBFILE at a nonexistent path and disable login for the block.

    The routes branch on os.path.isfile(DBFILE), so a bogus path forces the
    missing-DB branch. LOGIN_DISABLED lets @login_required through so we can
    assert on the rendered response.
    """
    orig_db = cfg.arm_config['DBFILE']
    orig_login = app.config.get('LOGIN_DISABLED')
    cfg.arm_config['DBFILE'] = '/nonexistent/arm/does-not-exist.db'
    app.config['LOGIN_DISABLED'] = True
    try:
        yield
    finally:
        cfg.arm_config['DBFILE'] = orig_db
        if orig_login is None:
            app.config.pop('LOGIN_DISABLED', None)
        else:
            app.config['LOGIN_DISABLED'] = orig_login


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


class TestMissingDbRoutes(unittest.TestCase):
    """Drive the real routes with the DB file absent -> must be 200, not 500."""

    def test_history_route_does_not_500(self):
        with missing_db_no_login():
            resp = app.test_client().get('/history')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(NOTICE, resp.get_data(as_text=True))

    def test_database_route_does_not_500(self):
        with missing_db_no_login():
            resp = app.test_client().get('/database')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(NOTICE, resp.get_data(as_text=True))


if __name__ == '__main__':
    unittest.main()
