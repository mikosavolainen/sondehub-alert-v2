import requests
import json
import time
import os
from datetime import datetime, timezone, timedelta
from math import radians, sin, cos, sqrt, atan2

# --- Configuration ---
SONDE_API_URL = "https://api.v2.sondehub.org/sondes"
PREDICTION_API_URL = "https://api.v2.sondehub.org/predictions?vehicles="
SITES_API_URL = "https://api.v2.sondehub.org/sites"

# Webhook for predicted landings in the radius
DISCORD_LANDING_WEBHOOK_URL = os.getenv("DISCORD_LANDING_WEBHOOK_URL", "https://discordapp.com/api/webhooks/1514763343796371637/DlBPQtH9jVLXThVRwfSMsyDBNoPUy4aTgnc0w8vQJAxXO9RuackVqvRa_yVhm_bryd9Q")

# User location and radius
USER_LAT = float(os.getenv("USER_LAT", "60.921800"))
USER_LON = float(os.getenv("USER_LON", "25.66003"))
LANDING_ALERT_RADIUS_KM = int(os.getenv("LANDING_ALERT_RADIUS_KM", "40000000"))
USER_LOCATION = {"lat": USER_LAT, "lon": USER_LON}

# Most standard sondes (like Vaisala RS41) have a hardware auto-kill timer of ~8.5 hours (510 mins)
SONDE_LIFESPAN_HOURS = float(os.getenv("SONDE_LIFESPAN_HOURS", "8.5"))

STATE_FILE = "alert_state.json"

# --- State Management ---
def load_alert_state():
    """Loads the alerted sondes from a file to prevent duplicate webhook alerts."""
    if not os.path.exists(STATE_FILE):
        return set()
    try:
        with open(STATE_FILE, "r") as f:
            state = json.load(f)
            # Support migrating from old dict structures by extracting keys if needed
            if isinstance(state, dict):
                return set(state.get("sondes_alerted", []))
            return set(state)
    except (json.JSONDecodeError, IOError) as e:
        print(f"Could not load state file, starting fresh: {e}")
        return set()

def save_alert_state(sondes_alerted):
    """Saves the alerted sondes to a file."""
    try:
        with open(STATE_FILE, "w") as f:
            json.dump({"sondes_alerted": list(sondes_alerted)}, f)
    except IOError as e:
        print(f"Error saving state file: {e}")

sondes_alerted = load_alert_state()
sites_data = None

# --- Core Functions ---
def get_sites_data():
    """Fetches and caches the sites data from the SondeHub API."""
    global sites_data
    if sites_data is None:
        try:
            response = requests.get(SITES_API_URL)
            response.raise_for_status()
            sites_data = response.json()
        except requests.exceptions.RequestException as e:
            print(f"Error fetching sites data: {e}")
            sites_data = {}
    return sites_data

def send_discord_alert(webhook_url, embed, content=None):
    """Sends a styled message with an embed to a Discord webhook."""
    if "YOUR_WEBHOOK_URL" in webhook_url:
        print(f"Webhook URL not configured. Printing alert to console:")
        print(json.dumps(embed, indent=2))
        return False

    payload = {"embeds": [embed]}
    if content:
        payload["content"] = content
    headers = {"Content-Type": "application/json"}
    try:
        response = requests.post(webhook_url, data=json.dumps(payload), headers=headers, timeout=10)
        if response.status_code in [200, 204]:
            print("Discord alert sent successfully.")
            return True
        else:
            print(f"Failed to send Discord alert. Status code: {response.status_code}, Response: {response.text}")
            return False
    except requests.exceptions.RequestException as e:
        print(f"Error sending Discord alert: {e}")
        return False

