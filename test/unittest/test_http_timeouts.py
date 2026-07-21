"""Tests for outbound-HTTP timeout + adequate error handling.

Every HTTP call now passes a timeout so a slow/unreachable server can't hang a
rip or a waitress worker, and the too-narrow excepts (which only caught
HTTPError) were widened so the timeout is actually handled.

Runs in-container.
"""
import sys
import unittest
from unittest import mock

sys.path.insert(0, '/opt/arm')
import requests   # noqa: E402
import arm.ripper.utils as utils          # noqa: E402
import arm.ui.metadata as metadata        # noqa: E402


class TestHttpTimeout(unittest.TestCase):

    def test_metadata_http_timeout_is_positive_int(self):
        self.assertIsInstance(metadata._http_timeout(), int)
        self.assertGreater(metadata._http_timeout(), 0)

    def test_scan_emby_swallows_timeout(self):
        cfg_stub = {'EMBY_REFRESH': True, 'EMBY_SERVER': 'h', 'EMBY_PORT': 8096,
                    'EMBY_API_KEY': 'k', 'HTTP_TIMEOUT_SECS': 15}
        with mock.patch.object(utils.cfg, 'arm_config', cfg_stub), \
             mock.patch.object(utils.requests, 'post',
                               side_effect=requests.exceptions.Timeout('slow')) as mpost:
            utils.scan_emby()   # must NOT raise
        # timeout was passed to the request
        _, kwargs = mpost.call_args
        self.assertIn('timeout', kwargs)

    def test_metadata_get_passes_timeout(self):
        # tmdb_get_imdb issues requests.get; assert a timeout is always supplied.
        fake = mock.Mock(text='{"movie_results": [], "tv_results": []}', status_code=200)
        with mock.patch.object(metadata.requests, 'get', return_value=fake) as mget:
            try:
                metadata.tmdb_get_imdb("tt0000000")
            except Exception:
                pass
        self.assertTrue(mget.called)
        for call in mget.call_args_list:
            self.assertIn('timeout', call.kwargs)


if __name__ == '__main__':
    unittest.main()
