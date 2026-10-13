"""Fetch public playlist metadata without the original third-party provider."""
import json
import html
import os
import socket
import ssl
import urllib.error
import urllib.parse
import urllib.request


class PlaylistError(Exception):
    pass


BATCH_SIZE = 200


def request_json(endpoint, params, post=False, json_body=False, referer=None):
    parts = urllib.parse.urlsplit(endpoint)
    if parts.scheme not in ('http', 'https') or not parts.netloc:
        raise PlaylistError('API endpoints must be HTTP or HTTPS URLs.')
    headers = {'Referer': 'https://music.163.com/', 'User-Agent': 'Mozilla/5.0',
               'Accept': 'application/json'}
    if referer:
        headers['Referer'] = referer
    encoded = urllib.parse.urlencode(params)
    if post:
        headers['Content-Type'] = 'application/json' if json_body else 'application/x-www-form-urlencoded'
        body = json.dumps(params) if json_body else encoded
        req = urllib.request.Request(endpoint, data=body.encode('utf-8'), headers=headers)
    else:
        query = [(key, value) for key, value in urllib.parse.parse_qsl(parts.query)
                 if key not in params]
        query.extend(params.items())
        url = urllib.parse.urlunsplit(parts._replace(query=urllib.parse.urlencode(query)))
        req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            result = json.load(response)
    except urllib.error.HTTPError as error:
        raise PlaylistError(f'Playlist provider returned HTTP {error.code}. It may be blocking requests or require login.') from error
    except urllib.error.URLError as error:
        if isinstance(error.reason, socket.gaierror):
            message = f'Cannot resolve {parts.hostname}. Check DNS, internet access, and proxy settings on the computer running Flask.'
        elif isinstance(error.reason, ssl.SSLError):
            message = 'TLS certificate verification failed. Check your Python certificates and HTTPS proxy configuration.'
        elif isinstance(error.reason, (TimeoutError, socket.timeout)):
            message = 'The playlist provider timed out. Check your connection and try again.'
        else:
            message = f'Cannot connect to {parts.hostname}. Check the server connection and proxy settings.'
        raise PlaylistError(message) from error
    except TimeoutError as error:
        raise PlaylistError('The playlist provider timed out. Please try again.') from error
    except OSError as error:
        raise PlaylistError('The connection to the playlist provider failed.') from error
    except (ValueError, UnicodeError) as error:
        raise PlaylistError('The playlist provider returned invalid JSON.') from error
    return result


def playlist_body(result):
    if not isinstance(result, dict):
        raise PlaylistError('The playlist provider returned an unexpected response.')
    if result.get('code') != 200:
        raise PlaylistError(f"NetEase could not retrieve this playlist (code {result.get('code', 'unknown')}). Check the ID and whether the playlist is public.")
    playlist = result.get('playlist') or result.get('result')
    if not isinstance(playlist, dict) or not isinstance(playlist.get('tracks'), list):
        raise PlaylistError('The playlist provider did not return song metadata.')
    return playlist


def fetch_playlist(playlist_id):
    endpoint = os.environ.get('PLAYLIST_API_URL', 'https://music.163.com/api/v6/playlist/detail')
    result = request_json(endpoint, {'id': playlist_id, 'n': '100000', 's': '0'})
    playlist = playlist_body(result)
    track_ids = playlist.get('trackIds')
    if not isinstance(track_ids, list):
        # Older/custom providers can return complete metadata without trackIds.
        return normalize_playlist(result)
    ids = []
    for entry in track_ids:
        song_id = entry.get('id') if isinstance(entry, dict) else entry
        if isinstance(song_id, bool) or not str(song_id).isdigit():
            raise PlaylistError('The provider returned an invalid song ID.')
        ids.append(str(song_id))
    metadata = {str(track['id']): track for track in playlist['tracks']
                if isinstance(track, dict) and track.get('id') is not None}
    missing = list(dict.fromkeys(song_id for song_id in ids if song_id not in metadata))
    parts = urllib.parse.urlsplit(endpoint)
    if parts.hostname == 'music.163.com':
        song_endpoint = 'https://music.163.com/api/v3/song/detail'
        direct = True
    else:
        # A compatible local API exposes /playlist/detail and /song/detail.
        path = parts.path.rsplit('/playlist/detail', 1)[0] + '/song/detail'
        song_endpoint = urllib.parse.urlunsplit(parts._replace(path=path, query='', fragment=''))
        direct = False
    song_endpoint = os.environ.get('SONG_API_URL', song_endpoint)
    for start in range(0, len(missing), BATCH_SIZE):
        batch = missing[start:start + BATCH_SIZE]
        if direct:
            params = {'c': json.dumps([{'id': int(song_id), 'v': 0} for song_id in batch]),
                      'ids': json.dumps([int(song_id) for song_id in batch])}
        else:
            params = {'ids': ','.join(batch)}
        details = request_json(song_endpoint, params, post=direct)
        if not isinstance(details, dict) or details.get('code') != 200 or not isinstance(details.get('songs'), list):
            raise PlaylistError('The song-detail provider could not retrieve the remaining songs. Please try again.')
        for track in details['songs']:
            if not isinstance(track, dict) or track.get('id') is None:
                raise PlaylistError('The song-detail provider returned invalid song metadata.')
            metadata[str(track['id'])] = track
    # Song-detail responses can be reordered. Rebuild using the playlist's IDs.
    ordered = [metadata[song_id] for song_id in ids if song_id in metadata]
    playlist = dict(playlist, tracks=ordered)
    total = playlist.get('trackCount', len(ids))
    playlist['trackCount'] = max(total if isinstance(total, int) else 0, len(ids))
    return normalize_playlist({'code': 200, 'playlist': playlist})


