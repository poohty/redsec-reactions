import os
import requests
from datetime import datetime, timedelta
from flask import Flask, request, render_template_string, jsonify
from dotenv import load_dotenv
import time  # For rate limiting

load_dotenv()

app = Flask(__name__)

# Config
TWITCH_CLIENT_ID = os.getenv('TWITCH_CLIENT_ID')
TWITCH_CLIENT_SECRET = os.getenv('TWITCH_CLIENT_SECRET')
GAMETOOLS_API_KEY = os.getenv('GAMETOOLS_API_KEY')
REDSEC_GAME_ID = 25260  # Placeholder; use actual BF6/RedSec ID from API docs

# Get Twitch OAuth token (cached for 60 days)
def get_twitch_token():
    cache_file = 'twitch_token.txt'
    if os.path.exists(cache_file):
        with open(cache_file, 'r') as f:
            token_data = f.read().strip().split('|')
            if datetime.now() < datetime.fromisoformat(token_data[1]):
                return token_data[0]
    # Refresh
    resp = requests.post('https://id.twitch.tv/oauth2/token', data={
        'client_id': TWITCH_CLIENT_ID,
        'client_secret': TWITCH_CLIENT_SECRET,
        'grant_type': 'client_credentials'
    })
    token = resp.json()['access_token']
    expiry = datetime.now() + timedelta(hours=4)  # Approx
    with open(cache_file, 'w') as f:
        f.write(f"{token}|{expiry.isoformat()}")
    return token

TWITCH_HEADERS = {'Client-ID': TWITCH_CLIENT_ID, 'Authorization': f'Bearer {get_twitch_token()}'}

# Fetch recent kills for username (using Gametools API; adapt for RedSec filter)
def fetch_recent_kills(username, platform='pc', limit=50):
    # Example endpoint for BF stats (adapt for BF6/RedSec; assumes kills include timestamps/victim)
    url = f"https://api.gametools.network/bf6/stats/{platform}/{username}?format=json&key={GAMETOOLS_API_KEY}"
    resp = requests.get(url)
    if resp.status_code != 200:
        return []
    data = resp.json()
    # Parse kills: Assume structure has list of {'kill_time': ts, 'victim': name, 'match_id': id, 'mode': 'redsec'}
    kills = [k for k in data.get('kills', []) if k.get('mode') == 'redsec'][:limit]
    return kills

# Find streamer's Twitch VOD around kill time
def find_stream_vod(streamer_login, kill_time, duration=300):  # +/- 5 min window
    # Get recent videos (VODs)
    url = f"https://api.twitch.tv/helix/videos?user_login={streamer_login}&type=archive&first=10"
    resp = requests.get(url, headers=TWITCH_HEADERS)
    vods = resp.json().get('data', [])
    for vod in vods:
        vod_start = datetime.fromisoformat(vod['created_at'])
        vod_end = vod_start + timedelta(seconds=int(vod['duration']))
        if vod_start <= kill_time <= vod_end:
            # Calculate offset seconds from vod_start
            offset = int((kill_time - vod_start).total_seconds()) - 10  # 10s before for reaction
            vod_url = f"{vod['url']}?t={offset}s"
            return {
                'url': vod_url,
                'thumbnail': vod['thumbnail_url'].split('-preview-')[0] + '-480x272.jpg',
                'title': vod['title'],
                'duration': vod['duration']
            }
    return None

# Main search endpoint
@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        username = request.form['username']
        platform = request.form.get('platform', 'pc')
        kills = fetch_recent_kills(username, platform)
        reactions = []
        for kill in kills:
            kill_time = datetime.fromisoformat(kill['kill_time'])
            victim = kill['victim']
            # Assume we have a simple map or API to get Twitch login from BF username (in prod, query Twitch users)
            # For demo: Hardcode/populate from known streamers or add Twitch search
            streamer_login = get_twitch_login_from_bf_username(victim)  # Implement below
            if streamer_login:
                vod = find_stream_vod(streamer_login, kill_time)
                if vod:
                    reactions.append({
                        'match_id': kill['match_id'],
                        'kill_time': kill_time.strftime('%Y-%m-%d %H:%M:%S'),
                        'victim': victim,
                        'vod': vod
                    })
            time.sleep(1)  # Rate limit
        return render_template_string(HTML_TEMPLATE, reactions=reactions, username=username)
    return render_template_string(HTML_TEMPLATE, reactions=[], username='')

# Helper: Map BF username to Twitch (in prod, use Twitch Helix /users endpoint or DB of known streamers)
def get_twitch_login_from_bf_username(bf_username):
    # Demo: Simple dict of known RedSec streamers; expand with API search
    known_streamers = {
        'Shroud': 'shroud',
        'DrDisRespect': 'drdisrespect',
        'Ninja': 'ninja',
        # Add more via Twitch search: requests.get(f"https://api.twitch.tv/helix/users?login={bf_username.lower()}")
    }
    return known_streamers.get(bf_username, None)

# HTML Template (embedded)
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head><title>RedSec Reactions Report</title>
<style>
body { font-family: Arial; max-width: 800px; margin: auto; }
input { width: 200px; padding: 10px; }
.results { margin-top: 20px; }
.card { border: 1px solid #ccc; margin: 10px 0; padding: 10px; }
.video-link { color: blue; text-decoration: none; }
</style>
</head>
<body>
<h1>RedSec Reactions: Find Streamer Reactions to Your Kills</h1>
<p>Enter your Battlefield username to see times you eliminated a streamer in RedSec. Get direct links to their reaction in the VOD!</p>
<form method="post">
    Username: <input type="text" name="username" value="{{ username or '' }}" required>
    Platform: <select name="platform">
        <option value="pc">PC</option>
        <option value="psn">PSN</option>
        <option value="xbl">Xbox</option>
    </select>
    <button type="submit">Search Kills</button>
</form>
{% if reactions %}
<h2>Found {{ reactions|length }} Streamer Kills for {{ username }}</h2>
<div class="results">
{% for r in reactions %}
<div class="card">
    <h3>Killed {{ r.victim }} in Match {{ r.match_id }} ({{ r.kill_time }})</h3>
    <p>Stream: {{ r.vod.title }} ({{ r.vod.duration }}s)</p>
    <a class="video-link" href="{{ r.vod.url }}" target="_blank">Watch Reaction (Click for Timestamp)</a>
    <br><img src="{{ r.vod.thumbnail }}" alt="Thumbnail" style="max-width: 100%;">
</div>
{% endfor %}
</div>
{% endif %}
</body>
</html>
'''

if __name__ == '__main__':
    app.run(debug=True)
