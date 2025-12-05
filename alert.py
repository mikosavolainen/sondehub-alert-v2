import requests
import json
import time
import os
from datetime import datetime
from math import radians, sin, cos, sqrt, atan2

# --- Configuration ---
SONDE_API_URL = "https://api.v2.sondehub.org/sondes"
PREDICTION_API_URL = "https://api.v2.sondehub.org/predictions?vehicles="
# Webhook for sondes currently in the radius
DISCORD_IN_RADIUS_WEBHOOK_URL = os.getenv("DISCORD_IN_RADIUS_WEBHOOK_URL", "https://discordapp.com/api/webhooks/1437914343671988407/uv5D1PSAGRfzLA0hh-nj-9Qfu638U4szfUSi_RTIlJLIzY075HwXXV1B3l0JXWBS47Mp")
# Webhook for predicted landings in the radius
DISCORD_LANDING_WEBHOOK_URL = os.getenv("DISCORD_LANDING_WEBHOOK_URL", "https://discordapp.com/api/webhooks/1437914417894522904/ORMPEbaV3evz4AtsjlrckT3VbAhYJGuf_vV7aBPMuyUP9J3U63tKktCgbr-zFoJplfF1")

# User location and radius
USER_LAT = float(os.getenv("USER_LAT", "60.921800"))
USER_LON = float(os.getenv("USER_LON", "25.66003"))
ALERT_RADIUS_KM = int(os.getenv("ALERT_RADIUS_KM", "100"))
LANDING_ALERT_RADIUS_KM = int(os.getenv("LANDING_ALERT_RADIUS_KM", "50"))
USER_LOCATION = {"lat": USER_LAT, "lon": USER_LON}

STATE_FILE = "alert_state.json"

# --- State Management ---
def load_alert_state():
    """Loads the alerted sondes from a file."""
    if not os.path.exists(STATE_FILE):
        return set(), set()
    try:
        with open(STATE_FILE, "r") as f:
            state = json.load(f)
            return set(state.get("sondes_alerted", [])), set(state.get("landings_alerted", []))
    except (json.JSONDecodeError, IOError) as e:
        print(f"Could not load state file, starting fresh: {e}")
        return set(), set()

def save_alert_state(sondes_alerted, landings_alerted):
    """Saves the alerted sondes to a file."""
    try:
        with open(STATE_FILE, "w") as f:
            state = {"sondes_alerted": list(sondes_alerted), "landings_alerted": list(landings_alerted)}
            json.dump(state, f)
    except IOError as e:
        print(f"Error saving state file: {e}")

sondes_alerted, landings_alerted = load_alert_state()

# --- Core Functions ---
def send_discord_alert(webhook_url, embed):
    """Sends a styled message with an embed to a Discord webhook."""
    if "YOUR_WEBHOOK_URL" in webhook_url:
        print(f"Webhook URL not configured. Printing alert to console for webhook: {webhook_url}")
        print(json.dumps(embed, indent=2))
        return

    payload = {"embeds": [embed]}
    headers = {"Content-Type": "application/json"}
    try:
        response = requests.post(webhook_url, data=json.dumps(payload), headers=headers, timeout=10)
        if response.status_code == 204:
            print("Discord alert sent successfully.")
        else:
            print(f"Failed to send Discord alert. Status code: {response.status_code}, Response: {response.text}")
    except requests.exceptions.RequestException as e:
        print(f"Error sending Discord alert: {e}")

