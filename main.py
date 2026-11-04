import collections
import time
from flask import Flask, render_template_string, request, jsonify

app = Flask(__name__)

# Fronta pro každý Session ID (SID) -> deque storing (char, binary_8bit)
queues = collections.defaultdict(collections.deque)
current_signal = collections.defaultdict(lambda: "00000000")
last_pop_time = collections.defaultdict(float)

INTERVAL_SEC = 0.35  # 350 ms interval mezi znaky

# Mapování základních znaků na 6-bitový kód (0 až 63)
# 1..26 = a-z, 27..36 = 0-9, 0 = mezera/neplatný
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
    Vytvoří 8-bitový řetězec:
    - Bit 1-6: Kód symbolu
    - Bit 7: Shift (1 pro velká písmena)
    - Bit 8: Clock (vždy 1 při aktivním vysílání znaku)
    """
    is_shift = "1" if char.isupper() else "0"
    clock_bit = "1"
    
    code_6bit = get_char_6bit(char)
    bits_6 = format(code_6bit, '06b')
    
    # Sestavení: 6-bit kód + Shift bit + Clock bit
    return bits_6 + is_shift + clock_bit

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="cs">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Level 1 - Typewriter</title>
    <link href="https://fonts.googleapis.com/css2?family=Fira+Code:wght@500;700&family=Inter:wght@400;600&display=swap" rel="stylesheet">
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: 'Inter', sans-serif; background-color: #0b0f19; color: #c9d1d9; padding: 30px; }
        .container { max-width: 600px; margin: 0 auto; background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 24px; box-shadow: 0 8px 24px rgba(0,0,0,0.5); }
        h1 { font-size: 20px; color: #58a6ff; margin-bottom: 20px; text-align: center; }
        label { display: block; font-size: 13px; color: #8b949e; margin-bottom: 6px; }
        input[type=text] { width: 100%; padding: 12px; background: #0d1117; border: 1px solid #30363d; border-radius: 6px; color: #f0f6fc; font-family: 'Fira Code', monospace; font-size: 15px; margin-bottom: 16px; }
        input[type=text]:focus { border-color: #58a6ff; outline: none; }
        button { width: 100%; padding: 12px; border-radius: 6px; border: none; font-weight: 600; background: #238636; color: #fff; cursor: pointer; font-size: 15px; }
        button:hover { background: #2ea043; }
        .status-box { margin-top: 20px; padding: 16px; background: #0d1117; border: 1px solid #21262d; border-radius: 8px; text-align: center; }
        .binary-display { font-family: 'Fira Code', monospace; font-size: 28px; color: #3fb950; letter-spacing: 4px; margin: 10px 0; }
        .info { font-size: 13px; color: #8b949e; }
    </style>
    <script>
        setInterval(async () => {
            let sid = document.getElementById('sid-input').value;
            if(!sid) return;
            try {
                let res = await fetch('/api/typewriter/status?sid=' + encodeURIComponent(sid + 'A'));
                let data = await res.json();
                document.getElementById('binary-val').innerText = data.current_signal;
                document.getElementById('queue-len').innerText = data.queue_len;
            } catch(e) {}
        }, 200);
    </script>
</head>
<body>
    <div class="container">
        <h1>⌨️ Level 1: Typewriter Panel</h1>
        <form method="POST" action="/typewriter/send">
            <label>Session ID (SID):</label>
            <input type="text" id="sid-input" name="sid" placeholder="např. MOJE_SESSION" value="{{ sid }}" required autocomplete="off">
            
            <label>Text k odeslání do Robloxu:</label>
            <input type="text" name="text" placeholder="Napiš text..." required autocomplete="off">
            
            <button type="submit">Odeslat do fronty</button>
        </form>

        <div class="status-box">
            <div class="info">Aktivní signál na vysílači (8 bitů):</div>
            <div class="binary-display" id="binary-val">00000000</div>
            <div class="info">Zbývá ve frontě: <span id="queue-len">0</span> znaků</div>
        </div>
    </div>
</body>
</html>
"""

@app.route('/typewriter')
def typewriter_page():
    sid = request.args.get('sid', '')
    return render_template_string(HTML_TEMPLATE, sid=sid)

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

# --- HTTP ENDPOINT PRO ROBLOX TRANSMITTER (GET) ---
@app.route('/api/typewriter', methods=['GET'])
def get_typewriter_signal():
    # Roblox posílá SID v headeru, např: SID: MOJE_SESSIONA
    sid = request.headers.get('SID', '').strip()
    
    if not sid:
        return jsonify({"value": "00000000"})

    now = time.time()
    # Zkontrolovat, zda uplynul interval ~350 ms od posledního posunu znaku
    if now - last_pop_time[sid] >= INTERVAL_SEC:
        if queues[sid]:
            current_signal[sid] = queues[sid].popleft()
            last_pop_time[sid] = now
        else:
            # Pokud je fronta prázdná, clock (8. bit) je 0
            current_signal[sid] = "00000000"

    return jsonify({"value": current_signal[sid]})

@app.route('/api/typewriter/status', methods=['GET'])
def typewriter_status():
    sid = request.args.get('sid', '').strip()
    return jsonify({
        "current_signal": current_signal[sid],
        "queue_len": len(queues[sid])
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)