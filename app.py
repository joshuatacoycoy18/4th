from flask import Flask, render_template, jsonify
import threading
import time
import random
import os

# Import System Libraries
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

# Import Hardware & GPS Libraries
try:
    import serial
    import pynmea2
    import RPi.GPIO as GPIO
    import board
    import busio
    import adafruit_ssd1306
    from PIL import Image, ImageDraw, ImageFont
    HARDWARE_AVAILABLE = True
except ImportError as e:
    HARDWARE_AVAILABLE = False
    print(f"[WARN] Hardware libraries not found: {e}")

app = Flask(__name__)

# ============================================
# HARDWARE SETUP (Ibinalik natin ito)
# ============================================
LED_PIN = 18
BUZZER_PIN = 23
oled = None

if HARDWARE_AVAILABLE:
    try:
        # Setup GPIO
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup(LED_PIN, GPIO.OUT)
        GPIO.setup(BUZZER_PIN, GPIO.OUT)
        
        # Setup OLED
        i2c = busio.I2C(board.SCL, board.SDA)
        oled = adafruit_ssd1306.SSD1306_I2C(128, 64, i2c, addr=0x3C)
        oled.fill(0)
        oled.show()
        print("[OK] Hardware initialized: LED, Buzzer, OLED")
    except Exception as e:
        print(f"[ERROR] Hardware init failed: {e}")
        oled = None

def update_hardware():
    """Function para i-update ang LED, Buzzer, at OLED base sa satellite count."""
    if not HARDWARE_AVAILABLE:
        return
        
    try:
        # Logic: Kapag 4 pataas ang satellites, LED ON, Buzzer OFF. Kapag 3 pababa, Alert!
        if gps_data["satellites"] >= 4:
            GPIO.output(LED_PIN, True)
            GPIO.output(BUZZER_PIN, False)
            gps_data["led"] = True
            gps_data["buzzer"] = False
            gps_data["oled_message"] = "GPS ACTIVE"
            
            if oled:
                oled.fill(0)
                img = Image.new("1", (oled.width, oled.height))
                draw = ImageDraw.Draw(img)
                font = ImageFont.load_default()
                draw.text((0, 0), "STATUS: ACTIVE", font=font, fill=255)
                draw.text((0, 16), f"SATS: {gps_data['satellites']}/12", font=font, fill=255)
                draw.text((0, 32), f"LAT: {gps_data['latitude']:.5f}", font=font, fill=255)
                draw.text((0, 48), f"LON: {gps_data['longitude']:.5f}", font=font, fill=255)
                oled.image(img)
                oled.show()
        else:
            GPIO.output(LED_PIN, False)
            GPIO.output(BUZZER_PIN, True)
            gps_data["led"] = False
            gps_data["buzzer"] = True
            gps_data["oled_message"] = "WEAK SIGNAL!"
            
            if oled:
                oled.fill(0)
                img = Image.new("1", (oled.width, oled.height))
                draw = ImageDraw.Draw(img)
                font = ImageFont.load_default()
                draw.text((0, 0), "! WARNING !", font=font, fill=255)
                draw.text((0, 16), "WEAK SIGNAL", font=font, fill=255)
                draw.text((0, 32), f"SATS: {gps_data['satellites']}/12", font=font, fill=255)
                oled.image(img)
                oled.show()
    except Exception as e:
        print(f"[ERROR] Hardware update failed: {e}")

# ============================================
# GLOBAL STATE
# ============================================
gps_data = {
    "latitude": 14.5995, "longitude": 120.9842, "altitude": 0,
    "satellites": 0, "speed": 0, "status": "Initializing...",
    "buzzer": False, "led": False, "oled_message": "Booting...",
    "history": []
}

def log_history():
    gps_data["history"].append({
        "time": time.strftime("%H:%M:%S"),
        "lat": round(gps_data["latitude"], 6),
        "lon": round(gps_data["longitude"], 6),
        "alt": round(gps_data["altitude"], 1)
    })
    if len(gps_data["history"]) > 50:
        gps_data["history"].pop(0)

# ============================================
# REAL GPS READER
# ============================================
def read_gps():
    if HARDWARE_AVAILABLE:
        try:
            ser = serial.Serial('/dev/serial0', 9600, timeout=1)
            print("[OK] GPS Connected on /dev/serial0.")
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
                                log_history()
                            if hasattr(msg, 'altitude') and msg.altitude:
                                gps_data["altitude"] = float(msg.altitude)
                            if hasattr(msg, 'num_sats') and msg.num_sats:
                                gps_data["satellites"] = int(msg.num_sats)
                            
                            # Tawagin ang hardware update function
                            update_hardware()
                            
                        except:
                            pass
        except Exception as e:
            print(f"[ERROR] GPS failed: {e}. Falling back to Mock.")
            run_mock_gps()
    else:
        run_mock_gps()

# ============================================
# MOCK GPS READER (Fallback)
# ============================================
def run_mock_gps():
    print("[MOCK] Generating simulated GPS data...")
    gps_data["status"] = "Mock Mode (Simulated)"
    while True:
        gps_data["latitude"] += random.uniform(-0.0002, 0.0002)
        gps_data["longitude"] += random.uniform(-0.0002, 0.0002)
        gps_data["altitude"] = random.uniform(10, 50)
        gps_data["satellites"] = random.randint(4, 12)
        gps_data["speed"] = random.uniform(0, 60) 
        
        log_history()
        update_hardware() # Tawagin din dito para gumana kahit Mock Mode
        
        time.sleep(2)

thread = threading.Thread(target=read_gps, daemon=True)
thread.start()

# ============================================
# FLASK ROUTES
# ============================================
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

# ============================================
# MAIN
# ============================================
if __name__ == '__main__':
    try:
        app.run(host='0.0.0.0', port=5000, debug=False)
    finally:
        # Siguraduhing papatayin ang LED at Buzzer kapag nag-stop ang app
        if HARDWARE_AVAILABLE:
            GPIO.cleanup()
            if oled:
                oled.fill(0)
                oled.show()
        print("Cleanup done.")
