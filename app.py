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

INTERVAL_SEC = 0.35  # Stable 350 ms interval per step (active -> pause)

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

# --- HTML TEMPLATE ---

TYPEWRITER_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Build Logic - Typewriter Hub</title>
    <link href="https://fonts.googleapis.com/css2?family=Fira+Code:wght@500;700&family=Inter:wght@400;600&display=swap" rel="stylesheet">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: 'Inter', sans-serif; background-color: #0b0f19; color: #c9d1d9; padding: 40px 20px; }
        .container { max-width: 600px; margin: 0 auto; background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 30px; box-shadow: 0 8px 24px rgba(0,0,0,0.5); }
        h1 { font-size: 22px; color: #58a6ff; margin-bottom: 6px; text-align: center; }
        p.subtitle { text-align: center; color: #8b949e; margin-bottom: 24px; font-size: 13px; }
        label { display: block; font-size: 13px; color: #8b949e; margin-bottom: 6px; }
        input[type=text] { width: 100%; padding: 12px; background: #0d1117; border: 1px solid #30363d; border-radius: 6px; color: #f0f6fc; font-family: 'Fira Code', monospace; font-size: 15px; margin-bottom: 16px; }
        input[type=text]:focus { border-color: #58a6ff; outline: none; }
        button { width: 100%; padding: 12px; border-radius: 6px; border: none; font-weight: 600; background: #238636; color: #fff; cursor: pointer; font-size: 15px; }
        button:hover { background: #2ea043; }
        .status-box { margin-top: 24px; padding: 16px; background: #0d1117; border: 1px solid #21262d; border-radius: 8px; text-align: center; }
        .binary-display { font-family: 'Fira Code', monospace; font-size: 28px; color: #3fb950; letter-spacing: 4px; margin: 10px 0; }
        .info { font-size: 13px; color: #8b949e; margin-top: 6px; }
        .badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 12px; font-weight: 600; background: #21262d; color: #f2cc60; border: 1px solid #30363d; }
        .setup-guide { margin-top: 24px; border-top: 1px solid #30363d; padding-top: 16px; font-size: 13px; color: #8b949e; line-height: 1.5; }
        .setup-guide code { font-family: 'Fira Code', monospace; background: #0d1117; padding: 2px 6px; border-radius: 4px; color: #3fb950; border: 1px solid #30363d; }
    </style>
    <script>
        setInterval(async () => {
            let sid = document.getElementById('sid-input').value.trim();
            if(!sid) return;
            try {
                let res = await fetch('/api/typewriter/status?sid=' + encodeURIComponent(sid));
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
        <h1>⌨️ Build Logic Typewriter</h1>
        <p class="subtitle">Direct web controller for Roblox HTTP Transmitters</p>
        
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

        <div class="setup-guide">
            <b>Roblox Transmitter Setup:</b><br>
            • Endpoint URL: <code>{{ base_url }}/api/typewriter</code><br>
            • Header SID: <code>MY_SESSION</code> (Enter matching SID above)
        </div>
    </div>
</body>
</html>
"""

# --- ROUTES ---

@app.route('/')
def main_hub():
    base_url = request.host_url.rstrip('/')
    sid = request.args.get('sid', '')
    return render_template_string(TYPEWRITER_TEMPLATE, base_url=base_url, sid=sid)

@app.route('/typewriter/send', methods=['POST'])
def send_text():
    sid = request.form.get('sid', '').strip()
    text = request.form.get('text', '')
    
    if sid and text:
        # Clear previous queue on new send so it overwrites immediately
        queues[sid].clear()
        for char in text:
            active_step, pause_step = text_to_8bit_steps(char)
            queues[sid].append(active_step)
            queues[sid].append(pause_step)

    return f"<script>window.location.href='/?sid={sid}';</script>"

# --- ROBLOX HTTP TRANSMITTER API ENDPOINT ---
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
