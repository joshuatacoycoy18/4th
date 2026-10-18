from flask import Flask, render_template, jsonify
import threading
import time
import random

# ============================================
# GPS LIBRARIES
# ============================================
try:
    import serial
    import pynmea2
    GPS_AVAILABLE = True
except ImportError:
    GPS_AVAILABLE = False
    print("[WARN] GPS libraries not installed.")

# ============================================
# HARDWARE LIBRARIES (LED, Buzzer, OLED)
# ============================================
try:
    import RPi.GPIO as GPIO
    import board
    import busio
    import adafruit_ssd1306
    from PIL import Image, ImageDraw, ImageFont
    HARDWARE_AVAILABLE = True
except ImportError as e:
    HARDWARE_AVAILABLE = False
    print(f"[WARN] Hardware libraries not installed: {e}")

app = Flask(__name__)

# ============================================
# HARDWARE SETUP
# ============================================
LED_PIN = 18
BUZZER_PIN = 23
oled = None

if HARDWARE_AVAILABLE:
    try:
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup(LED_PIN, GPIO.OUT)
        GPIO.setup(BUZZER_PIN, GPIO.OUT)
        print("[OK] LED and Buzzer initialized (GPIO 18, GPIO 23)")
    except Exception as e:
        print(f"[WARN] GPIO init failed: {e}")

    try:
        i2c = busio.I2C(board.SCL, board.SDA)
        oled = adafruit_ssd1306.SSD1306_I2C(128, 64, i2c, addr=0x3C)
        oled.fill(0)
        oled.show()
        print("[OK] OLED connected (0x3C)")
    except Exception as e:
        print(f"[WARN] OLED not connected: {e}")
        oled = None

# ============================================
# OLED SLIDING/SCROLLING LOGIC
# ============================================
current_page = 0
last_page_change = time.time()
PAGE_DELAY = 3  # Seconds bago magpalit ng page

def oled_display_sliding(lat, lon, alt, sats, speed, status):
    global current_page, last_page_change
    
    if oled is None:
        return
        
    # Palitan ang page tuwing PAGE_DELAY seconds
    if time.time() - last_page_change > PAGE_DELAY:
        current_page = (current_page + 1) % 3  # 3 pages: 0, 1, 2
        last_page_change = time.time()

    try:
        oled.fill(0)
        img = Image.new("1", (oled.width, oled.height))
        draw = ImageDraw.Draw(img)
        font = ImageFont.load_default()

        if current_page == 0:
            # PAGE 1: Status at Satellites
            draw.text((0, 0), f"STATUS: {status}", font=font, fill=255)
            draw.text((0, 16), f"SATS: {sats}/12", font=font, fill=255)
            draw.text((0, 32), f"ALT: {alt:.1f}m", font=font, fill=255)
            draw.text((0, 48), f"SPD: {speed:.1f}km/h", font=font, fill=255)
            
        elif current_page == 1:
            # PAGE 2: Coordinates
            draw.text((0, 0), "COORDINATES", font=font, fill=255)
            draw.text((0, 16), f"LAT: {lat:.5f}", font=font, fill=255)
            draw.text((0, 32), f"LON: {lon:.5f}", font=font, fill=255)
            draw.text((0, 48), f"SATS: {sats}/12", font=font, fill=255)
            
        elif current_page == 2:
            # PAGE 3: System Info / Alert
            if sats < 4:
                draw.text((0, 0), "!! WARNING !!", font=font, fill=255)
                draw.text((0, 16), "WEAK SIGNAL", font=font, fill=255)
                draw.text((0, 32), "CHECK ANTENNA", font=font, fill=255)
                draw.text((0, 48), f"SATS: {sats}/12", font=font, fill=255)
            else:
                draw.text((0, 0), "SYSTEM OK", font=font, fill=255)
                draw.text((0, 16), "GPS ACTIVE", font=font, fill=255)
                draw.text((0, 32), "MONITORING...", font=font, fill=255)
                draw.text((0, 48), "RPi 4 + NEO-6M", font=font, fill=255)

        oled.image(img)
        oled.show()
    except Exception as e:
        print(f"OLED error: {e}")

