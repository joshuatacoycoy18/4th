from flask import Flask, render_template, jsonify
import threading
import time
import random

app = Flask(__name__)

# Dito natin i-save ang GPS data at Hardware status
gps_data = {
    "latitude": 14.5995,
    "longitude": 120.9842,
    "altitude": 0,
    "satellites": 0,
    "status": "Mock Mode (No Hardware)",
    "buzzer": False,
    "led": False,
    "oled_message": "System Booting...",
    "geofence_alert": False
}

def mock_gps_reader():
    # Simulate Geofence center
    safe_zone_lat = 14.5995
    safe_zone_lon = 120.9842
    
    while True:
        # Gumagalaw nang bahagya para kunwari gumagalaw ka
        gps_data["latitude"] += random.uniform(-0.0002, 0.0002)
        gps_data["longitude"] += random.uniform(-0.0002, 0.0002)
        gps_data["altitude"] = random.uniform(10, 50)
        gps_data["satellites"] = random.randint(1, 12)
        
        # Simulate Hardware Logic
        if gps_data["satellites"] < 4:
            gps_data["buzzer"] = True
            gps_data["led"] = True
            gps_data["oled_message"] = "WEAK SIGNAL!"
            gps_data["status"] = "Alert: Weak GPS"
        else:
            gps_data["buzzer"] = False
            gps_data["led"] = False
            gps_data["oled_message"] = "GPS ACTIVE"
            gps_data["status"] = "Connected"
            
        # Simulate Geofence Alert (10% chance na lumabas sa safe zone)
        if random.random() < 0.1:
            gps_data["geofence_alert"] = True
            gps_data["buzzer"] = True
            gps_data["led"] = True
            gps_data["oled_message"] = "OUTSIDE SAFE ZONE!"
            gps_data["status"] = "Geofence Alert"
        else:
            gps_data["geofence_alert"] = False
            
        time.sleep(2)

gps_thread = threading.Thread(target=mock_gps_reader, daemon=True)
gps_thread.start()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/get_gps')
def get_gps():
    return jsonify(gps_data)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)