def normalize_playlist(result):
    playlist = playlist_body(result)
    songs = []
    for track in playlist['tracks']:
        if not isinstance(track, dict):
            raise PlaylistError('The playlist provider returned invalid song metadata.')
        artists = track.get('ar', track.get('artists', []))
        if not isinstance(artists, list) or any(not isinstance(artist, dict) for artist in artists):
            raise PlaylistError('The playlist provider returned invalid artist metadata.')
        songs.append({'title': str(track.get('name') or ''),
                      'author': ', '.join(str(artist.get('name') or '') for artist in artists)})
    total = playlist.get('trackCount', len(songs))
    partial = isinstance(total, int) and total > len(songs)
    return {'name': str(playlist.get('name') or ''), 'songs': songs,
            'warning': f'Only {len(songs)} of {total} songs could be retrieved. Some song IDs or details are unavailable from the provider; login may be required.' if partial else ''}


QQ_PAGE_SIZE = 100


def fetch_qq_playlist(playlist_id):
    """Read every page from QQ Music's playlist metadata service."""
    endpoint = os.environ.get('QQ_PLAYLIST_API_URL', 'https://u.y.qq.com/cgi-bin/musicu.fcg')
    songs, seen_pages = [], set()
    name, offset, total = '', 0, None
    while True:
        payload = {
            'comm': {'ct': 24, 'cv': 4747474, 'uin': '0', 'format': 'json'},
            'playlist': {'module': 'music.srfDissInfo.DissInfo', 'method': 'CgiGetDiss',
                         'param': {'disstid': int(playlist_id), 'dirid': 0, 'tag': True,
                                   'song_begin': offset, 'song_num': QQ_PAGE_SIZE,
                                   'userinfo': True, 'orderlist': True, 'onlysonglist': False}},
        }
        response = request_json(endpoint, payload, post=True, json_body=True, referer='https://y.qq.com/')
        block = response.get('playlist') if isinstance(response, dict) else None
        if not isinstance(block, dict) or block.get('code') != 0 or response.get('code', 0) != 0:
            raise PlaylistError('QQ Music could not retrieve this playlist. Check its ID and whether it is public.')
        data = block.get('data')
        if not isinstance(data, dict) or not isinstance(data.get('songlist'), list):
            raise PlaylistError('QQ Music returned an unexpected playlist response.')
        detail = data.get('dirinfo') or {}
        if not isinstance(detail, dict):
            raise PlaylistError('QQ Music returned invalid playlist details.')
        name = name or html.unescape(str(detail.get('title') or detail.get('name') or 'QQ Music playlist'))
        count = data.get('total_song_num', detail.get('songnum', detail.get('total_song_num')))
        if count is not None:
            try:
                total = int(count)
            except (ValueError, TypeError):
                raise PlaylistError('QQ Music returned an invalid song count.')
        tracks = data['songlist']
        # Detect a provider ignoring the offset rather than repeating a page forever.
        signature = json.dumps(tracks, sort_keys=True, ensure_ascii=False)
        if tracks and signature in seen_pages:
            raise PlaylistError('QQ Music repeated a page; the complete playlist could not be retrieved.')
        seen_pages.add(signature)
        for track in tracks:
            if not isinstance(track, dict):
                raise PlaylistError('QQ Music returned invalid song metadata.')
            singers = track.get('singer') or []
            if not isinstance(singers, list) or any(not isinstance(singer, dict) for singer in singers):
                raise PlaylistError('QQ Music returned invalid artist metadata.')
            title = track.get('title') or track.get('name') or track.get('songname')
            if not title:
                raise PlaylistError('QQ Music returned a song without a name.')
            songs.append({'title': html.unescape(str(title)),
                          'author': ', '.join(html.unescape(str(singer.get('name') or '')) for singer in singers)})
        offset += len(tracks)
        marker = data.get('hasmore', data.get('hasMore'))
        if not tracks:
            break
        if total is not None:
            if offset >= total:
                break
        elif marker is not None:
            if marker in (False, 0, '0'):
                break
        elif len(tracks) < QQ_PAGE_SIZE:
            break
    warning = ''
    if total is not None and len(songs) < total:
        warning = f'Only {len(songs)} of {total} songs could be retrieved from QQ Music. Some songs may be private or unavailable.'
    return {'name': name, 'songs': songs, 'warning': warning}