def haversine(lat1, lon1, lat2, lon2):
    """Calculates the distance between two points on Earth."""
    R = 6371
    dLat = radians(lat2 - lat1)
    dLon = radians(lon2 - lon1)
    a = sin(dLat / 2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dLon / 2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c

def check_sonde_positions_and_predictions():
    """Fetches sonde data, checks for positions and landing predictions, and sends alerts."""
    global sondes_alerted, landings_alerted
    try:
        response = requests.get(SONDE_API_URL)
        response.raise_for_status()
        sondes = response.json()
        serials_to_check = []

        # Check for unrecovered sondes in the radius
        for serial, sonde_data in sondes.items():
            if not serial or sonde_data.get("recovered", 0) != 0:
                continue

            serials_to_check.append(serial)
            if "lat" in sonde_data and "lon" in sonde_data and serial not in sondes_alerted:
                distance = haversine(USER_LOCATION["lat"], USER_LOCATION["lon"], sonde_data["lat"], sonde_data["lon"])
                if distance <= ALERT_RADIUS_KM:
                    embed = {
                        "title": "Sonde In Radius Alert",
                        "description": f"Sonde `{serial}` is **{distance:.2f} km** away (within the {ALERT_RADIUS_KM} km radius).",
                        "color": 15158332,  # Red
                        "fields": [
                            {"name": "Serial", "value": serial, "inline": True},
                            {"name": "Altitude", "value": f"{sonde_data.get('alt', 'N/A')} m", "inline": True},
                            {"name": "Position", "value": f"{sonde_data['lat']:.4f}, {sonde_data['lon']:.4f}", "inline": False},
                            {"name": "Tracker Link", "value": f"[View on SondeHub](https://sondehub.org/{serial})", "inline": False}
                        ],
                        "footer": {"text": f"Alert generated at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"}
                    }
                    send_discord_alert(DISCORD_IN_RADIUS_WEBHOOK_URL, embed)
                    sondes_alerted.add(serial)

        # Check for landing predictions
        if serials_to_check:
            vehicles_str = ",".join(serials_to_check)
            prediction_response = requests.get(f"{PREDICTION_API_URL}{vehicles_str}")
            prediction_response.raise_for_status()
            predictions = prediction_response.json()

            for prediction in predictions:
                vehicle = prediction.get("vehicle")
                if not vehicle or vehicle in landings_alerted:
                    continue

                prediction_data = json.loads(prediction.get("data", "[]"))
                if prediction_data:
                    landing_point = prediction_data[-1]
                    if "lat" in landing_point and "lon" in landing_point:
                        distance = haversine(USER_LOCATION["lat"], USER_LOCATION["lon"], landing_point["lat"], landing_point["lon"])
                        if distance <= LANDING_ALERT_RADIUS_KM:
                            embed = {
                                "title": "Predicted Landing Alert",
                                "description": f"Predicted landing for sonde `{vehicle}` is **{distance:.2f} km** away (within the {LANDING_ALERT_RADIUS_KM} km radius).",
                                "color": 3447003,  # Blue
                                "fields": [
                                    {"name": "Serial", "value": vehicle, "inline": True},
                                    {"name": "Predicted Landing", "value": f"{landing_point['lat']:.4f}, {landing_point['lon']:.4f}", "inline": False},
                                    {"name": "Tracker Link", "value": f"[View on SondeHub](https://sondehub.org/{vehicle})", "inline": False}
                                ],
                                "footer": {"text": f"Alert generated at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"}
                            }
                            send_discord_alert(DISCORD_LANDING_WEBHOOK_URL, embed)
                            landings_alerted.add(vehicle)

    except requests.exceptions.RequestException as e:
        print(f"Error fetching data: {e}")
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON: {e}")
    finally:
        save_alert_state(sondes_alerted, landings_alerted)

if __name__ == "__main__":
    print("Alert system starting. To configure, set environment variables:")
    print("DISCORD_IN_RADIUS_WEBHOOK_URL, DISCORD_LANDING_WEBHOOK_URL, USER_LAT, USER_LON, ALERT_RADIUS_KM, LANDING_ALERT_RADIUS_KM")
    while True:
        print("\nChecking for sondes...")
        check_sonde_positions_and_predictions()
        print(f"Check complete. Waiting for 5 minutes. Currently tracking {len(sondes_alerted)} sondes and {len(landings_alerted)} landings.")
        time.sleep(300)
