import requests
import json
import time
import os
from datetime import datetime, timezone
from math import radians, sin, cos, sqrt, atan2

# --- Configuration ---
SONDE_API_URL = "https://api.v2.sondehub.org/sondes"
PREDICTION_API_URL = "https://api.v2.sondehub.org/predictions?vehicles="
SITES_API_URL = "https://api.v2.sondehub.org/sites"
# Webhook for predicted landings in the radius
DISCORD_LANDING_WEBHOOK_URL = os.getenv("DISCORD_LANDING_WEBHOOK_URL", "https://discordapp.com/api/webhooks/1446618700420743411/KMHJeyW3PoByB1JwqT05moVc2KXr61ywGXLp3EvzOSL4a2n1Q4HVaNR4iFTfregdxCZ4")

# User location and radius
USER_LAT = float(os.getenv("USER_LAT", "60.921800"))
USER_LON = float(os.getenv("USER_LON", "25.66003"))
LANDING_ALERT_RADIUS_KM = int(os.getenv("LANDING_ALERT_RADIUS_KM", "40000000"))
USER_LOCATION = {"lat": USER_LAT, "lon": USER_LON}

STATE_FILE = "alert_state.json"

# --- State Management ---
def load_alert_state():
    """Loads the alerted sondes from a file, handling legacy format."""
    if not os.path.exists(STATE_FILE):
        return set(), {}
    try:
        with open(STATE_FILE, "r") as f:
            state = json.load(f)
            sondes_alerted = set(state.get("sondes_alerted", []))
            landings_alerted_data = state.get("landings_alerted", {})

            # Handle migration from old list format to new dict format
            if isinstance(landings_alerted_data, list):
                print("Old 'landings_alerted' format detected in state file. Starting fresh for landing alerts.")
                landings_alerted = {}
            else:
                landings_alerted = landings_alerted_data

            return sondes_alerted, landings_alerted
    except (json.JSONDecodeError, IOError) as e:
        print(f"Could not load state file, starting fresh: {e}")
        return set(), {}

def save_alert_state(sondes_alerted, landings_alerted):
    """Saves the alerted sondes to a file."""
    try:
        with open(STATE_FILE, "w") as f:
            state = {"sondes_alerted": list(sondes_alerted), "landings_alerted": landings_alerted}
            json.dump(state, f)
    except IOError as e:
        print(f"Error saving state file: {e}")

sondes_alerted, landings_alerted = load_alert_state()
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
        print(f"Webhook URL not configured. Printing alert to console for webhook: {webhook_url}")
        print(json.dumps(embed, indent=2))
        return None

    payload = {"embeds": [embed]}
    if content:
        payload["content"] = content
    headers = {"Content-Type": "application/json"}
    try:
        response = requests.post(f"{webhook_url}?wait=true", data=json.dumps(payload), headers=headers, timeout=10)
        if response.status_code == 200:
            print("Discord alert sent successfully.")
            message_data = response.json()
            return message_data.get("id"), message_data.get("channel_id")
        else:
            print(f"Failed to send Discord alert. Status code: {response.status_code}, Response: {response.text}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Error sending Discord alert: {e}")
        return None

def add_discord_reaction(channel_id, message_id, emoji):
    """Adds a reaction to a specific Discord message."""
    DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
    if not DISCORD_BOT_TOKEN:
        print("Discord bot token not configured. Cannot add reactions.")
        return

    url = f"https://discord.com/api/v10/channels/{channel_id}/messages/{message_id}/reactions/{emoji}/@me"
    headers = {"Authorization": f"Bot {DISCORD_BOT_TOKEN}"}
    try:
        response = requests.put(url, headers=headers, timeout=10)
        if response.status_code == 204:
            print(f"Reaction {emoji} added successfully.")
        else:
            print(f"Failed to add reaction. Status code: {response.status_code}, Response: {response.text}")
    except requests.exceptions.RequestException as e:
        print(f"Error adding reaction: {e}")

def calculate_remaining_time(sonde, site):
    """Calculates the remaining time until the sonde bursts."""
    if not site or 'burst_altitude' not in site or 'ascent_rate' not in site:
        return None

    burst_altitude = site['burst_altitude']
    ascent_rate = site['ascent_rate']

    if ascent_rate <= 0:
        return None

    time_to_burst_seconds = burst_altitude / ascent_rate

    launch_time_str = sonde.get("datetime")
    if not launch_time_str:
        return None

    launch_time = datetime.fromisoformat(launch_time_str.replace('Z', '+00:00'))

    time_since_launch = (datetime.now(timezone.utc) - launch_time).total_seconds()

    remaining_seconds = time_to_burst_seconds - time_since_launch
    remaining_hours = remaining_seconds / 3600

    return remaining_hours
