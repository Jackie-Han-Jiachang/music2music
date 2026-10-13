#!/usr/bin/env python3
"""Local playlist export app; the server proxies requests to the playlist API."""
import os
from pathlib import Path
import re

from flask import Flask, jsonify, redirect, render_template, request, send_file

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 4096
from playlist import PlaylistError, fetch_playlist, fetch_qq_playlist


@app.get('/')
def index():
    return redirect('/n2s')


@app.get('/n2s.js')
def javascript():
    return send_file(Path(__file__).resolve().parent.parent / 'n2s.js', mimetype='application/javascript')


@app.get('/n2s.css')
def stylesheet():
    return send_file(Path(__file__).resolve().parent.parent / 'n2s.css', mimetype='text/css')


@app.get('/n2s')
def n2s_show():
    return render_template('n2s.html')


@app.post('/n2s')
def n2s():
    data = request.get_json(silent=True) if request.is_json else request.form
    if not hasattr(data, 'get'):
        return jsonify(error='Enter a numeric playlist ID.'), 400
    playlist_id = str(data.get('playlistId', '')).strip()
    if not re.fullmatch(r'[0-9]+', playlist_id):
        return jsonify(error='Enter a numeric playlist ID.'), 400
    service = data.get('service', 'netease')
    if service not in ('netease', 'qq'):
        return jsonify(error='Select NetEase Cloud Music or QQ Music.'), 400
    try:
        fetcher = fetch_qq_playlist if service == 'qq' else fetch_playlist
        return jsonify(fetcher(playlist_id))
    except PlaylistError as error:
        app.logger.warning('Playlist retrieval failed: %s', error, exc_info=True)
        return jsonify(error=str(error)), 502


if __name__ == '__main__':
    app.run(host='127.0.0.1', port=int(os.environ.get('PORT', '8888')))
