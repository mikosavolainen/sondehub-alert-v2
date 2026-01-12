# Sondehub Alert V2 (Node.js & Docker)

This application monitors the SondeHub API for radiosondes and sends alerts to a Discord webhook for predicted landings within a specified radius of a user-defined location.

## Configuration

The application is configured via environment variables. You can create a `.env` file in the root of the project to store these variables.

- `DISCORD_LANDING_WEBHOOK_URL`: The Discord webhook URL for landing alerts.
- `DISCORD_BOT_TOKEN`: A Discord bot token with permissions to add reactions to messages.
- `USER_LAT`: Your latitude.
- `USER_LON`: Your longitude.
- `LANDING_ALERT_RADIUS_KM`: The radius in kilometers to check for predicted landings.

## Running with Docker

1. **Build the Docker image:**
   ```bash
   docker build -t sondehub-alert .
   ```

2. **Run the Docker container:**
   ```bash
   docker run --env-file .env sondehub-alert
   ```

   *Note: The `--env-file` flag is the easiest way to manage your environment variables. Make sure your `.env` file is in the same directory where you are running the `docker run` command.*

## State

The application maintains a state file (`alert_state.json`) to keep track of sondes that have already been alerted. This file is created automatically.
