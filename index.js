const axios = require('axios');
const fs = require('fs').promises;
const path = require('path');

// --- Configuration ---
const SONDE_API_URL = "https://api.v2.sondehub.org/sondes";
const PREDICTION_API_URL = "https://api.v2.sondehub.org/predictions?vehicles=";
const SITES_API_URL = "https://api.v2.sondehub.org/sites";
const DISCORD_LANDING_WEBHOOK_URL = process.env.DISCORD_LANDING_WEBHOOK_URL || "https://discordapp.com/api/webhooks/1446618700420743411/KMHJeyW3PoByB1JwqT05moVc2KXr61ywGXLp3EvzOSL4a2n1Q4HVaNR4iFTfregdxCZ4";

const USER_LAT = parseFloat(process.env.USER_LAT || "60.921800");
const USER_LON = parseFloat(process.env.USER_LON || "25.66003");
const LANDING_ALERT_RADIUS_KM = parseInt(process.env.LANDING_ALERT_RADIUS_KM || "40000000");
const USER_LOCATION = { lat: USER_LAT, lon: USER_LON };

const STATE_FILE = path.join(__dirname, 'alert_state.json');

let sondesAlerted = new Set();
let landingsAlerted = {};
let sites_data = null;

// --- State Management ---
async function loadAlertState() {
    try {
        await fs.access(STATE_FILE);
        const data = await fs.readFile(STATE_FILE, 'utf8');
        const state = JSON.parse(data);
        sondesAlerted = new Set(state.sondes_alerted || []);
        landingsAlerted = state.landings_alerted || {};
    } catch (error) {
        if (error.code === 'ENOENT') {
            console.log("State file not found, starting fresh.");
        } else {
            console.error(`Could not load state file, starting fresh: ${error}`);
        }
        sondesAlerted = new Set();
        landingsAlerted = {};
    }
}

async function saveAlertState() {
    try {
        const state = {
            sondes_alerted: [...sondesAlerted],
            landings_alerted: landingsAlerted
        };
        await fs.writeFile(STATE_FILE, JSON.stringify(state, null, 2));
    } catch (error) {
        console.error(`Error saving state file: ${error}`);
    }
}

// --- Core Functions ---
async function getSitesData() {
    if (sites_data === null) {
        try {
            const response = await axios.get(SITES_API_URL);
            sites_data = response.data;
        } catch (error) {
            console.error(`Error fetching sites data: ${error}`);
            sites_data = {};
        }
    }
    return sites_data;
}

async function sendDiscordAlert(webhookUrl, embed, content = null) {
    if (webhookUrl.includes("YOUR_WEBHOOK_URL")) {
        console.log("Webhook URL not configured. Printing alert to console.");
        console.log(JSON.stringify(embed, null, 2));
        return null;
    }

    const payload = { embeds: [embed] };
    if (content) {
        payload.content = content;
    }

    try {
        const response = await axios.post(`${webhookUrl}?wait=true`, payload, {
            headers: { "Content-Type": "application/json" }
        });
        if (response.status === 200) {
            console.log("Discord alert sent successfully.");
            return { id: response.data.id, channel_id: response.data.channel_id };
        } else {
            console.error(`Failed to send Discord alert. Status code: ${response.status}, Response: ${response.data}`);
            return null;
        }
    } catch (error) {
        console.error(`Error sending Discord alert: ${error}`);
        return null;
    }
}

async function addDiscordReaction(channelId, messageId, emoji) {
    const DISCORD_BOT_TOKEN = process.env.DISCORD_BOT_TOKEN;
    if (!DISCORD_BOT_TOKEN) {
        console.log("Discord bot token not configured. Cannot add reactions.");
        return;
    }

    const url = `https://discord.com/api/v10/channels/${channelId}/messages/${messageId}/reactions/${emoji}/@me`;
    try {
        await axios.put(url, {}, {
            headers: { Authorization: `Bot ${DISCORD_BOT_TOKEN}` }
        });
        console.log(`Reaction ${emoji} added successfully.`);
    } catch (error) {
        console.error(`Failed to add reaction. Status code: ${error.response?.status}, Response: ${error.response?.data}`);
    }
}

