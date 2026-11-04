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

INTERVAL_SEC = 0.35  # 350 ms interval per step (active -> pause)

# --- ADVANCED CUSTOM SYMBOL & CHARACTER MAPPING ---
def get_char_mapping(char):
    """
    Returns (6bit_binary_string, is_shift_bool)
    Based on user specification for letters, numbers, and symbols.
    """
    if 'a' <= char <= 'z':
        idx = ord(char) - ord('a') + 1
        return format(idx, '06b'), False
    elif 'A' <= char <= 'Z':
        idx = ord(char.lower()) - ord('a') + 1
        return format(idx, '06b'), True
    
    # Numbers & their shifted symbol equivalents
    num_map = {
        '1': ('011011', False), '!': ('011011', True),
        '2': ('011100', False), '@': ('011100', True), # approximated from sequence
        '3': ('011101', False), '#': ('011101', True),
        '4': ('011110', False), '$': ('011110', True),
        '5': ('011111', False), '%': ('011111', True),
        '6': ('100000', False), '?': ('100000', True),
        '7': ('100001', False), '&': ('100001', True),
        '8': ('100010', False), '*': ('100010', True),
        '9': ('100011', True),  '(': ('100011', True), # 9 is 100011
        '0': ('100100', False), ')': ('100100', True), # 0 is 100100
    }
    if char in num_map:
        return num_map[char]

    # Unshifted & Shifted Symbols specified by user
    symbol_map = {
        '-': ('100101', False), '_': ('100101', True),
        '=': ('100110', False), '+': ('100110', True),
        '.': ('100111', False),
        ',': ('101000', False), "'": ('101000', True),
        ';': ('101001', False), ':': ('101001', True),
        '/': ('101010', False), '~': ('101010', True),
        '[': ('110101', False), '{': ('110101', True),
        ']': ('110110', False), '}': ('110110', True),
        ' ': ('000000', False)
    }
    if char in symbol_map:
        return symbol_map[char]

    return '000000', False

def text_to_8bit_steps(char):
    """
    Creates two 8-bit steps for the queue (Reversed for Roblox right-to-left output):
    Step 1: [Bits 1-6 symbol] + [Bit 7 shift] + [Bit 8 Clock=1] (Active)
    Step 2: 00000000 (Clock=0 Pause, ensuring distinct edge trigger)
    """
    bits_6, is_shift = get_char_mapping(char)
    shift_bit = "1" if is_shift else "0"
    clock_active = "1"
    
    active_byte = (bits_6 + shift_bit + clock_active)[::-1]
    pause_byte = "00000000"
    return active_byte, pause_byte

# --- COLOR PALETTE MAPPING FOR COLORED TYPEWRITER ---
COLOR_MAP = {
    "black": "000000",
    "white": "111111",
    "dim_white": "111000",
    "red": "100000",
    "green": "010000",
    "blue": "001000",
    "cyan": "011000",
    "magenta": "101000",
    "yellow": "110000",
    "maroon": "000100",
    "grey": "000111",
    "lavender": "001100",
    "sky_blue": "011100",
    "orange": "100010",
    "pink": "111100",
    "beige": "110001"
}

