import io
import json
from pathlib import Path
import socket
import sys
import unittest
from unittest.mock import patch
import urllib.error

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'flask+ninja2'))
from playlist import PlaylistError, fetch_playlist, normalize_playlist


class PlaylistTests(unittest.TestCase):
    def test_modern_and_legacy_metadata(self):
        for key, artists in [('playlist', 'ar'), ('result', 'artists')]:
            result = normalize_playlist({'code': 200, key: {
                'name': 'Example', 'tracks': [{'name': 'Song', artists: [{'name': 'A'}, {'name': 'B'}]}]}})
            self.assertEqual(result['songs'], [{'title': 'Song', 'author': 'A, B'}])
            self.assertEqual(result['warning'], '')

    def test_partial_playlist_is_reported(self):
        result = normalize_playlist({'code': 200, 'playlist': {'tracks': [], 'trackCount': 10}})
        self.assertIn('0 of 10', result['warning'])

    def test_provider_failure_and_invalid_metadata(self):
        for result in [{'code': 404}, {'code': 200, 'playlist': {'tracks': [None]}}, []]:
            with self.assertRaises(PlaylistError):
                normalize_playlist(result)

    @patch('playlist.urllib.request.urlopen')
    def test_direct_request(self, open_url):
        open_url.return_value = io.BytesIO(json.dumps({'code': 200, 'result': {'name': 'Test', 'tracks': []}}).encode())
        with patch.dict('os.environ', {'PLAYLIST_API_URL': 'https://music.163.com/api/playlist/detail?extra=1'}):
            self.assertEqual(fetch_playlist('123')['name'], 'Test')
        request = open_url.call_args.args[0]
        self.assertIn('id=123', request.full_url)
        self.assertIn('extra=1', request.full_url)
        self.assertEqual(request.get_method(), 'GET')
        self.assertEqual(open_url.call_args.kwargs['timeout'], 20)

    @patch('playlist.urllib.request.urlopen')
    def test_dns_error_is_actionable(self, open_url):
        open_url.side_effect = urllib.error.URLError(socket.gaierror(8, 'Unknown host'))
        with self.assertRaisesRegex(PlaylistError, 'Check DNS'):
            fetch_playlist('123')

    @patch('playlist.request_json')
    def test_ten_song_preview_expands_to_all_songs_in_order(self, request_json):
        def song(song_id):
            return {'id': song_id, 'name': f'Song {song_id}', 'ar': [{'name': 'Artist'}]}
        calls = []
        def provider(endpoint, params, post=False):
            if not post:
                return {'code': 200, 'playlist': {'name': 'Large playlist', 'trackCount': 451,
                    'trackIds': [{'id': i} for i in range(451)],
                    'tracks': [song(i) for i in range(10)]}}
            ids = [item['id'] for item in json.loads(params['c'])]
            calls.append(ids)
            return {'code': 200, 'songs': [song(i) for i in reversed(ids)]}
        request_json.side_effect = provider
        with patch.dict('os.environ', {'PLAYLIST_API_URL': 'https://music.163.com/api/v6/playlist/detail'}):
            result = fetch_playlist('123')
        self.assertEqual(len(result['songs']), 451)
        self.assertEqual([song['title'] for song in result['songs']], [f'Song {i}' for i in range(451)])
        self.assertEqual([len(batch) for batch in calls], [200, 200, 41])
        self.assertEqual(result['warning'], '')

    @patch('playlist.request_json')
    def test_local_service_and_missing_song_details(self, request_json):
        request_json.side_effect = [
            {'code': 200, 'playlist': {'tracks': [], 'trackIds': [{'id': 1}, {'id': 2}], 'trackCount': 2}},
            {'code': 200, 'songs': [{'id': 1, 'name': 'Available', 'artists': []}]},
        ]
        with patch.dict('os.environ', {'PLAYLIST_API_URL': 'http://localhost:3000/playlist/detail'}):
            result = fetch_playlist('123')
        self.assertEqual(request_json.call_args.args, ('http://localhost:3000/song/detail', {'ids': '1,2'}))
        self.assertEqual(result['songs'][0]['title'], 'Available')
        self.assertIn('1 of 2', result['warning'])

    @patch('playlist.request_json')
    def test_repeated_track_ids_preserve_playlist_entries(self, request_json):
        request_json.side_effect = [
            {'code': 200, 'playlist': {'tracks': [], 'trackIds': [{'id': 1}, {'id': 1}]}},
            {'code': 200, 'songs': [{'id': 1, 'name': 'Repeated', 'ar': []}]},
        ]
        with patch.dict('os.environ', {'PLAYLIST_API_URL': 'https://music.163.com/api/v6/playlist/detail'}):
            result = fetch_playlist('123')
        self.assertEqual(len(json.loads(request_json.call_args.args[1]['c'])), 1)
        self.assertEqual(len(result['songs']), 2)
        self.assertEqual(result['warning'], '')


if __name__ == '__main__':
    unittest.main()