function calculateRemainingTime(sonde, site) {
    if (!site || !site.burst_altitude || !site.ascent_rate || site.ascent_rate <= 0 || !sonde.datetime) {
        return null;
    }

    const timeToBurstSeconds = site.burst_altitude / site.ascent_rate;
    const launchTime = new Date(sonde.datetime);
    const timeSinceLaunch = (new Date() - launchTime) / 1000;
    const remainingSeconds = timeToBurstSeconds - timeSinceLaunch;
    return remainingSeconds / 3600;
}

async function checkBurstTimers(sondes, landingsAlerted) {
    const now = Date.now() / 1000;
    const activeSerials = new Set(sondes.map(s => s.vehicle).filter(Boolean));

    for (const serial in landingsAlerted) {
        const data = landingsAlerted[serial];
        if (activeSerials.has(serial)) {
            data.last_seen = now;
        } else {
            const timeSinceLastSeen = now - data.last_seen;
            const hoursSilent = Math.floor(timeSinceLastSeen / 3600);

            if (hoursSilent > data.burst_timer) {
                data.burst_timer = hoursSilent;
                const emojiMap = {
                    1: "%31%EF%B8%8F%E2%83%A3", 2: "%32%EF%B8%8F%E2%83%A3", 3: "%33%EF%B8%8F%E2%83%A3",
                    4: "%34%EF%B8%8F%E2%83%A3", 5: "%35%EF%B8%8F%E2%83%A3", 6: "%36%EF%B8%8F%E2%83%A3",
                    7: "%37%EF%B8%8F%E2%83%A3", 8: "%38%EF%B8%8F%E2%83%A3", 9: "%39%EF%B8%8F%E2%83%A3"
                };
                const emoji = emojiMap[hoursSilent];
                if (emoji) {
                    await addDiscordReaction(data.channel_id, data.message_id, emoji);
                }
            }
        }
    }
}

