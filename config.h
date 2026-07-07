// ═══════════════════════════════════════════════════════════════════════════
// FlightScnr Pi — API keys & home location
// ═══════════════════════════════════════════════════════════════════════════
//
// Edit this file with any text editor, save, then restart:
//   sudo systemctl restart flightscnr
//
// You can also set keys from the web portal at http://raspberrypi.local
// (saved separately — portal keys override config.h when env vars are not set)
//
// Lines starting with // are comments. Examples below — replace with your keys.

// FlightRadar24 subscription (format: subscription_key|jwt_token)
// Get keys from your FR24 subscription / the fr24 Python package docs.
FR24_API_KEY =

// Tomorrow.io weather — https://www.tomorrow.io/weather-api/
TOMORROW_API_KEY =

// Optional — schedule lookup when a flight is not airborne yet
// AIRLABS_API_KEY =

// Radar center (optional if you set location in the web portal)
HOME_LAT = 37.619664
HOME_LON = -122.372035
