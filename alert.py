import requests
import json
import time
import os
from datetime import datetime
from math import radians, sin, cos, sqrt, atan2

# --- Configuration ---
SONDE_API_URL = "https://api.v2.sondehub.org/sondes"
PREDICTION_API_URL = "https://api.v2.sondehub.org/predictions?vehicles="
# Webhook for predicted landings in the radius
DISCORD_LANDING_WEBHOOK_URL = os.getenv("DISCORD_LANDING_WEBHOOK_URL", "https://discordapp.com/api/webhooks/1446618700420743411/KMHJeyW3PoByB1JwqT05moVc2KXr61ywGXLp3EvzOSL4a2n1Q4HVaNR4iFTfregdxCZ4")

# User location and radius
USER_LAT = float(os.getenv("USER_LAT", "60.921800"))
USER_LON = float(os.getenv("USER_LON", "25.66003"))

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
def send_discord_alert(webhook_url, embed, content=None):
    """Sends a styled message with an embed to a Discord webhook."""
    if "YOUR_WEBHOOK_URL" in webhook_url:
        print(f"Webhook URL not configured. Printing alert to console for webhook: {webhook_url}")
        print(json.dumps(embed, indent=2))
        return

    payload = {"embeds": [embed]}
    if content:
        payload["content"] = content
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

        # Check for unrecovered sondes
        for serial, sonde_data in sondes.items():
            if not serial or sonde_data.get("recovered", 0) != 0:
                continue

            serials_to_check.append(serial)

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
                            send_discord_alert(DISCORD_LANDING_WEBHOOK_URL, embed, content=f"<@&1446621625742004264>")
                            landings_alerted.add(vehicle)

    except requests.exceptions.RequestException as e:
        print(f"Error fetching data: {e}")
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON: {e}")
    finally:
        save_alert_state(sondes_alerted, landings_alerted)

def get_sleep_duration():
    """Determines the sleep duration based on the current UTC time."""
    now_utc = datetime.utcnow()
    minute = now_utc.minute
    hour = now_utc.hour

    # Check for windows around 00:00, 06:00, and 12:00 UTC
    if (hour == 23 and minute >= 30) or (hour == 0 and minute < 30):  # 23:30 - 00:30
        return 300  # 5 minutes
    if (hour == 5 and minute >= 30) or (hour == 6 and minute < 30):   # 05:30 - 06:30
        return 300  # 5 minutes
    if (hour == 11 and minute >= 30) or (hour == 12 and minute < 30): # 11:30 - 12:30
        return 300  # 5 minutes

    return 600  # 10 minutes

if __name__ == "__main__":
    print("Alert system starting. To configure, set environment variables:")
    print("DISCORD_LANDING_WEBHOOK_URL, USER_LAT, USER_LON, LANDING_ALERT_RADIUS_KM")
    try:
        while True:
            print("\nChecking for sondes...")
            check_sonde_positions_and_predictions()
            sleep_duration = get_sleep_duration()
            print(f"Check complete. Waiting for {sleep_duration // 60} minutes. Currently tracking {len(sondes_alerted)} sondes and {len(landings_alerted)} landings.")
            time.sleep(sleep_duration)
    except KeyboardInterrupt:
        print("\nShutting down...")