def color_to_8bit(color_name, reset_active=False, clock=True):
    """
    Transmitter B format (8 bits reversed):
    - Bits 1-6: Color code
    - Bit 7: Reset button (1 if active)
    - Bit 8: Clock (1 if transmitting)
    """
    c_bits = COLOR_MAP.get(color_name, "000000")
    r_bit = "1" if reset_active else "0"
    cl_bit = "1" if clock else "0"
    return (c_bits + r_bit + cl_bit)[::-1]


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
                <p>Send text strings sequentially using 8-bit encoding with full symbol support.</p>
                <a href="/typewriter" class="btn">Open Typewriter</a>
            </div>
            <div class="card">
                <h3>🎨 Colored Typewriter</h3>
                <p>16x16 grid panel supporting colors, painting, and remote reset control.</p>
                <a href="/colored-typewriter" class="btn">Open Panel</a>
            </div>
            <div class="card">
                <h3>⚡ Upgraded Typewriter</h3>
                <p>Advanced real-time pixel updating with custom coordinate mapping.</p>
                <a href="/upgraded-typewriter" class="btn btn-secondary">Coming Soon</a>
            </div>
            <div class="card">
                <h3>🎮 Game Engine</h3>
                <p>Interactive two-way communication, button inputs, and minigames hub.</p>
                <a href="/game-engine" class="btn btn-secondary">Coming Soon</a>
            </div>
        </div>

        <div class="instructions">
            <h2>⚙️ Roblox HTTP Transmitter Setup Guide</h2>
            <ol>
                <li>In Roblox, point your transmitters to endpoint URL: <br><code>{{ base_url }}/api/typewriter</code> (or colored endpoint)</li>
                <li>For Typewriter, set Header: <code>SID: MY_SESSION_A</code></li>
                <li>For Colored Typewriter, use two transmitters: <br><code>SID: MY_SESSION_A</code> (Text) and <code>SID: MY_SESSION_B</code> (Colors & Reset)</li>
                <li><b>Tutorial Videos:</b> YouTube video guides for each section are coming soon!</li>
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
            <label>Session ID (SID):</label>
            <input type="text" id="sid-input" name="sid" placeholder="e.g. my_game" value="{{ sid }}" required autocomplete="off">
            
            <label>Text to send into Roblox:</label>
            <input type="text" name="text" placeholder="Type something..." required autocomplete="off">
            
            <button type="submit">Enqueue Text</button>
        </form>

        <div class="status-box">
            <div class="info">Current Active Signal (8-bit):</div>
            <div class="binary-display" id="binary-val">00000000</div>
            <div class="info">Remaining in Queue: <span id="queue-len" class="badge">0</span> steps</div>
            <div class="info" style="margin-top: 10px;">Last Roblox Connection: <span id="last-ping" style="color: #58a6ff;">Never</span></div>
        </div>
    </div>
