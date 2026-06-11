# SondeHub Alert System

This script monitors the SondeHub API for predicted landings of radiosondes within a specified radius and sends alerts to a Discord webhook.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/)
- [Docker Compose](https://docs.docker.com/compose/install/)

## Installation & Setup

1.  **Clone the repository** (if you haven't already).
2.  **Configure Environment Variables**:
    Create a `.env` file in the root directory and add the following variables:
    ```env
    DISCORD_LANDING_WEBHOOK_URL=your_discord_webhook_url
    USER_LAT=60.921800
    USER_LON=25.66003
    LANDING_ALERT_RADIUS_KM=100
    # Optional:
    SONDE_LIFESPAN_HOURS=8.5
    ```

3.  **Run with Docker Compose**:
    The system is designed to run in a Docker container and will automatically restart if it fails or if the host system reboots.

    ```bash
    docker-compose up -d --build
    ```

## Maintenance

- **Logs**: To view the application logs, run:
  ```bash
  docker-compose logs -f
  ```
- **State**: The application persists its alert state in the `data/` directory on the host to avoid duplicate alerts after a restart.
- **Stopping**: To stop the system, run:
  ```bash
  docker-compose down
  ```

## Development (Local)

If you wish to run the script directly without Docker:

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Set your environment variables.
3. Run the script:
   ```bash
   python alert.py
   ```
