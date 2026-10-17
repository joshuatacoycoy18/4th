"""
Sound & Raindrop Monitor - OFFLINE version (USB cable, no internet needed)

The Raspberry Pi Pico reads the sensors and sends each reading through the
USB cable to the computer running this program (Windows PC or Raspberry Pi).
This program reads the USB port, serves a web page, and tells the Pico when
to sound the buzzer.

Nothing is made up: until the Pico sends data, the page says
"Waiting for sensor data".

Run:   python app.py
Open:  http://localhost:5000            (on the same computer)
       http://<IP-shown-at-startup>:5000 (from another device on the same
                                           Wi-Fi / hotspot)
       landing page = /     dashboard = /dashboard

Important: close Thonny first - only one program can use the USB port.

Optional environment variables:
  SERIAL_PORT  e.g. COM5 or /dev/ttyACM0   (default: auto-detect)
  HOST         default 0.0.0.0  (use 127.0.0.1 to allow only this computer)
  PORT         default 5000
"""
import json
import os
import socket
import threading
import time
from collections import deque

import serial
from serial.tools import list_ports
from flask import Flask, jsonify, render_template, request

# ---------------- Settings ----------------
SERIAL_PORT = os.environ.get("SERIAL_PORT")      # None = auto-detect
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "5000"))
BAUD_RATE = 115200
HISTORY_SIZE = 120            # readings kept for the charts
SOUND_ALERT_PERCENT = 70      # buzzer beeps above this sound level
RAIN_THRESHOLD_PERCENT = 30   # wetness at/above this = "raining"
OFFLINE_AFTER_SECONDS = 5     # no reading for this long = sensor offline

# ---------------- Shared state ----------------
history = deque(maxlen=HISTORY_SIZE)
state = {"buzzer_enabled": True, "buzzer_on": False, "last_seen": 0.0}
lock = threading.Lock()

app = Flask(__name__)


def clamp_percent(value):
    return max(0.0, min(100.0, float(value)))


def get_local_ip():
    """Best-effort local IP (works without internet; no data is sent)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))   # UDP "connect" sends nothing
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def find_pico_port():
    """Return the USB serial port of the Pico (or None)."""
    if SERIAL_PORT:
        return SERIAL_PORT
    ports = list(list_ports.comports())
    for p in ports:                       # 0x2E8A = Raspberry Pi vendor ID
        if p.vid == 0x2E8A:
            return p.device
    for p in ports:
        text = (p.description or "") + " " + (p.manufacturer or "")
        if any(k in text for k in ("MicroPython", "Pico", "USB Serial Device")):
            return p.device
    return None


def handle_reading(sound, wetness):
    """Store a reading and return True if the buzzer should be on."""
    raining = wetness >= RAIN_THRESHOLD_PERCENT
    alert = raining or sound >= SOUND_ALERT_PERCENT
    with lock:
        state["last_seen"] = time.time()
        state["buzzer_on"] = alert and state["buzzer_enabled"]
        history.append({
            "time": time.strftime("%H:%M:%S"),
            "sound": sound,
            "wetness": wetness,
            "raining": raining,
        })
        return state["buzzer_on"]


def serial_loop():
    """Background thread: read lines from the Pico, answer with B1 / B0."""
    last_msg = None

    def say(msg):
        nonlocal last_msg
        if msg != last_msg:          # only print when something changes
            print(msg, flush=True)
            last_msg = msg

    while True:
        port = find_pico_port()
        if not port:
            say("Pico not found. Plug it in with the USB cable (and close Thonny).")
            time.sleep(2)
            continue
        try:
            with serial.Serial(port, BAUD_RATE, timeout=1, write_timeout=1) as ser:
                ser.reset_input_buffer()      # drop stale data from before
                say(f"Connected to Pico on {port}")
                while True:
                    raw = ser.readline()
                    if not raw:
                        continue
                    try:
                        data = json.loads(raw.decode("utf-8", "ignore").strip())
                        sound = round(clamp_percent(data["sound"]), 1)
                        wetness = round(clamp_percent(data["wetness"]), 1)
                    except (ValueError, KeyError, TypeError):
                        continue     # ignore any other text the Pico prints
                    buzzer_on = handle_reading(sound, wetness)
                    ser.write(b"B1\n" if buzzer_on else b"B0\n")
        except PermissionError:
            say(f"Permission denied on {port}. On Raspberry Pi run: "
                "sudo usermod -aG dialout $USER   then reboot. "
                "On Windows, close Thonny. Retrying...")
            time.sleep(2)
        except (serial.SerialException, OSError) as err:
            say(f"Cannot use {port}: {err}. Is Thonny still open? Retrying...")
            time.sleep(2)


@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")


@app.route("/api/data")
def api_data():
    with lock:
        connected = (time.time() - state["last_seen"]) < OFFLINE_AFTER_SECONDS
        return jsonify({
            "history": list(history),
            "connected": connected,
            "buzzer_enabled": state["buzzer_enabled"],
            "buzzer_on": state["buzzer_on"] and connected,
            "sound_alert": SOUND_ALERT_PERCENT,
            "rain_threshold": RAIN_THRESHOLD_PERCENT,
        })


@app.route("/api/buzzer", methods=["POST"])
def api_buzzer():
    with lock:
        state["buzzer_enabled"] = bool((request.get_json(silent=True) or {}).get("enabled", True))
        if not state["buzzer_enabled"]:
            state["buzzer_on"] = False
    return jsonify(ok=True, buzzer_enabled=state["buzzer_enabled"])


if __name__ == "__main__":
    threading.Thread(target=serial_loop, daemon=True).start()
    print(f"\nDashboard on this computer:  http://localhost:{PORT}/dashboard")
    if HOST == "0.0.0.0":
        print(f"From another device (same Wi-Fi/hotspot): "
              f"http://{get_local_ip()}:{PORT}/dashboard\n", flush=True)
    # debug is off on purpose: the reloader would start the serial thread twice
    app.run(host=HOST, port=PORT, debug=False, threaded=True)