def update_hardware(lat, lon, alt, sats):
    """Update LED, Buzzer, OLED based on satellite count."""
    if not HARDWARE_AVAILABLE:
        return
    try:
        # Compute speed mula sa distance formula (approximate)
        # Sa totoong scenario, kinukuha ito sa $GPRMC sentence.
        # Dito, gagamit tayo ng 0.0 kung walang data para safe.
        speed = 0.0 # Placeholder, pwede natin i-update later kung may speed data tayo
        
        if sats >= 4:
            GPIO.output(LED_PIN, True)
            GPIO.output(BUZZER_PIN, False)
            gps_data["buzzer"] = False
            gps_data["led"] = True
            gps_data["oled_message"] = "GPS ACTIVE"
            status_text = "ACTIVE"
        else:
            GPIO.output(LED_PIN, False)
            GPIO.output(BUZZER_PIN, True)
            gps_data["buzzer"] = True
            gps_data["led"] = False
            gps_data["oled_message"] = "WEAK SIGNAL!"
            status_text = "WEAK"
            
        # I-update ang OLED (sliding)
        oled_display_sliding(lat, lon, alt, sats, speed, status_text)
        
    except Exception as e:
        print(f"Hardware update error: {e}")

# ============================================
# GLOBAL STATE
# ============================================
gps_data = {
    "latitude": 14.5995,
    "longitude": 120.9842,
    "altitude": 0,
    "satellites": 0,
    "status": "Initializing...",
    "buzzer": False,
    "led": False,
    "oled_message": "Booting...",
    "geofence_alert": False
}

# ============================================
# REAL GPS READER
# ============================================
def real_gps_reader():
    PORT = '/dev/serial0'
    BAUD = 9600
    ser = None
    retries = 0

    print(f"[INFO] Connecting to GPS on {PORT}...")

    while ser is None:
        try:
            ser = serial.Serial(PORT, baudrate=BAUD, timeout=1)
            print(f"[OK] GPS connected on {PORT}")
            gps_data["status"] = "GPS Connected"
        except serial.SerialException as e:
            retries += 1
            print(f"[FAIL] GPS failed ({retries}): {e}")
            gps_data["status"] = "GPS Disconnected"
            time.sleep(3)
            if retries > 5:
                print("[WARN] Falling back to MOCK mode.")
                mock_gps_reader()
                return

    while True:
        try:
            if ser.in_waiting > 0:
                line = ser.readline().decode('utf-8', errors='ignore').strip()
                if line.startswith('$GPGGA') or line.startswith('$GPRMC'):
                    try:
                        msg = pynmea2.parse(line)
                        
                        if hasattr(msg, 'latitude') and msg.latitude != 0.0:
                            gps_data["latitude"] = msg.latitude
                            gps_data["longitude"] = msg.longitude
                            gps_data["status"] = "GPS Active"
                        
                        if hasattr(msg, 'altitude') and msg.altitude:
                            gps_data["altitude"] = float(msg.altitude)
                        
                        if hasattr(msg, 'num_sats') and msg.num_sats:
                            gps_data["satellites"] = int(msg.num_sats)
                        
                        update_hardware(
                            gps_data["latitude"],
                            gps_data["longitude"],
                            gps_data["altitude"],
                            gps_data["satellites"]
                        )
                    except (pynmea2.ParseError, ValueError):
                        pass
            time.sleep(0.1)
        except serial.SerialException as e:
            print(f"[FAIL] Read error: {e}")
            gps_data["status"] = "GPS Lost"
            time.sleep(2)

# ============================================
# MOCK READER (Fallback kapag walang GPS)
# ============================================
def mock_gps_reader():
    print("[MOCK] Mock GPS activated.")
    gps_data["status"] = "Mock Mode"

    while True:
        gps_data["latitude"] += random.uniform(-0.0002, 0.0002)
        gps_data["longitude"] += random.uniform(-0.0002, 0.0002)
        gps_data["altitude"] = random.uniform(10, 50)
        gps_data["satellites"] = random.randint(1, 12)
        
        update_hardware(
            gps_data["latitude"],
            gps_data["longitude"],
            gps_data["altitude"],
            gps_data["satellites"]
        )
        time.sleep(2)

# ============================================
# START GPS THREAD
# ============================================
if GPS_AVAILABLE:
    gps_thread = threading.Thread(target=real_gps_reader, daemon=True)
else:
    print("[WARN] GPS libraries not available. Using mock mode.")
    gps_thread = threading.Thread(target=mock_gps_reader, daemon=True)
gps_thread.start()

# ============================================
# FLASK ROUTES
# ============================================
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/get_gps')
def get_gps():
    return jsonify(gps_data)

# ============================================
# MAIN
# ============================================
if __name__ == '__main__':
    try:
        app.run(host='0.0.0.0', port=5000, debug=False)
    finally:
        if HARDWARE_AVAILABLE:
            GPIO.cleanup()
            if oled:
                oled.fill(0)
                oled.show()
        print("Cleanup done.")