def get_time_until_silent(launch_time_str, lifespan_hours=SONDE_LIFESPAN_HOURS):
    """Estimates time remaining or time passed since the sonde's kill timer expired."""
    if not launch_time_str:
        return "Unknown"
    try:
        launch_time = datetime.fromisoformat(launch_time_str.replace('Z', '+00:00'))
        estimated_death_time = launch_time + timedelta(hours=lifespan_hours)
        now_utc = datetime.now(timezone.utc)
        
        remaining = estimated_death_time - now_utc
        total_seconds = remaining.total_seconds()
        
        if total_seconds > 0:
            # Timer is active, show remaining time
            hours = int(total_seconds // 3600)
            minutes = int((total_seconds % 3600) // 60)
            return f"~{hours}h {minutes}m left"
        else:
            # Timer has expired, calculate how long ago
            abs_seconds = abs(total_seconds)
            hours = int(abs_seconds // 3600)
            minutes = int((abs_seconds % 3600) // 60)
            return f"Expired {hours}h {minutes}m ago"
            
    except ValueError:
        return "Unknown"

def haversine(lat1, lon1, lat2, lon2):
    """Calculates the distance between two points on Earth."""
    R = 6371
    dLat = radians(lat2 - lat1)
    dLon = radians(lon2 - lon1)
    a = sin(dLat / 2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dLon / 2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c

def check_sonde_positions_and_predictions():
    """Fetches sonde data, checks landing predictions, and sends webhook alerts."""
    global sondes_alerted
    try:
        response = requests.get(SONDE_API_URL)
        response.raise_for_status()
        sondes_data = response.json()
        
        sondes_list = list(sondes_data.values()) if isinstance(sondes_data, dict) else sondes_data
        serials_to_check = []

        # Gather unrecovered sondes to query predictions
        for sonde in sondes_list:
            serial = sonde.get("serial")
            if not serial or sonde.get("recovered", 0) != 0:
                continue
            if serial not in sondes_alerted:
                serials_to_check.append(serial)

        # Check for landing predictions
        if serials_to_check:
            vehicles_str = ",".join(serials_to_check)
            prediction_response = requests.get(f"{PREDICTION_API_URL}{vehicles_str}")
            prediction_response.raise_for_status()
            predictions = prediction_response.json()

            for prediction in predictions:
                vehicle = prediction.get("vehicle")
                if not vehicle or vehicle in sondes_alerted:
                    continue

                prediction_data = json.loads(prediction.get("data", "[]"))
                if prediction_data:
                    landing_point = prediction_data[-1]
                    if "lat" in landing_point and "lon" in landing_point:
                        distance = haversine(USER_LOCATION["lat"], USER_LOCATION["lon"], landing_point["lat"], landing_point["lon"])
                        
                        if distance <= LANDING_ALERT_RADIUS_KM:
                            # Pull data from active sonde profile to check its launch time
                            target_sonde = next((s for s in sondes_list if s.get("serial") == vehicle), {})
                            time_left_str = get_time_until_silent(target_sonde.get("datetime"))

                            embed = {
                                "title": "Predicted Landing Alert",
                                "description": f"Predicted landing for sonde `{vehicle}` is **{distance:.2f} km** away.",
                                "color": 3447003,  # Blue
                                "fields": [
                                    {"name": "Serial", "value": vehicle, "inline": True},
                                    {"name": "Transmission Remaining", "value": f"`{time_left_str}`", "inline": True},
                                    {"name": "Predicted Landing", "value": f"{landing_point['lat']:.4f}, {landing_point['lon']:.4f}", "inline": False},
                                    {"name": "Tracker Link", "value": f"[View on SondeHub](https://sondehub.org/{vehicle})", "inline": False}
                                ],
                                "footer": {"text": f"Alert generated at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"}
                            }

                            # Mentions a role if alert falls on or after 04:00 UTC
                            now_utc = datetime.now(timezone.utc)
                            content = f"<@&1446621625742004264>" if now_utc.hour >= 4 else None

                            if send_discord_alert(DISCORD_LANDING_WEBHOOK_URL, embed, content=content):
                                sondes_alerted.add(vehicle)

    except requests.exceptions.RequestException as e:
        print(f"Error fetching data: {e}")
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON: {e}")
    finally:
        save_alert_state(sondes_alerted)

def get_sleep_duration():
    """Determines the sleep duration based on the current UTC time."""
    now_utc = datetime.now(timezone.utc)
    minute = now_utc.minute
    hour = now_utc.hour

    # Frequent updates during common launch intervals (00, 06, 12 UTC)
    if (hour == 23 and minute >= 30) or (hour == 0 and minute < 30):
        return 300
    if (hour == 5 and minute >= 30) or (hour == 6 and minute < 30):
        return 300
    if (hour == 11 and minute >= 30) or (hour == 12 and minute < 30):
        return 300

    return 600  # Default 10 minutes

if __name__ == "__main__":
    print("Alert system starting. Webhook mode active.")
    try:
        while True:
            print("\nChecking for sondes...")
            check_sonde_positions_and_predictions()
            sleep_duration = get_sleep_duration()
            print(f"Check complete. Waiting {sleep_duration // 60} minutes. Total alerted tracking cache: {len(sondes_alerted)}")
            time.sleep(sleep_duration)
    except KeyboardInterrupt:
        print("\nShutting down...")