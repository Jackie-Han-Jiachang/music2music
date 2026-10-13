// The local Flask server retrieves metadata from the selected music service.
(() => {
    'use strict';
    function initialize() {
        const form = document.getElementById('playlist-form');
        if (!form) return;
        const input = document.getElementById('playlistId');
        const submit = document.getElementById('submit');
        const output = document.getElementById('output');
        const status = document.getElementById('status');
        const copy = document.getElementById('copy');
        const download = document.getElementById('download');
        const rows = document.getElementById('song-rows');
        const list = document.getElementById('song-list');
        const empty = document.getElementById('empty-state');
        const name = document.getElementById('plname');
        const count = document.getElementById('numsongs');
        const services = Array.from(form.querySelectorAll('[name="service"]'));
        let loading = false;
        let filename = 'playlist';
        function report(message, state = 'ready') {
            status.textContent = message;
            status.dataset.state = state;
        }
        function clear() {
            output.value = '';
            rows.replaceChildren();
            list.hidden = true;
            empty.hidden = false;
            name.textContent = 'Your playlist';
            count.textContent = '0';
            copy.disabled = download.disabled = true;
        }
        services.forEach(service => service.addEventListener('change', () => {
            clear();
            report('Your extracted songs will appear here.');
            input.placeholder = service.value === 'qq' ? 'Enter the QQ Music playlist ID' : 'e.g. 9699105';
        }));
        form.addEventListener('submit', async event => {
            event.preventDefault();
            if (loading) return;
            const playlistId = input.value.trim();
            if (!/^[0-9]+$/.test(playlistId)) return report('Enter a numeric playlist ID.', 'error');
            const service = form.querySelector('[name="service"]:checked').value;
            loading = true;
            submit.disabled = true;
            services.forEach(item => { item.disabled = true; });
            document.getElementById('submit-label').textContent = 'Extracting…';
            document.getElementById('results').setAttribute('aria-busy', 'true');
            clear();
            report('Loading all playlist songs. Large playlists may take a few minutes.', 'loading');
            const controller = new AbortController();
            const timer = setTimeout(() => controller.abort(), 300000);
            try {
                const response = await fetch(form.action, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
                    body: JSON.stringify({ playlistId, service }), signal: controller.signal
                });
                let result;
                try { result = await response.json(); }
                catch (_) { throw new Error('The server returned an unexpected response. Please try again.'); }
                if (!response.ok) throw new Error(result.error || 'Playlist request failed.');
                if (!Array.isArray(result.songs)) throw new Error('Unexpected server response.');
                output.value = result.songs.map(song => `${song.title} - ${song.author}`).join('\n');
                name.textContent = result.name || 'Untitled playlist';
                filename = `${service}-playlist-${playlistId}`;
                count.textContent = String(result.songs.length);
                const fragment = document.createDocumentFragment();
                result.songs.forEach((song, index) => {
                    const row = document.createElement('tr');
                    [String(index + 1).padStart(2, '0'), song.title, song.author].forEach((value, column) => {
                        const cell = document.createElement('td');
                        cell.textContent = value;
                        if (!column) cell.className = 'number';
                        row.appendChild(cell);
                    });
                    fragment.appendChild(row);
                });
                rows.appendChild(fragment);
                list.hidden = result.songs.length === 0;
                empty.hidden = result.songs.length > 0;
                copy.disabled = download.disabled = result.songs.length === 0;
                report(result.warning || (result.songs.length ? 'All available songs are ready to export.' : 'This playlist is empty.'), result.warning ? 'warning' : 'ready');
            } catch (error) {
                report(error.name === 'AbortError' ? 'Request timed out. Please try again.' : error.message, 'error');
            } finally {
                clearTimeout(timer);
                loading = false;
                submit.disabled = false;
                services.forEach(item => { item.disabled = false; });
                document.getElementById('submit-label').textContent = 'Extract songs';
                document.getElementById('results').setAttribute('aria-busy', 'false');
            }
        });
        copy.addEventListener('click', async () => {
            if (!output.value) return;
            try {
                if (!navigator.clipboard) throw new Error('Clipboard unavailable');
                await navigator.clipboard.writeText(output.value);
                report('Song list copied to your clipboard.');
            } catch (_) {
                const field = document.createElement('textarea');
                field.value = output.value;
                field.style.position = 'fixed';
                field.style.opacity = '0';
                document.body.appendChild(field);
                try {
                    field.select();
                    if (!document.execCommand('copy')) throw new Error('Copy failed');
                    report('Song list copied to your clipboard.');
                } catch (_) { report('Copy failed. Use Download .txt to save your list.', 'error'); }
                finally { field.remove(); copy.focus(); }
            }
        });
        download.addEventListener('click', () => {
            if (!output.value) return;
            const url = URL.createObjectURL(new Blob([output.value + '\n'], { type: 'text/plain;charset=utf-8' }));
            const link = document.createElement('a');
            link.href = url;
            link.download = `${filename}.txt`;
            document.body.appendChild(link);
            link.click();
            link.remove();
            setTimeout(() => URL.revokeObjectURL(url), 1000);
        });
    }
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', initialize, { once: true });
    else initialize();
})();
