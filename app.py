import os
import requests
import random
import re
from datetime import datetime, timedelta
from flask import Flask, request, render_template_string
from dotenv import load_dotenv
import time

load_dotenv()
app = Flask(__name__)

# ====================== TWITCH TOKEN ======================
def get_twitch_token():
    if not os.getenv('TWITCH_CLIENT_ID') or not os.getenv('TWITCH_CLIENT_SECRET'):
        return "dummy"
    cache_file = 'twitch_token.txt'
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r') as f:
                token, expiry = f.read().strip().split('|')
                if datetime.fromisoformat(expiry) > datetime.now():
                    return token
        except:
            pass
    resp = requests.post('https://id.twitch.tv/oauth2/token', data={
        'client_id': os.getenv('TWITCH_CLIENT_ID'),
        'client_secret': os.getenv('TWITCH_CLIENT_SECRET'),
        'grant_type': 'client_credentials'
    })
    if resp.status_code == 200 and resp.json().get('access_token'):
        token = resp.json()['access_token']
        expiry = datetime.now() + timedelta(seconds=resp.json().get('expires_in', 3600))
        with open(cache_file, 'w') as f:
            f.write(f"{token}|{expiry.isoformat()}")
        return token
    return ""

TWITCH_HEADERS = {'Client-ID': os.getenv('TWITCH_CLIENT_ID'), 'Authorization': f'Bearer {get_twitch_token()}'}

# ====================== DEMO KILLS (until BF6 trackers are ready) ======================
def fetch_recent_redsec_kills(username, platform='pc'):
    print(f"[DEMO MODE] Generating kills for {username} ({platform})")
    demo_kills = []
    victims = ['xQc', 'Valkyrae', 'Swagg', 'Shroud', 'Nickmercs', 'DrDisRespect']
    weapons = ['NTW-50', 'M5A3', 'GOL Magnum', 'PP-29', 'AK-24']
    for i in range(3):
        victim = random.choice(victims)
        demo_kills.append({
            'victim': victim,
            'weapon': random.choice(weapons),
            'kill_time': (datetime.now() - timedelta(minutes=random.randint(10, 240))).isoformat(),
            'match_id': f"DEMO-{random.randint(100000, 999999)}"
        })
    return demo_kills

# ====================== FIND VOD (real + demo fallback) ======================
def find_stream_vod(streamer_login):
    # Try real Twitch API first
    try:
        url = f"https://api.twitch.tv/helix/videos?user_login={streamer_login}&type=archive&first=3"
        resp = requests.get(url, headers=TWITCH_HEADERS, timeout=8)
        if resp.status_code == 200 and resp.json().get('data'):
            vod = resp.json()['data'][0]
            offset = random.randint(600, 3600)  # random point in stream
            return {
                'url': f"{vod['url']}?t={offset}s",
                'title': vod['title'],
                'thumbnail': vod['thumbnail_url'].replace('%{width}', '480').replace('%{height}', '272'),
                'duration': vod.get('duration', '10m')
            }
    except:
        pass
    # Demo fallback if Twitch fails or no VOD
    return {
        'url': f"https://twitch.tv/{streamer_login}",
        'title': f"{streamer_login} raging in RedSec (demo clip)",
        'thumbnail': f"https://static-cdn.jtvnw.net/previews-ttv/live_user_{streamer_login}-480x272.jpg",
        'duration': '8:42'
    }

# ====================== STREAMER MAP ======================
KNOWN_STREAMERS = {
    'xqc': 'xqc', 'valkyrae': 'valkyrae', 'swagg': 'swagg',
    'shroud': 'shroud', 'nickmercs': 'nickmercs', 'drdisrespect': 'drdisrespect',
    'ninja': 'ninja', 'timthetatman': 'timthetatman', 'pokimane': 'pokimanelol',
    'summit1g': 'summit1g', 'lirik': 'lirik'
    # add your PSN here later
}

# ====================== MAIN ROUTE ======================
@app.route('/', methods=['GET', 'POST'])
def index():
    reactions = []
    username = ''
    platform = 'pc'
    scanned = 0

    if request.method == 'POST':
        username = request.form['username'].strip()
        platform = request.form.get('platform', 'pc')
        kills = fetch_recent_redsec_kills(username, platform)
        scanned = len(kills)

        for kill in kills:
            victim_lower = kill['victim'].lower()
            twitch_login = KNOWN_STREAMERS.get(victim_lower)
            if twitch_login:
                vod = find_stream_vod(twitch_login)
                reactions.append({
                    'victim': kill['victim'],
                    'weapon': kill['weapon'],
                    'match_id': kill['match_id'],
                    'kill_time': datetime.fromisoformat(kill['kill_time'].replace('Z', '+00:00')).strftime('%b %d, %H:%M'),
                    'vod': vod
                })
            time.sleep(0.5)

    return render_template_string(HTML_TEMPLATE, reactions=reactions, username=username, platform=platform, scanned=scanned)

# ====================== HTML ======================
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>RedSec Reactions</title>
    <style>
        body { font-family: system-ui, sans-serif; max-width: 850px; margin: 40px auto; padding: 20px; background:#0e0e10; color:#eee; }
        h1 { color: #ff6b35; text-align:center; }
        form { text-align:center; margin:30px 0; }
        input, select, button { padding:12px; margin:5px; font-size:1.1em; border-radius:8px; border:none; }
        button { background:#ff6b35; color:white; cursor:pointer; }
        .card { background:#1a1a1d; padding:20px; margin:15px 0; border-radius:12px; }
        .video-link { color:#9146ff; font-weight:bold; font-size:1.2em; }
        .no-results { text-align:center; font-size:1.3em; color:#888; margin:40px; }
    </style>
</head>
<body>
    <h1>RedSec Reactions</h1>
    <p style="text-align:center;">Enter any Battlefield gamertag → see every time you killed a streamer in RedSec (with clip!)</p>
    
    <form method="post">
        <input type="text" name="username" placeholder="Gamertag" value="{{ username }}" required>
        <select name="platform">
            <option value="pc" {% if platform=='pc' %}selected{% endif %}>PC</option>
            <option value="psn" {% if platform=='psn' %}selected{% endif %}>PlayStation</option>
            <option value="xbl" {% if platform=='xbl' %}selected{% endif %}>Xbox</option>
        </select>
        <button type="submit">Search Kills</button>
    </form>

    {% if reactions is defined and reactions == [] %}
        <div class="no-results">
            No streamer kills found yet<br><small>(BF6 data still rolling out — demo mode active)</small>
        </div>
    {% elif reactions %}
        <h2 style="text-align:center;">Found {{ reactions|length }} streamer kills! ({{ scanned }} total scanned)</h2>
        {% for r in reactions %}
        <div class="card">
            <h3>Killed <strong>{{ r.victim }}</strong> with {{ r.weapon }}</h3>
            <p>Match {{ r.match_id }} • {{ r.kill_time }}</p>
            <a class="video-link" href="{{ r.vod.url }}" target="_blank">Watch the rage moment →</a>
            <br><br>
            <img src="{{ r.vod.thumbnail }}" style="width:100%; border-radius:8px;">
            <small>{{ r.vod.title }}</small>
        </div>
        {% endfor %}
    {% endif %}

    <div style="text-align:center; margin-top:50px; color:#666; font-size:0.9em;">
        RedSec Reactions • Live demo while BF6 trackers catch up • Built by poohty
    </div>
</body>
</html>
'''

if __name__ == '__main__':
    app.run(debug=True)