function haversine(lat1, lon1, lat2, lon2) {
    const R = 6371;
    const dLat = (lat2 - lat1) * Math.PI / 180;
    const dLon = (lon2 - lon1) * Math.PI / 180;
    const a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
              Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
              Math.sin(dLon / 2) * Math.sin(dLon / 2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    return R * c;
}

async function checkSondePositionsAndPredictions() {
    const sites = await getSitesData();
    try {
        const response = await axios.get(SONDE_API_URL);
        const sondes = Object.values(response.data);

        await checkBurstTimers(sondes, landingsAlerted);

        const serialsToCheck = [];
        for (const sonde of sondes) {
            const serial = sonde.serial;
            if (!serial || sonde.recovered !== 0) continue;

            let nearestSite = null;
            if (sonde.lat && sonde.lon) {
                let min_dist = Infinity;
                for (const siteId in sites) {
                    const siteData = sites[siteId];
                    if (siteData.position && siteData.position.length === 2) {
                        const dist = haversine(sonde.lat, sonde.lon, siteData.position[1], siteData.position[0]);
                        if (dist < min_dist) {
                            min_dist = dist;
                            nearestSite = siteId;
                        }
                    }
                }
            }

            if (nearestSite && sites[nearestSite]) {
                const remainingHours = calculateRemainingTime(sonde, sites[nearestSite]);
                if (remainingHours !== null && landingsAlerted[serial]) {
                    const hourFloor = Math.floor(remainingHours);
                    if (hourFloor !== landingsAlerted[serial].last_hour_reaction) {
                        landingsAlerted[serial].last_hour_reaction = hourFloor;
                        const emojiMap = {
                            1: "%31%EF%B8%8F%E2%83%A3", 2: "%32%EF%B8%8F%E2%83%A3", 3: "%33%EF%B8%8F%E2%83%A3",
                            4: "%34%EF%B8%8F%E2%83%A3", 5: "%35%EF%B8%8F%E2%83%A3", 6: "%36%EF%B8%8F%E2%83%A3",
                            7: "%37%EF%B8%8F%E2%83%A3", 8: "%38%EF%B8%8F%E2%83%A3", 9: "%39%EF%B8%8F%E2%83%A3"
                        };
                        const emoji = emojiMap[hourFloor];
                        if (emoji) {
                            await addDiscordReaction(landingsAlerted[serial].channel_id, landingsAlerted[serial].message_id, emoji);
                        }
                    }
                }
            }
            serialsToCheck.push(serial);
        }

        if (serialsToCheck.length > 0) {
            const vehiclesStr = serialsToCheck.join(',');
            const predictionResponse = await axios.get(`${PREDICTION_API_URL}${vehiclesStr}`);
            const predictions = predictionResponse.data;

            for (const prediction of predictions) {
                const vehicle = prediction.vehicle;
                if (!vehicle || landingsAlerted[vehicle]) continue;

                const predictionData = JSON.parse(prediction.data || "[]");
                if (predictionData.length > 0) {
                    const landingPoint = predictionData[predictionData.length - 1];
                    if (landingPoint.lat && landingPoint.lon) {
                        const distance = haversine(USER_LOCATION.lat, USER_LOCATION.lon, landingPoint.lat, landingPoint.lon);
                        if (distance <= LANDING_ALERT_RADIUS_KM) {
                            const embed = {
                                title: "Predicted Landing Alert",
                                description: `Predicted landing for sonde \`${vehicle}\` is **${distance.toFixed(2)} km** away (within the ${LANDING_ALERT_RADIUS_KM} km radius).`,
                                color: 3447003, // Blue
                                fields: [
                                    { name: "Serial", value: vehicle, inline: true },
                                    { name: "Predicted Landing", value: `${landingPoint.lat.toFixed(4)}, ${landingPoint.lon.toFixed(4)}`, inline: false },
                                    { name: "Tracker Link", value: `[View on SondeHub](https://sondehub.org/${vehicle})`, inline: false }
                                ],
                                footer: { text: `Alert generated at ${new Date().toISOString()}` }
                            };

                            const nowUtc = new Date();
                            let content = null;
                            if (nowUtc.getUTCHours() >= 4) {
                                content = "<@&1446621625742004264>";
                            }

                            const messageInfo = await sendDiscordAlert(DISCORD_LANDING_WEBHOOK_URL, embed, content);
                            if (messageInfo) {
                                landingsAlerted[vehicle] = {
                                    message_id: messageInfo.id,
                                    channel_id: messageInfo.channel_id,
                                    last_seen: Date.now() / 1000,
                                    burst_timer: 0,
                                    last_hour_reaction: -1
                                };
                            }
                        }
                    }
                }
            }
        }
    } catch (error) {
        console.error(`Error fetching data: ${error}`);
    } finally {
        await saveAlertState();
    }
}

function getSleepDuration() {
    const now = new Date();
    const minute = now.getUTCMinutes();
    const hour = now.getUTCHours();

    if ((hour === 23 && minute >= 30) || (hour === 0 && minute < 30) ||
        (hour === 5 && minute >= 30) || (hour === 6 && minute < 30) ||
        (hour === 11 && minute >= 30) || (hour === 12 && minute < 30)) {
        return 300 * 1000; // 5 minutes
    }
    return 600 * 1000; // 10 minutes
}

async function main() {
    console.log("Alert system starting. To configure, set environment variables:");
    console.log("DISCORD_LANDING_WEBHOOK_URL, USER_LAT, USER_LON, LANDING_ALERT_RADIUS_KM");
    await loadAlertState();
    try {
        while (true) {
            console.log("\nChecking for sondes...");
            await checkSondePositionsAndPredictions();
            const sleepDuration = getSleepDuration();
            console.log(`Check complete. Waiting for ${sleepDuration / 60000} minutes. Currently tracking ${sondesAlerted.size} sondes and ${Object.keys(landingsAlerted).length} landings.`);
            await new Promise(resolve => setTimeout(resolve, sleepDuration));
        }
    } catch (error) {
        console.error("An unexpected error occurred:", error);
    }
}

if (require.main === module) {
    main();
}
