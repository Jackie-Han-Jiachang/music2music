from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'flask+ninja2'))
from n2s import app


class AppTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_local_page_and_assets(self):
        page = self.client.get('/n2s')
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'QQ Music', page.data)
        for asset in ['/n2s.js', '/n2s.css']:
            response = self.client.get(asset)
            self.assertEqual(response.status_code, 200)
            response.close()

    @patch('n2s.fetch_qq_playlist')
    def test_qq_service_dispatch(self, fetch):
        fetch.return_value = {'name': 'QQ', 'songs': [{'title': 'Song', 'author': 'Artist'}], 'warning': ''}
        response = self.client.post('/n2s', json={'playlistId': '123', 'service': 'qq'})
        self.assertEqual(response.status_code, 200)
        fetch.assert_called_once_with('123')
        self.assertEqual(response.json['songs'][0]['author'], 'Artist')

    def test_invalid_service_and_id(self):
        for payload in [{'playlistId': '123', 'service': 'unknown'}, {'playlistId': 'abc', 'service': 'qq'}, []]:
            self.assertEqual(self.client.post('/n2s', json=payload).status_code, 400)
