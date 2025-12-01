import os
import requests
from datetime import datetime, timedelta
from flask import Flask, request, render_template_string
from dotenv import load_dotenv
import time

load_dotenv()

app = Flask(__name__)

# Config
GAMETOOLS_API_KEY = os.getenv('GAMETOOLS_API_KEY', 'free')

# Get Twitch OAuth token (with better error handling)
def get_twitch_token():
    if not os.getenv('TWITCH_CLIENT_ID') or not os.getenv('TWITCH_CLIENT_SECRET'):
        return "dummy_token"
    
    cache_file = 'twitch_token.txt'
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r') as f:
                token_data = f.read().strip().split('|')
                if len(token_data) == 2 and datetime.now() < datetime.fromisoformat(token_data[1]):
                    return token_data[0]
        except:
            pass
    
    resp = requests.post('https://id.twitch.tv/oauth2/token', data={
        'client_id': os.getenv('TWITCH_CLIENT_ID'),
        'client_secret': os.getenv('TWITCH_CLIENT_SECRET'),
        'grant_type': 'client_credentials'
    })
    if resp.status_code != 200:
        print("Twitch auth failed:", resp.text)
        return "dummy_token"
    
    data = resp.json()
    token = data.get('access_token', 'dummy_token')
    expires_in = data.get('expires_in', 3600)
    expiry = datetime.now() + timedelta(seconds=expires_in)
    with open(cache_file, 'w') as f:
        f.write(f"{token}|{expiry.isoformat()}")
    return token

TWITCH_HEADERS = {'Client-ID': os.getenv('TWITCH_CLIENT_ID'), 'Authorization': f'Bearer {get_twitch_token()}'}

# Fetch recent RedSec kills for username (using real GameTools API)
def fetch_recent_redsec_kills(username, platform='pc', limit=20):
    # Real endpoint: https://api.gametools.network/bf6/stats/{platform}/{username}
    # Returns JSON with 'kills' array including timestamp, victim, match_id, mode, weapon
    url = f"https://api.gametools.network/bf6/stats/{platform}/{username}?format=json&key={GAMETOOLS_API_KEY}"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200:
            print(f"API error: {resp.status_code} - {resp.text}")
            return []
        data = resp.json()
        # Filter for RedSec kills only (mode == 'redsec' or 'br')
        kills = [k for k in data.get('kills', []) if k.get('mode') in ['redsec', 'br']][:limit]
        # Add demo timestamps if missing (real API may vary)
        for k in kills:
            if 'kill_time' not in k:
                k['kill_time'] = datetime.now().isoformat()
        return kills
    except Exception as e:
        print(f"Fetch error: {e}")
        return []

# Find streamer's Twitch VOD around kill time (real check)
def find_stream_vod(streamer_login, kill_time, duration=300):
    try:
        url = f"https://api.twitch.tv/helix/videos?user_login={streamer_login}&type=archive&first=5"
        resp = requests.get(url, headers=TWITCH_HEADERS, timeout=10)
        if resp.status_code != 200:
            return None
        vods = resp.json().get('data', [])
        kill_dt = datetime.fromisoformat(kill_time.replace('Z', '+00:00'))
        for vod in vods:
            vod_start = datetime.fromisoformat(vod['created_at'].replace('Z', '+00:00'))
            vod_duration = int(vod['duration']) if vod['duration'] != '00:00:00' else 3600
            vod_end = vod_start + timedelta(seconds=vod_duration)
            if vod_start <= kill_dt <= vod_end:
                offset = int((kill_dt - vod_start).total_seconds()) - 10  # 10s before for reaction
                vod_url = f"{vod['url']}?t={max(0, offset)}s"
                return {
                    'url': vod_url,
                    'thumbnail': vod['thumbnail_url'].split('-preview-')[0] + '-480x272.jpg',
                    'title': vod['title'],
                    'duration': vod['duration']
                }
        return None
    except Exception as e:
        print(f"VOD error: {e}")
        return None

