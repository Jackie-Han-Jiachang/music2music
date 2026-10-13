from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'flask+ninja2'))
from playlist import PlaylistError, fetch_qq_playlist


def response(songs, total, more=False):
    return {'code': 0, 'playlist': {'code': 0, 'data': {
        'dirinfo': {'title': 'My &amp; your music'}, 'total_song_num': total,
        'hasmore': more, 'songlist': songs}}}


def song(i):
    return {'id': i, 'title': f'Song {i}', 'singer': [{'name': 'A'}, {'name': 'B'}]}


class QQTests(unittest.TestCase):
    @patch('playlist.request_json')
    def test_all_pages_names_and_artists(self, request):
        request.side_effect = [response([song(i) for i in range(100)], 102, True),
                               response([song(100), song(101)], 102)]
        result = fetch_qq_playlist('123')
        self.assertEqual(len(result['songs']), 102)
        self.assertEqual(result['name'], 'My & your music')
        self.assertEqual(result['songs'][-1], {'title': 'Song 101', 'author': 'A, B'})
        self.assertEqual(result['warning'], '')
        self.assertEqual(request.call_args.args[1]['playlist']['param']['song_begin'], 100)
        self.assertTrue(request.call_args.kwargs['json_body'])
        self.assertEqual(request.call_args.kwargs['referer'], 'https://y.qq.com/')

    @patch('playlist.request_json')
    def test_private_playlist(self, request):
        request.return_value = {'code': 0, 'playlist': {'code': 1000}}
        with self.assertRaisesRegex(PlaylistError, 'public'):
            fetch_qq_playlist('123')

    @patch('playlist.request_json')
    def test_repeated_page_is_rejected(self, request):
        request.return_value = response([song(1)], 5, True)
        with self.assertRaisesRegex(PlaylistError, 'repeated a page'):
            fetch_qq_playlist('123')

    @patch('playlist.request_json')
    def test_partial_playlist_is_reported(self, request):
        request.side_effect = [response([song(1)], 5), response([], 5)]
        self.assertIn('1 of 5', fetch_qq_playlist('123')['warning'])

    @patch('playlist.request_json')
    def test_empty_playlist(self, request):
        request.return_value = response([], 0)
        result = fetch_qq_playlist('123')
        self.assertEqual(result['songs'], [])
        self.assertEqual(result['warning'], '')
