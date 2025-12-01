import os
import requests
from datetime import datetime, timedelta
from flask import Flask, request, render_template_string
from dotenv import load_dotenv
from bs4 import BeautifulSoup  # For scraping
import time
import re

load_dotenv()

app = Flask(__name__)

# Config
GAMETOOLS_API_KEY = os.getenv('GAMETOOLS_API_KEY', 'free')  # Fallback, but we're using scraping now

# Get Twitch OAuth token (unchanged)
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

# Scrape recent RedSec kills from battlefieldtracker.com
def fetch_recent_redsec_kills(username, platform='pc', limit=20):
    # Map platform to tracker URL param
    plat_map = {'pc': 'origin', 'psn': 'psn', 'xbl': 'xbox'}
    plat_param = plat_map.get(platform, 'origin')
    url = f"https://battlefieldtracker.com/bf6/profile/{plat_param}/{username}/matches"
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}  # Avoid blocks
        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            print(f"Tracker error: {resp.status_code}")
            return []
        
        soup = BeautifulSoup(resp.text, 'lxml')
        kills = []
        # Parse match table (tracker structure: rows with match ID, mode, kills)
        match_rows = soup.find_all('tr', class_='match-row')[:limit]  # Recent matches
        for row in match_rows:
            mode = row.find('td', class_='mode').text.strip() if row.find('td', class_='mode') else ''
            if 'RedSec' not in mode and 'BR' not in mode:  # Filter RedSec/BR
                continue
            kill_td = row.find('td', class_='kills')
            if kill_td:
                # Extract kill details (simplified: assume 1-3 kills per match; in prod, drill into match page)
                kill_count = int(kill_td.text.strip())
                match_id = row.find('a', href=re.compile(r'/match/'))['href'].split('/')[-1] if row.find('a', href=re.compile(r'/match/')) else 'Unknown'
                kill_time = datetime.now() - timedelta(hours=1 * len(kills))  # Approx timestamps; real: parse date col
                for i in range(min(kill_count, 3)):  # Demo 3 kills max per match
                    # Fake victims for demo; real: would scrape /match/{id} for victim names
                    demo_victim = f"Player{i+1}"  # Placeholder—expand to real scrape
                    kills.append({
                        'victim': demo_victim,
                        'kill_time': kill_time.isoformat(),
                        'match_id': match_id,
                        'mode': mode,
                        'weapon': 'NTW-50'  # Demo; real from match details
                    })
        print(f"Scraped {len(kills)} kills for {username}")
        return kills[:limit]
    except Exception as e:
        print(f"Scrape error: {e}")
        return []

# Find streamer's Twitch VOD (unchanged)
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
                offset = int((kill_dt - vod_start).total_seconds()) - 10
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

# Map BF username to Twitch (expanded to 30+)
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
        'DrLupo': 'drlupo',
        'Myth': 'myth',
        'Tfue': 'tfue',
        'Clix': 'clix',
        'Bugha': 'bugha',
        'Loserfruit': 'loserfruit',
        'Pokimane': 'pokimanelol',
        'Amouranth': 'amouranth',
        'IShowSpeed': 'ishowspeed',
        'KaiCenat': 'kaicenat',
    }
    return known_streamers.get(bf_username, known_streamers.get(bf_username.lower(), None))

# Main search (updated to use scraping)
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
            reactions = None  # No results message
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
                time.sleep(1)  # Slower rate limit for scraping

    return render_template_string(HTML_TEMPLATE, reactions=reactions, username=username, platform=platform)

# HTML (unchanged, but added debug note)
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
.debug { font-size: 0.8em; color: #999; }
</style>
</head>
<body>
<h1>🩸 RedSec Reactions: Streamer Rage Clips from Your Kills</h1>
<p>Enter a Battlefield gamertag to scan recent RedSec matches for kills on streamers. Get timestamps to their epic fails! (Debug: Check Heroku logs for API details.)</p>
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
<div class="no-results">No streamer kills found yet—keep dropping bodies in RedSec! Try a big name like "Aculite". (If empty, check logs—API may need time to index.)</div>
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
<div class="debug">Searched: {{ username }} on {{ platform }} | Kills scanned: {{ reactions|length if reactions else 0 }}</div>
</body>
</html>
'''

if __name__ == '__main__':
    app.run(debug=True)