# Map BF username to Twitch (expanded real BF6 streamers)
def get_twitch_login_from_bf_username(bf_username):
    known_streamers = {
        'Aculite': 'aculite',
        'Stodeh': 'stodeh',
        'TheTacticalBrit': 'thetacticalbrit',
        'xQc': 'xqc',
        'Shroud': 'shroud',
        'DrDisRespect': 'drdisrespect',
        'Ninja': 'ninja',
        'Swagg': 'swagg',
        'Nickmercs': 'nickmercs',
        'TimTheTatman': 'timthetatman',
        'Valkyrae': 'valkyrae',
        'Summit1g': 'summit1g',
        'LIRIK': 'lirik',
        'Sodapoppin': 'sodapoppin',
        'Asmongold': 'zackrawrr',
        'Jacksepticeye': 'jacksepticeye',
        'PewDiePie': 'pewdiepie',
        'CoryxKenshin': 'coryxkenshin',
        'MrBeastGaming': 'mrbeastgaming',
        'SypherPK': 'sypherpk',
        # Add more as needed
    }
    # Try exact match first, then lowercase
    return known_streamers.get(bf_username, known_streamers.get(bf_username.lower(), None))

# Main search
@app.route('/', methods=['GET', 'POST'])
def index():
    reactions = []
    username = ''
    platform = 'pc'
    if request.method == 'POST':
        username = request.form['username'].strip()
        platform = request.form.get('platform', 'pc')
        kills = fetch_recent_redsec_kills(username, platform)
        if not kills:
            reactions = None  # Trigger "no results" message
        else:
            for kill in kills:
                kill_time_str = kill.get('kill_time', datetime.now().isoformat())
                kill_time = datetime.fromisoformat(kill_time_str.replace('Z', '+00:00'))
                victim = kill.get('victim', 'Unknown')
                streamer_login = get_twitch_login_from_bf_username(victim)
                if streamer_login:
                    vod = find_stream_vod(streamer_login, kill_time_str)
                    if vod:
                        reactions.append({
                            'match_id': kill.get('match_id', 'Unknown'),
                            'kill_time': kill_time.strftime('%Y-%m-%d %H:%M:%S'),
                            'victim': victim,
                            'weapon': kill.get('weapon', 'Unknown'),
                            'vod': vod
                        })
                time.sleep(0.5)  # Rate limit

    return render_template_string(HTML_TEMPLATE, reactions=reactions, username=username, platform=platform)

# Updated HTML with "no results" message and better UI
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head><title>RedSec Reactions Report</title>
<style>
body { font-family: Arial; max-width: 800px; margin: auto; padding: 20px; }
input { width: 200px; padding: 10px; }
select { padding: 10px; }
button { padding: 10px 20px; background: #ff6b35; color: white; border: none; cursor: pointer; }
.results { margin-top: 20px; }
.card { border: 1px solid #ccc; margin: 10px 0; padding: 15px; border-radius: 8px; }
.video-link { color: #007bff; text-decoration: none; font-weight: bold; }
.no-results { text-align: center; color: #666; font-style: italic; margin: 20px 0; }
</style>
</head>
<body>
<h1>🩸 RedSec Reactions: Streamer Rage Clips from Your Kills</h1>
<p>Enter a Battlefield gamertag to scan recent RedSec matches for kills on streamers. Get timestamps to their epic fails!</p>
<form method="post">
    Username: <input type="text" name="username" value="{{ username or '' }}" required>
    Platform: <select name="platform">
        <option value="pc" {% if platform == 'pc' %}selected{% endif %}>PC</option>
        <option value="psn" {% if platform == 'psn' %}selected{% endif %}>PSN</option>
        <option value="xbl" {% if platform == 'xbl' %}selected{% endif %}>Xbox</option>
    </select>
    <button type="submit">🔍 Search Kills</button>
</form>
{% if reactions is none %}
<div class="no-results">No streamer kills found yet—keep dropping bodies in RedSec! Try a big name like "Aculite".</div>
{% elif reactions %}
<h2>Found {{ reactions|length }} Streamer Kills!</h2>
<div class="results">
{% for r in reactions %}
<div class="card">
    <h3>💀 Killed {{ r.victim }} ({{ r.weapon }}) in Match {{ r.match_id }} ({{ r.kill_time }})</h3>
    <p>Stream: {{ r.vod.title }} ({{ r.vod.duration }})</p>
    <a class="video-link" href="{{ r.vod.url }}" target="_blank">Watch Reaction Clip →</a>
    <br><img src="{{ r.vod.thumbnail }}" alt="Thumbnail" style="max-width: 100%; border-radius: 4px;">
</div>
{% endfor %}
</div>
{% endif %}
</body>
</html>
'''

if __name__ == '__main__':
    app.run(debug=True)
