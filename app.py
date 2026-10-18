from flask import Flask, render_template, jsonify
import threading
import time
import random
import os

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

try:
    import serial
    import pynmea2
    import RPi.GPIO as GPIO
    HARDWARE_AVAILABLE = True
except ImportError:
    HARDWARE_AVAILABLE = False

app = Flask(__name__)

gps_data = {
    "latitude": 14.5995, "longitude": 120.9842, "altitude": 0,
    "satellites": 0, "speed": 0, "status": "Initializing...",
    "buzzer": False, "led": False, "oled_message": "Booting...",
    "history": []
}

def log_history():
    # Function para i-save ang history para pareho sa Mock at Hardware
    gps_data["history"].append({
        "time": time.strftime("%H:%M:%S"),
        "lat": round(gps_data["latitude"], 6),
        "lon": round(gps_data["longitude"], 6),
        "alt": round(gps_data["altitude"], 1)
    })
    if len(gps_data["history"]) > 50:
        gps_data["history"].pop(0)

def read_gps():
    if HARDWARE_AVAILABLE:
        try:
            ser = serial.Serial('/dev/serial0', 9600, timeout=1)
            print("[OK] GPS Connected.")
            while True:
                if ser.in_waiting > 0:
                    line = ser.readline().decode('utf-8', errors='ignore').strip()
                    if line.startswith('$GPGGA') or line.startswith('$GPRMC'):
                        try:
                            msg = pynmea2.parse(line)
                            if hasattr(msg, 'latitude') and msg.latitude != 0.0:
                                gps_data["latitude"] = msg.latitude
                                gps_data["longitude"] = msg.longitude
                                gps_data["status"] = "GPS Active"
                                log_history() # <--- ITO ANG FIX PARA GUMANA ANG LOGS SA HARDWARE
                            if hasattr(msg, 'altitude') and msg.altitude:
                                gps_data["altitude"] = float(msg.altitude)
                            if hasattr(msg, 'num_sats') and msg.num_sats:
                                gps_data["satellites"] = int(msg.num_sats)
                        except:
                            pass
        except Exception as e:
            print(f"[ERROR] {e}. Falling back to Mock.")
            run_mock_gps()
    else:
        run_mock_gps()

def run_mock_gps():
    print("[MOCK] Generating simulated GPS data...")
    gps_data["status"] = "Mock Mode (Simulated)"
    while True:
        gps_data["latitude"] += random.uniform(-0.0002, 0.0002)
        gps_data["longitude"] += random.uniform(-0.0002, 0.0002)
        gps_data["altitude"] = random.uniform(10, 50)
        gps_data["satellites"] = random.randint(4, 12)
        gps_data["speed"] = random.uniform(0, 60) 
        gps_data["led"] = True
        gps_data["oled_message"] = "GPS ACTIVE"
        
        log_history() # I-save sa logs
        time.sleep(2)

thread = threading.Thread(target=read_gps, daemon=True)
thread.start()

# --- ROUTES ---
@app.route('/')
def landing(): return render_template('landing.html')

@app.route('/how-it-works')
def how_it_works(): return render_template('how_it_works.html')

@app.route('/hardware')
def hardware(): return render_template('hardware.html')

@app.route('/logs')
def logs(): return render_template('logs.html')

@app.route('/dashboard')
def dashboard(): return render_template('dashboard.html')

@app.route('/api/gps')
def get_gps(): return jsonify(gps_data)

@app.route('/api/system')
def get_system():
    cpu = psutil.cpu_percent() if PSUTIL_AVAILABLE else random.uniform(10, 30)
    temp = random.uniform(40.0, 55.0)
    try:
        with open('/sys/class/thermal/thermal_zone0/temp', 'r') as f:
            temp = float(f.read()) / 1000.0
    except:
        pass
    return jsonify({"cpu": round(cpu, 1), "temp": round(temp, 1)})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
