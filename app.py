import collections
import time
from datetime import datetime
from flask import Flask, render_template_string, request, jsonify

app = Flask(__name__)

# Unified storage per base session ID:
# queues[base_sid] = deque of tuples: (byte_A, byte_B)
queues = collections.defaultdict(collections.deque)
current_signals = collections.defaultdict(lambda: {"A": "00000000", "B": "00000000"})
last_pop_time = collections.defaultdict(float)
last_roblox_ping = collections.defaultdict(lambda: "Never")

INTERVAL_SEC = 0.20  # Faster 200 ms interval per step

# --- CUSTOM CHARACTER & SYMBOL MAPPING ---
def get_char_mapping(char):
    if 'a' <= char <= 'z':
        idx = ord(char) - ord('a') + 1
        return format(idx, '06b'), False
    elif 'A' <= char <= 'Z':
        idx = ord(char.lower()) - ord('a') + 1
        return format(idx, '06b'), True
    
    num_map = {
        '1': ('011011', False), '!': ('011011', True),
        '2': ('011100', False), '@': ('011100', True),
        '3': ('011101', False), '#': ('011101', True),
        '4': ('011110', False), '$': ('011110', True),
        '5': ('011111', False), '%': ('011111', True),
        '6': ('100000', False), '?': ('100000', True),
        '7': ('100001', False), '&': ('100001', True),
        '8': ('100010', False), '*': ('100010', True),
        '9': ('100011', True),  '(': ('100011', True),
        '0': ('100100', False), ')': ('100100', True),
    }
    if char in num_map:
        return num_map[char]

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
    bits_6, is_shift = get_char_mapping(char)
    shift_bit = "1" if is_shift else "0"
    clock_active = "1"
    
    active_byte = (bits_6 + shift_bit + clock_active)[::-1]
    pause_byte = "00000000"
    return active_byte, pause_byte

# --- COLOR PALETTE MAPPING ---
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

def color_to_8bit(color_name, reset_active=False):
    c_bits = COLOR_MAP.get(color_name, "000000")
    r_bit = "1" if reset_active else "0"
    unused_bit = "0"
    return (c_bits + r_bit + unused_bit)[::-1]

