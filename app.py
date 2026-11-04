import collections
import time
from datetime import datetime
from flask import Flask, render_template_string, request, jsonify

app = Flask(__name__)

# Storage for queues and signals
queues = collections.defaultdict(collections.deque)
current_signal = collections.defaultdict(lambda: "00000000")
last_pop_time = collections.defaultdict(float)
last_roblox_ping = collections.defaultdict(lambda: "Never")

INTERVAL_SEC = 0.35  # 350 ms interval per character

# 6-bit character mapping
def get_char_6bit(char):
    clean = char.lower()
    if 'a' <= clean <= 'z':
        return ord(clean) - ord('a') + 1
    elif '0' <= clean <= '9':
        return int(clean) + 27
    elif char == ' ':
        return 0
    return 0

def text_to_8bit_clock(char):
    """
    8-bit format:
    - Bits 1-6: Symbol code
    - Bit 7: Shift (1 for uppercase)
    - Bit 8: Clock (1 when sending active character)
    """
    is_shift = "1" if char.isupper() else "0"
    clock_bit = "1"
    
    code_6bit = get_char_6bit(char)
    bits_6 = format(code_6bit, '06b')
    
    return bits_6 + is_shift + clock_bit

# --- HTML TEMPLATES ---

MAIN_HUB_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Build Logic - Control Hub</title>
    <link href="https://fonts.googleapis.com/css2?family=Fira+Code:wght@500;700&family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: 'Inter', sans-serif; background-color: #0b0f19; color: #c9d1d9; padding: 40px 20px; }
        .container { max-width: 800px; margin: 0 auto; }
        h1 { font-size: 28px; color: #58a6ff; margin-bottom: 8px; text-align: center; }
        p.subtitle { text-align: center; color: #8b949e; margin-bottom: 30px; font-size: 15px; }
        
        .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 30px; }
        @media (max-width: 600px) { .grid { grid-template-columns: 1fr; } }
        
        .card { background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 20px; box-shadow: 0 8px 24px rgba(0,0,0,0.5); transition: 0.2s; }
        .card:hover { border-color: #58a6ff; }
        .card h3 { color: #58a6ff; font-size: 18px; margin-bottom: 8px; }
        .card p { color: #8b949e; font-size: 13px; margin-bottom: 14px; line-height: 1.4; }
        .btn { display: inline-block; padding: 10px 16px; border-radius: 6px; background: #238636; color: #fff; font-weight: 600; text-decoration: none; font-size: 14px; text-align: center; width: 100%; }
        .btn:hover { background: #2ea043; }
        .btn-secondary { background: #21262d; border: 1px solid #30363d; color: #c9d1d9; }
        .btn-secondary:hover { background: #30363d; color: #fff; }

        .instructions { background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 24px; margin-bottom: 30px; }
        .instructions h2 { font-size: 18px; color: #f0f6fc; margin-bottom: 12px; }
        .instructions ol { padding-left: 20px; color: #8b949e; font-size: 14px; line-height: 1.6; }
        .instructions li { margin-bottom: 8px; }
        code { font-family: 'Fira Code', monospace; background: #0d1117; padding: 2px 6px; border-radius: 4px; color: #3fb950; border: 1px solid #30363d; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🌐 Build Logic Control Hub</h1>
        <p class="subtitle">External web controller for Roblox HTTP Transmitters</p>

        <div class="grid">
            <div class="card">
                <h3>⌨️ Typewriter</h3>
                <p>Send text strings sequentially to your Roblox display using 8-bit encoding.</p>
                <a href="/typewriter" class="btn">Open Typewriter</a>
            </div>
            <div class="card">
                <h3>🎨 Colored Typewriter</h3>
                <p>Expanded 16x16 grid panel supporting colors and text transmission.</p>
                <a href="/colored-typewriter" class="btn btn-secondary">Open Panel</a>
            </div>
            <div class="card">
                <h3>⚡ Upgraded Typewriter</h3>
                <p>Advanced real-time pixel updating with custom coordinate mapping.</p>
                <a href="/upgraded-typewriter" class="btn btn-secondary">Open Panel</a>
            </div>
            <div class="card">
                <h3>🎮 Game Engine</h3>
                <p>Interactive two-way communication, button inputs, and minigames hub.</p>
                <a href="/game-engine" class="btn btn-secondary">Open Engine</a>
            </div>
        </div>

        <div class="instructions">
            <h2>⚙️ Roblox HTTP Transmitter Setup Guide</h2>
            <ol>
                <li>In Roblox, select your <b>HTTP Transmitter</b> and paste the endpoint URL: <br><code>{{ base_url }}/api/typewriter</code></li>
                <li>In the transmitter's <b>Headers</b> property, add your Session ID with an <code>A</code> suffix: <br><code>SID: MY_SESSION_A</code></li>
                <li>Open the <b>Typewriter</b> app above, enter <code>MY_SESSION</code> as your SID, type your text, and hit send!</li>
                <li><b>Tutorial Videos:</b> YouTube video guides for each section are coming soon! Stay tuned.</li>
            </ol>
        </div>
    </div>
</body>
</html>
"""

TYPEWRITER_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Typewriter - Build Logic Hub</title>
    <link href="https://fonts.googleapis.com/css2?family=Fira+Code:wght@500;700&family=Inter:wght@400;600&display=swap" rel="stylesheet">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: 'Inter', sans-serif; background-color: #0b0f19; color: #c9d1d9; padding: 30px; }
        .container { max-width: 600px; margin: 0 auto; background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 24px; box-shadow: 0 8px 24px rgba(0,0,0,0.5); }
        .back-link { display: inline-block; color: #58a6ff; text-decoration: none; font-size: 13px; margin-bottom: 16px; }
        .back-link:hover { text-decoration: underline; }
        h1 { font-size: 20px; color: #58a6ff; margin-bottom: 20px; text-align: center; }
        label { display: block; font-size: 13px; color: #8b949e; margin-bottom: 6px; }
        input[type=text] { width: 100%; padding: 12px; background: #0d1117; border: 1px solid #30363d; border-radius: 6px; color: #f0f6fc; font-family: 'Fira Code', monospace; font-size: 15px; margin-bottom: 16px; }
        input[type=text]:focus { border-color: #58a6ff; outline: none; }
        button { width: 100%; padding: 12px; border-radius: 6px; border: none; font-weight: 600; background: #238636; color: #fff; cursor: pointer; font-size: 15px; }
        button:hover { background: #2ea043; }
        .status-box { margin-top: 20px; padding: 16px; background: #0d1117; border: 1px solid #21262d; border-radius: 8px; text-align: center; }
        .binary-display { font-family: 'Fira Code', monospace; font-size: 28px; color: #3fb950; letter-spacing: 4px; margin: 10px 0; }
        .info { font-size: 13px; color: #8b949e; margin-top: 6px; }
        .badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: 600; background: #21262d; color: #f2cc60; border: 1px solid #30363d; }
    </style>
    <script>
        setInterval(async () => {
            let sid = document.getElementById('sid-input').value.trim();
            if(!sid) return;
            try {
                let res = await fetch('/api/typewriter/status?sid=' + encodeURIComponent(sid + 'A'));
                let data = await res.json();
                document.getElementById('binary-val').innerText = data.current_signal;
                document.getElementById('queue-len').innerText = data.queue_len;
                document.getElementById('last-ping').innerText = data.last_ping;
            } catch(e) {}
        }, 300);
    </script>
</head>
<body>
    <div class="container">
        <a href="/" class="back-link">← Back to Hub</a>
        <h1>⌨️ Typewriter Panel</h1>
        <form method="POST" action="/typewriter/send">
            <label>Session ID (SID): <span style="font-size:11px; color:#8b949e;">(Roblox expects SID + 'A')</span></label>
            <input type="text" id="sid-input" name="sid" placeholder="e.g. my_game" value="{{ sid }}" required autocomplete="off">
            
            <label>Text to send into Roblox:</label>
            <input type="text" name="text" placeholder="Type something..." required autocomplete="off">
            
            <button type="submit">Enqueue Text</button>
        </form>

        <div class="status-box">
            <div class="info">Current Active Signal (8-bit):</div>
            <div class="binary-display" id="binary-val">00000000</div>
            <div class="info">Remaining in Queue: <span id="queue-len" class="badge">0</span> characters</div>
            <div class="info" style="margin-top: 10px;">Last Roblox Connection: <span id="last-ping" style="color: #58a6ff;">Never</span></div>
        </div>
    </div>
</body>
</html>
"""

STUB_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ title }} - Build Logic Hub</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Inter', sans-serif; background-color: #0b0f19; color: #c9d1d9; padding: 50px; text-align: center; }
        .container { max-width: 500px; margin: 0 auto; background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 30px; }
        h1 { color: #58a6ff; font-size: 22px; margin-bottom: 12px; }
        p { color: #8b949e; font-size: 14px; margin-bottom: 20px; }
        a { color: #58a6ff; text-decoration: none; font-weight: 600; }
        a:hover { text-decoration: underline; }
    </style>
</head>
<body>
    <div class="container">
        <h1>{{ title }}</h1>
        <p>This module is currently under development according to our step-by-step plan. It will be ready soon!</p>
        <a href="/">← Return to Hub</a>
    </div>
</body>
</html>
"""

# --- ROUTES ---

@app.route('/')
def main_hub():
    base_url = request.host_url.rstrip('/')
    return render_template_string(MAIN_HUB_TEMPLATE, base_url=base_url)

@app.route('/typewriter')
def typewriter_page():
    sid = request.args.get('sid', '')
    return render_template_string(TYPEWRITER_TEMPLATE, sid=sid)

@app.route('/colored-typewriter')
def colored_typewriter():
    return render_template_string(STUB_TEMPLATE, title="Colored Typewriter")

@app.route('/upgraded-typewriter')
def upgraded_typewriter():
    return render_template_string(STUB_TEMPLATE, title="Upgraded Typewriter")

@app.route('/game-engine')
def game_engine():
    return render_template_string(STUB_TEMPLATE, title="Game Engine")

@app.route('/typewriter/send', methods=['POST'])
def send_text():
    sid = request.form.get('sid', '').strip()
    text = request.form.get('text', '')
    
    if sid and text:
        target_sid = sid + "A"
        for char in text:
            bin_val = text_to_8bit_clock(char)
            queues[target_sid].append(bin_val)

    return f"<script>window.location.href='/typewriter?sid={sid}';</script>"

# --- ROBLOX HTTP TRANSMITTER API ENDPOINT ---
@app.route('/api/typewriter', methods=['GET'])
def get_typewriter_signal():
    # Roblox transmitter sends SID in header, e.g. SID: my_gameA
    sid = request.headers.get('SID', '').strip()
    
    if not sid:
        return jsonify({"value": "00000000"})

    # Track last time Roblox polled this endpoint
    last_roblox_ping[sid] = datetime.now().strftime("%H:%M:%S")

    now = time.time()
    if now - last_pop_time[sid] >= INTERVAL_SEC:
        if queues[sid]:
            current_signal[sid] = queues[sid].popleft()
            last_pop_time[sid] = now
        else:
            # If queue is empty, turn off clock (bit 8 = 0)
            current_signal[sid] = "00000000"

    return jsonify({"value": current_signal[sid]})

@app.route('/api/typewriter/status', methods=['GET'])
def typewriter_status():
    sid = request.args.get('sid', '').strip()
    return jsonify({
        "current_signal": current_signal[sid],
        "queue_len": len(queues[sid]),
        "last_ping": last_roblox_ping[sid]
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
