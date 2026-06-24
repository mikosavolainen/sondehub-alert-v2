# SondeHub Alert V2

A Python-based alert system for SondeHub, designed to notify via Discord when a sonde is predicted to land within a specified radius.

## Features
- Monitors SondeHub for active sondes.
- Checks landing predictions for unrecovered sondes.
- Sends Discord notifications with sonde details and tracker links.
- Persists alerted sondes to avoid duplicate notifications.
- Dockerized for easy deployment and automatic restarts.

## Prerequisites
- [Docker](https://docs.docker.com/get-docker/)
- [Docker Compose](https://docs.docker.com/compose/install/)
- A Discord Webhook URL

## Configuration

The application is configured via environment variables. Create a `.env` file in the root directory with the following variables:

```env
DISCORD_LANDING_WEBHOOK_URL=https://discordapp.com/api/webhooks/...
USER_LAT=60.921800
USER_LON=25.66003
LANDING_ALERT_RADIUS_KM=100
SONDE_LIFESPAN_HOURS=8.5
STATE_FILE=data/alert_state.json
```

| Variable | Description | Default |
| --- | --- | --- |
| `DISCORD_LANDING_WEBHOOK_URL` | Discord webhook URL for alerts. | |
| `USER_LAT` | Your latitude. | `60.921800` |
| `USER_LON` | Your longitude. | `25.66003` |
| `LANDING_ALERT_RADIUS_KM` | Radius in km for landing alerts. | `40000000` (effectively global) |
| `SONDE_LIFESPAN_HOURS` | Estimated battery life of a sonde in hours. | `8.5` |
| `STATE_FILE` | Path to the JSON file for state persistence. | `data/alert_state.json` |

## Installation & Running

### Using Docker (Recommended)

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd sondehub-alert-v2
   ```

2. **Configure environment variables:**
   Create a `.env` file as described above.

3. **Start the application:**
   ```bash
   docker-compose up -d
   ```
   This will build the image and start the container in the background. It is configured to restart automatically on boot or failure.

4. **View logs:**
   ```bash
   docker-compose logs -f
   ```

5. **Stop the application:**
   ```bash
   docker-compose down
   ```

### Manual Installation

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Run the script:**
   ```bash
   python alert.py
   ```
   *Note: Ensure you have set the necessary environment variables in your shell.*

## Maintenance

The state of alerted sondes is stored in the `data/` directory (or wherever `STATE_FILE` points). This directory is mounted as a volume in Docker to ensure persistence across container restarts and updates.