def get_reset_steps():
    space_active, space_pause = text_to_8bit_steps(' ')
    reset_on = color_to_8bit("black", reset_active=True)
    reset_off = color_to_8bit("black", reset_active=False)
    return [
        (space_active, reset_on),
        (space_pause, reset_on),
        (space_active, reset_off),
        (space_pause, reset_off)
    ]

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
        .card { background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 20px; box-shadow: 0 8px 24px rgba(0,0,0,0.5); }
        .card h3 { color: #58a6ff; font-size: 18px; margin-bottom: 8px; }
        .card p { color: #8b949e; font-size: 13px; margin-bottom: 14px; line-height: 1.4; }
        .btn { display: inline-block; padding: 10px 16px; border-radius: 6px; background: #238636; color: #fff; font-weight: 600; text-decoration: none; font-size: 14px; text-align: center; width: 100%; }
        .btn:hover { background: #2ea043; }
        .btn-secondary { background: #21262d; border: 1px solid #30363d; color: #c9d1d9; }
        .instructions { background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 24px; }
        .instructions h2 { font-size: 18px; color: #f0f6fc; margin-bottom: 12px; }
        .instructions ol { padding-left: 20px; color: #8b949e; font-size: 14px; line-height: 1.6; }
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
                <p>Monochrome text transmission with full symbol support.</p>
                <a href="/typewriter" class="btn">Open Typewriter</a>
            </div>
            <div class="card">
                <h3>🎨 Colored Typewriter</h3>
                <p>Synchronized dual-transmitter text & color panel with grid painting and auto-reset.</p>
                <a href="/colored-typewriter" class="btn">Open Panel</a>
            </div>
            <div class="card">
                <h3>⚡ Upgraded Typewriter</h3>
                <p>Advanced real-time pixel updating with coordinate mapping.</p>
                <a href="/upgraded-typewriter" class="btn btn-secondary">Coming Soon</a>
            </div>
            <div class="card">
                <h3>🎮 Game Engine</h3>
                <p>Two-way communication, button inputs, and minigames hub.</p>
                <a href="/game-engine" class="btn btn-secondary">Coming Soon</a>
            </div>
        </div>
        <div class="instructions">
            <h2>⚙️ Roblox Setup</h2>
            <ol>
                <li>URL Endpoint for transmitters: <br><code>{{ base_url }}/api/typewriter</code></li>
                <li>Transmitter A Header: <code>SID: MY_SESSION_A</code> (Text + Clock)</li>
                <li>Transmitter B Header: <code>SID: MY_SESSION_B</code> (Color + Reset)</li>
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
    <title>Typewriter - Build Logic Hub</title>
    <link href="https://fonts.googleapis.com/css2?family=Fira+Code:wght@500;700&family=Inter:wght@400;600&display=swap" rel="stylesheet">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: 'Inter', sans-serif; background-color: #0b0f19; color: #c9d1d9; padding: 30px; }
        .container { max-width: 600px; margin: 0 auto; background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 24px; }
        .back-link { display: inline-block; color: #58a6ff; text-decoration: none; font-size: 13px; margin-bottom: 16px; }
        h1 { font-size: 20px; color: #58a6ff; margin-bottom: 20px; text-align: center; }
        label { display: block; font-size: 13px; color: #8b949e; margin-bottom: 6px; }
        input[type=text] { width: 100%; padding: 12px; background: #0d1117; border: 1px solid #30363d; border-radius: 6px; color: #f0f6fc; font-family: 'Fira Code', monospace; font-size: 15px; margin-bottom: 16px; }
        button { width: 100%; padding: 12px; border-radius: 6px; border: none; font-weight: 600; background: #238636; color: #fff; cursor: pointer; font-size: 15px; }
        button:hover { background: #2ea043; }
        .status-box { margin-top: 20px; padding: 16px; background: #0d1117; border: 1px solid #21262d; border-radius: 8px; text-align: center; }
        .binary-display { font-family: 'Fira Code', monospace; font-size: 28px; color: #3fb950; letter-spacing: 4px; margin: 10px 0; }
        .info { font-size: 13px; color: #8b949e; margin-top: 6px; }
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
        }, 200);
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
            <div class="info">Transmitter A Signal (8-bit):</div>
            <div class="binary-display" id="binary-val">00000000</div>
            <div class="info">Remaining Steps: <span id="queue-len">0</span></div>
            <div class="info" style="margin-top: 8px;">Last Roblox Ping: <span id="last-ping" style="color:#58a6ff;">Never</span></div>
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
        
        .section-card { background: #0d1117; border: 1px solid #21262d; border-radius: 8px; padding: 16px; margin-bottom: 20px; }
        .section-title { font-size: 14px; color: #f0f6fc; font-weight: 600; margin-bottom: 10px; }
        
        label { display: block; font-size: 12px; color: #8b949e; margin-bottom: 4px; }
        input[type=text] { width: 100%; padding: 10px; background: #161b22; border: 1px solid #30363d; border-radius: 6px; color: #f0f6fc; font-family: 'Fira Code', monospace; font-size: 14px; margin-bottom: 10px; }
        
        .palette { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }
        .color-btn { width: 30px; height: 30px; border-radius: 6px; border: 2px solid #30363d; cursor: pointer; }
        .color-btn.active { border-color: #58a6ff; transform: scale(1.1); }
        
        .grid-16 { display: grid; grid-template-columns: repeat(16, 1fr); gap: 3px; background: #0d1117; padding: 10px; border-radius: 8px; border: 1px solid #30363d; margin-bottom: 15px; }
        .pixel { aspect-ratio: 1; background: #161b22; border: 1px solid #21262d; border-radius: 3px; cursor: pointer; }
        .pixel:hover { border-color: #58a6ff; }
        
        .toggle-group { display: flex; align-items: center; gap: 10px; margin-bottom: 15px; font-size: 13px; color: #c9d1d9; cursor: pointer; }
        .toggle-group input { width: 18px; height: 18px; accent-color: #238636; cursor: pointer; }

        button { width: 100%; padding: 14px; border-radius: 6px; border: none; font-weight: 600; background: #238636; color: #fff; cursor: pointer; font-size: 15px; }
        button:hover { background: #2ea043; }
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

        async function sendAllToRoblox() {
            let sid = document.getElementById('sid-input').value.trim();
            let text = document.getElementById('text-input').value;
            let autoReset = document.getElementById('auto-reset-toggle').checked;
            
            if(!sid) { alert("Please enter Session ID (SID)"); return; }

            let pixels = [];
            document.querySelectorAll('.pixel').forEach(p => pixels.push(p.dataset.colorName));

            let res = await fetch('/api/colored-typewriter/send-all', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    sid: sid,
                    text: text,
                    color: selectedColor,
                    pixels: pixels,
                    auto_reset: autoReset
                })
            });
            let data = await res.json();
            alert("Successfully enqueued to Roblox! Queue length: " + data.queue_len + " steps.");
        }
    </script>
</head>
<body>
    <div class="container">
        <a href="/" class="back-link">← Back to Hub</a>
        <h1>🎨 Colored Typewriter Panel</h1>
        
        <div style="margin-bottom: 15px;">
            <label>Session ID (SID):</label>
            <input type="text" id="sid-input" placeholder="e.g. my_game" value="{{ sid }}" autocomplete="off">
        </div>

        <div class="section-card">
            <div class="section-title">1. Choose Active Color (for Text Tool)</div>
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
        </div>

        <div class="section-card">
            <div class="section-title">2. Text Tool (Transmits Text + Selected Color)</div>
            <input type="text" id="text-input" placeholder="Type text to display..." autocomplete="off">
        </div>

        <div class="section-card">
            <div class="section-title">3. 16x16 Grid Paint Tool</div>
            <div id="grid-16" class="grid-16"></div>
        </div>

        <label class="toggle-group">
            <input type="checkbox" id="auto-reset-toggle" checked>
            <span>Auto-Reset on Send (Automatically pulse Bit 7 on Transmitter B before loading new data)</span>
        </label>

        <button onclick="sendAllToRoblox()">🚀 Send All to Roblox (Text & Grid)</button>
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
        <p style="color: #8b949e; margin-bottom: 20px;">Coming up next in our step-by-step plan!</p>
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
        base_sid = sid[:-1] if (sid.endswith('A') or sid.endswith('B')) else sid
        steps = []
        for char in text:
            active_step, pause_step = text_to_8bit_steps(char)
            steps.append((active_step, "00000000"))
            steps.append((pause_step, "00000000"))
        queues[base_sid].extend(steps)

    return f"<script>window.location.href='/typewriter?sid={sid}';</script>"

@app.route('/api/colored-typewriter/send-all', methods=['POST'])
def api_send_all():
    data = request.get_json() or {}
    sid = data.get('sid', '').strip()
    text = data.get('text', '')
    color_name = data.get('color', 'white')
    pixels = data.get('pixels', [])
    auto_reset = data.get('auto_reset', False)

    if sid:
        base_sid = sid[:-1] if (sid.endswith('A') or sid.endswith('B')) else sid
        steps = []

        # 1. Optional Auto-Reset at the beginning
        if auto_reset:
            steps.extend(get_reset_steps())

        # 2. Text Steps (if text is provided)
        if text:
            color_byte = color_to_8bit(color_name, reset_active=False)
            for char in text:
                active_a, pause_a = text_to_8bit_steps(char)
                steps.append((active_a, color_byte))
                steps.append((pause_a, color_byte))

        # 3. Grid Steps (all 256 pixels)
        if pixels:
            space_active, space_pause = text_to_8bit_steps(' ')
            for col_name in pixels:
                color_byte = color_to_8bit(col_name, reset_active=False)
                steps.append((space_active, color_byte))
                steps.append((space_pause, color_byte))

        queues[base_sid].extend(steps)
        return jsonify({"status": "success", "queue_len": len(queues[base_sid])})

    return jsonify({"status": "error", "message": "Invalid SID"}), 400

# --- UNIFIED ROBLOX HTTP TRANSMITTER ENDPOINT ---
@app.route('/api/typewriter', methods=['GET'])
def get_typewriter_signal():
    header_sid = request.headers.get('SID', '').strip()
    if not header_sid:
        return jsonify({"value": "00000000"})

    # Determine base SID and channel (A or B)
    if header_sid.endswith('A') or header_sid.endswith('B'):
        base_sid = header_sid[:-1]
        channel = header_sid[-1]
    else:
        base_sid = header_sid
        channel = 'A'

    last_roblox_ping[base_sid] = datetime.now().strftime("%H:%M:%S")

    now = time.time()
    # Shared interval check: advances BOTH A and B simultaneously from the same queue step
    if now - last_pop_time[base_sid] >= INTERVAL_SEC:
        if queues[base_sid]:
            byte_a, byte_b = queues[base_sid].popleft()
            current_signals[base_sid]["A"] = byte_a
            current_signals[base_sid]["B"] = byte_b
            last_pop_time[base_sid] = now
        else:
            current_signals[base_sid]["A"] = "00000000"
            current_signals[base_sid]["B"] = "00000000"

    return jsonify({"value": current_signals[base_sid][channel]})

@app.route('/api/typewriter/status', methods=['GET'])
def typewriter_status():
    sid = request.args.get('sid', '').strip()
    if sid.endswith('A') or sid.endswith('B'):
        base_sid = sid[:-1]
        channel = sid[-1]
    else:
        base_sid = sid
        channel = 'A'

    return jsonify({
        "current_signal": current_signals[base_sid][channel],
        "queue_len": len(queues[base_sid]),
        "last_ping": last_roblox_ping[base_sid]
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
