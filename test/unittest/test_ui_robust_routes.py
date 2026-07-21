"""Crash-guard regressions for previously-broken routes and git_check_version.

- /activerips used Job.query.filter_by(~Job.finished) (filter_by takes kwargs)
  and always 500'd.
- /error was `def was_error(error)` with no path arg, so GET /error 500'd.
- git_check_version left local_version unbound if the VERSION file was missing,
  raising UnboundLocalError on every /settings load.

Runs in-container (imports arm.ui).
"""
import os
import sys
import tempfile
import unittest
from contextlib import contextmanager

sys.path.insert(0, '/opt/arm')
from arm.ui import app   # noqa: E402
import arm.ui.routes   # noqa: E402,F401  (registers the root routes incl. /error)
import arm.ui.utils as ui_utils   # noqa: E402
import arm.config.config as cfg   # noqa: E402


@contextmanager
def login_disabled():
    orig = app.config.get('LOGIN_DISABLED')
    app.config['LOGIN_DISABLED'] = True
    try:
        yield
    finally:
        if orig is None:
            app.config.pop('LOGIN_DISABLED', None)
        else:
            app.config['LOGIN_DISABLED'] = orig


class TestRobustRoutes(unittest.TestCase):

    def test_activerips_does_not_500(self):
        with login_disabled():
            resp = app.test_client().get('/activerips')
        self.assertNotEqual(resp.status_code, 500)

    def test_error_page_does_not_500(self):
        # /error has no @login_required; used to 500 on the missing positional arg.
        resp = app.test_client().get('/error')
        self.assertEqual(resp.status_code, 200)

    def test_error_page_accepts_query_message(self):
        resp = app.test_client().get('/error?error=boom')
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b'boom', resp.data)


class TestGitCheckVersion(unittest.TestCase):

    def test_missing_version_file_returns_unknown_not_unbound(self):
        with tempfile.TemporaryDirectory() as d:   # no VERSION file inside
            orig = cfg.arm_config.get('INSTALLPATH')
            cfg.arm_config['INSTALLPATH'] = d
            try:
                with app.app_context():
                    local, remote = ui_utils.git_check_version()
            finally:
                cfg.arm_config['INSTALLPATH'] = orig
        self.assertEqual(local, "unknown")
        self.assertFalse(os.path.isfile(os.path.join(d, 'VERSION')))


if __name__ == '__main__':
    unittest.main()