</body>
</html>
"""

COLORED_TYPEWRITER_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Colored Typewriter - Build Logic Hub</title>
    <link href="https://fonts.googleapis.com/css2?family=Fira+Code:wght@500;700&family=Inter:wght@400;600&display=swap" rel="stylesheet">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: 'Inter', sans-serif; background-color: #0b0f19; color: #c9d1d9; padding: 20px; }
        .container { max-width: 850px; margin: 0 auto; background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 24px; box-shadow: 0 8px 24px rgba(0,0,0,0.5); }
        .back-link { display: inline-block; color: #58a6ff; text-decoration: none; font-size: 13px; margin-bottom: 12px; }
        h1 { font-size: 22px; color: #58a6ff; margin-bottom: 16px; text-align: center; }
        
        .controls-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-bottom: 20px; }
        label { display: block; font-size: 12px; color: #8b949e; margin-bottom: 4px; }
        input[type=text] { width: 100%; padding: 10px; background: #0d1117; border: 1px solid #30363d; border-radius: 6px; color: #f0f6fc; font-family: 'Fira Code', monospace; font-size: 14px; }
        
        .palette { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 15px; justify-content: center; }
        .color-btn { width: 32px; height: 32px; border-radius: 6px; border: 2px solid #30363d; cursor: pointer; transition: 0.1s; }
        .color-btn.active { border-color: #58a6ff; transform: scale(1.1); }
        
        .grid-16 { display: grid; grid-template-columns: repeat(16, 1fr); gap: 3px; background: #0d1117; padding: 10px; border-radius: 8px; border: 1px solid #30363d; margin-bottom: 15px; }
        .pixel { aspect-ratio: 1; background: #161b22; border: 1px solid #21262d; border-radius: 3px; cursor: pointer; }
        .pixel:hover { border-color: #58a6ff; }
        
        .btn-group { display: flex; gap: 10px; }
        button { flex: 1; padding: 12px; border-radius: 6px; border: none; font-weight: 600; background: #238636; color: #fff; cursor: pointer; font-size: 14px; }
        button:hover { background: #2ea043; }
        .btn-danger { background: #da3633; }
        .btn-danger:hover { background: #f85149; }
        
        .status-bar { margin-top: 15px; padding: 12px; background: #0d1117; border-radius: 6px; font-size: 13px; text-align: center; color: #8b949e; }
    </style>
    <script>
        let selectedColor = 'white';

        function setPaletteColor(name, hex, el) {
            selectedColor = name;
            document.querySelectorAll('.color-btn').forEach(b => b.classList.remove('active'));
            el.classList.add('active');
        }

        document.addEventListener("DOMContentLoaded", () => {
            const gridEl = document.getElementById('grid-16');
            for(let i=0; i<256; i++) {
                let p = document.createElement('div');
                p.className = 'pixel';
                p.dataset.index = i;
                p.style.backgroundColor = '#000000';
                p.dataset.colorName = 'black';
                p.addEventListener('click', () => {
                    p.style.backgroundColor = getHex(selectedColor);
                    p.dataset.colorName = selectedColor;
                });
                gridEl.appendChild(p);
            }
        });

        function getHex(name) {
            const map = {
                black: '#000000', white: '#ffffff', dim_white: '#cccccc', red: '#ff0000',
                green: '#00ff00', blue: '#0000ff', cyan: '#00ffff', magenta: '#ff00ff',
                yellow: '#ffff00', maroon: '#800000', grey: '#808080', lavender: '#e6e6fa',
                sky_blue: '#87ceeb', orange: '#ffa500', pink: '#ffc0cb', beige: '#f5f5dc'
            };
            return map[name] || '#000000';
        }

        async function sendGrid() {
            let sid = document.getElementById('sid-input').value.trim();
            if(!sid) { alert("Please enter SID"); return; }
            
            let pixels = [];
            document.querySelectorAll('.pixel').forEach(p => pixels.push(p.dataset.colorName));

            let res = await fetch('/api/colored-typewriter/send', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({sid: sid, pixels: pixels})
            });
            let data = await res.json();
            alert("Grid enqueued successfully! Queue length: " + data.queue_len);
        }

        async function triggerReset() {
            let sid = document.getElementById('sid-input').value.trim();
            if(!sid) { alert("Please enter SID"); return; }
            await fetch('/api/colored-typewriter/reset', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({sid: sid})
            });
            alert("Reset signal sent to Transmitter B (Bit 7 activated)!");
        }
    </script>
</head>
<body>
    <div class="container">
        <a href="/" class="back-link">← Back to Hub</a>
        <h1>🎨 Colored Typewriter Panel (16x16)</h1>
        
        <div class="controls-grid">
            <div>
                <label>Session ID (SID):</label>
                <input type="text" id="sid-input" placeholder="e.g. my_game" value="{{ sid }}" autocomplete="off">
            </div>
            <div>
                <label>Transmitter Mapping:</label>
                <div style="font-size:12px; color:#3fb950; padding-top:8px;">Transmitter A = Text | Transmitter B = Colors & Reset</div>
            </div>
        </div>

        <label>Select Paint Color:</label>
        <div class="palette">
            <div class="color-btn" style="background:#000000;" onclick="setPaletteColor('black', '#000000', this)"></div>
            <div class="color-btn active" style="background:#ffffff;" onclick="setPaletteColor('white', '#ffffff', this)"></div>
            <div class="color-btn" style="background:#ff0000;" onclick="setPaletteColor('red', '#ff0000', this)"></div>
            <div class="color-btn" style="background:#00ff00;" onclick="setPaletteColor('green', '#00ff00', this)"></div>
            <div class="color-btn" style="background:#0000ff;" onclick="setPaletteColor('blue', '#0000ff', this)"></div>
            <div class="color-btn" style="background:#00ffff;" onclick="setPaletteColor('cyan', '#00ffff', this)"></div>
            <div class="color-btn" style="background:#ff00ff;" onclick="setPaletteColor('magenta', '#ff00ff', this)"></div>
            <div class="color-btn" style="background:#ffff00;" onclick="setPaletteColor('yellow', '#ffff00', this)"></div>
            <div class="color-btn" style="background:#800000;" onclick="setPaletteColor('maroon', '#800000', this)"></div>
            <div class="color-btn" style="background:#808080;" onclick="setPaletteColor('grey', '#808080', this)"></div>
            <div class="color-btn" style="background:#e6e6fa;" onclick="setPaletteColor('lavender', '#e6e6fa', this)"></div>
            <div class="color-btn" style="background:#87ceeb;" onclick="setPaletteColor('sky_blue', '#87ceeb', this)"></div>
            <div class="color-btn" style="background:#ffa500;" onclick="setPaletteColor('orange', '#ffa500', this)"></div>
            <div class="color-btn" style="background:#ffc0cb;" onclick="setPaletteColor('pink', '#ffc0cb', this)"></div>
            <div class="color-btn" style="background:#f5f5dc;" onclick="setPaletteColor('beige', '#f5f5dc', this)"></div>
        </div>

        <div id="grid-16" class="grid-16"></div>

        <div class="btn-group">
            <button onclick="sendGrid()">Send Grid / Text to Roblox</button>
            <button class="btn-danger" onclick="triggerReset()">Trigger Reset (Bit 7)</button>
        </div>

        <div class="status-bar">
            Click pixels to paint, then click Send Grid. Transmitter B will transmit color bytes sequentially!
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
    <title>{{ title }}</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Inter', sans-serif; background-color: #0b0f19; color: #c9d1d9; padding: 50px; text-align: center; }
        .container { max-width: 500px; margin: 0 auto; background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 30px; }
        h1 { color: #58a6ff; font-size: 22px; margin-bottom: 12px; }
        a { color: #58a6ff; text-decoration: none; font-weight: 600; }
    </style>
</head>
<body>
    <div class="container">
        <h1>{{ title }}</h1>
        <p style="color: #8b949e; margin-bottom: 20px;">Coming up next in our step-by-step development plan!</p>
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
def colored_typewriter_page():
    sid = request.args.get('sid', '')
    return render_template_string(COLORED_TYPEWRITER_TEMPLATE, sid=sid)

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
            active_step, pause_step = text_to_8bit_steps(char)
            queues[target_sid].append(active_step)
            queues[target_sid].append(pause_step)

    return f"<script>window.location.href='/typewriter?sid={sid}';</script>"

@app.route('/api/colored-typewriter/send', methods=['POST'])
def api_send_colored_grid():
    data = request.get_json() or {}
    sid = data.get('sid', '').strip()
    pixels = data.get('pixels', [])
    
    if sid and pixels:
        target_b = sid + "B"
        for col_name in pixels:
            active_b = color_to_8bit(col_name, reset_active=False, clock=True)
            pause_b = color_to_8bit(col_name, reset_active=False, clock=False)
            queues[target_b].append(active_b)
            queues[target_b].append(pause_b)
            
    return jsonify({"status": "success", "queue_len": len(queues[sid + "B"])})

@app.route('/api/colored-typewriter/reset', methods=['POST'])
def api_reset_signal():
    data = request.get_json() or {}
    sid = data.get('sid', '').strip()
    if sid:
        target_b = sid + "B"
        # Push a reset frame where Bit 7 is active
        reset_frame = color_to_8bit("black", reset_active=True, clock=True)
        queues[target_b].appendleft(reset_frame)
    return jsonify({"status": "reset_sent"})

# --- ROBLOX HTTP TRANSMITTER API ENDPOINTS ---
@app.route('/api/typewriter', methods=['GET'])
def get_typewriter_signal():
    sid = request.headers.get('SID', '').strip()
    if not sid:
        return jsonify({"value": "00000000"})

    last_roblox_ping[sid] = datetime.now().strftime("%H:%M:%S")

    now = time.time()
    if now - last_pop_time[sid] >= INTERVAL_SEC:
        if queues[sid]:
            current_signal[sid] = queues[sid].popleft()
            last_pop_time[sid] = now
        else:
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