def check_burst_timers(sondes, landings_alerted):
    """Checks for sondes that have stopped transmitting and adds a reaction."""
    now = datetime.now(timezone.utc).timestamp()
    active_serials = {sonde['vehicle'] for sonde in sondes if 'vehicle' in sonde}

    for serial, data in list(landings_alerted.items()):
        if serial in active_serials:
            # Sonde is still transmitting, update last_seen
            landings_alerted[serial]["last_seen"] = now
        else:
            # Sonde is not in the active list
            time_since_last_seen = now - data["last_seen"]
            hours_silent = int(time_since_last_seen // 3600)

            if hours_silent > data["burst_timer"]:
                landings_alerted[serial]["burst_timer"] = hours_silent
                emoji_map = {
                    1: "1%E2%83%A3", 2: "2%E2%83%A3", 3: "3%E2%83%A3",
                    4: "4%E2%83%A3", 5: "5%E2%83%A3", 6: "6%E2%83%A3",
                    7: "7%E2%83%A3", 8: "8%E2%83%A3", 9: "9%E2%83%A3"
                }
                emoji = emoji_map.get(hours_silent)
                if emoji:
                    add_discord_reaction(data["channel_id"], data["message_id"], emoji)


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
    sites = get_sites_data()
    try:
        response = requests.get(SONDE_API_URL)
        response.raise_for_status()
        sondes = response.json()

        # Check burst timers for alerted landings
        check_burst_timers(sondes, landings_alerted)

        serials_to_check = []

        # Check for unrecovered sondes
        for sonde in sondes.values():
            serial = sonde.get("serial")
            if not serial or sonde.get("recovered", 0) != 0:
                continue

            # Find the nearest site
            min_dist = float('inf')
            nearest_site = None
            if 'lat' in sonde and 'lon' in sonde:
                for site_id, site_data in sites.items():
                    if 'position' in site_data and len(site_data['position']) == 2:
                        dist = haversine(sonde['lat'], sonde['lon'], site_data['position'][1], site_data['position'][0])
                        if dist < min_dist:
                            min_dist = dist
                            nearest_site = site_id

            # Now you have the nearest_site, you can use it to get burst_altitude and ascent_rate
            if nearest_site and nearest_site in sites:
                remaining_hours = calculate_remaining_time(sonde, sites[nearest_site])
                if remaining_hours is not None and serial in landings_alerted:
                    hour_floor = int(remaining_hours)
                    if hour_floor != landings_alerted[serial]["last_hour_reaction"]:
                        landings_alerted[serial]["last_hour_reaction"] = hour_floor
                        emoji_map = {
                            1: "1%E2%83%A3", 2: "2%E2%83%A3", 3: "3%E2%83%A3",
                            4: "4%E2%83%A3", 5: "5%E2%83%A3", 6: "6%E2%83%A3",
                            7: "7%E2%83%A3", 8: "8%E2%83%A3", 9: "9%E2%83%A3"
                        }
                        emoji = emoji_map.get(hour_floor)
                        if emoji:
                            add_discord_reaction(landings_alerted[serial]["channel_id"], landings_alerted[serial]["message_id"], emoji)

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
                                "footer": {"text": f"Alert generated at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"}
                            }

                            # Add role mention only at or after 04:00 UTC
                            now_utc = datetime.now(timezone.utc)
                            content = None
                            if now_utc.hour >= 4:
                                content = f"<@&1446621625742004264>"

                            message_info = send_discord_alert(DISCORD_LANDING_WEBHOOK_URL, embed, content=content)
                            if message_info:
                                landings_alerted[vehicle] = {
                                    "message_id": message_info[0],
                                    "channel_id": message_info[1],
                                    "last_seen": datetime.now(timezone.utc).timestamp(),
                                    "burst_timer": 0
                                }

    except requests.exceptions.RequestException as e:
        print(f"Error fetching data: {e}")
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON: {e}")
    finally:
        save_alert_state(sondes_alerted, landings_alerted)

def get_sleep_duration():
    """Determines the sleep duration based on the current UTC time."""
    now_utc = datetime.now(timezone.utc)
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
