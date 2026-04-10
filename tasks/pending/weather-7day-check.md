---
profile: small
priority: normal
status: pending
created: "2026-04-10T00:00:00Z"
---

# Check the weather for the next 7 days

## Description
Fetch the 7-day weather forecast for Seattle, WA (default — no location was specified) and summarize it.

Suggested approach:
- Use a free weather API such as the US National Weather Service (`api.weather.gov`) or Open-Meteo (`api.open-meteo.com/v1/forecast`) — no auth required.
- Report daily high/low temps, conditions, and precipitation chance for each of the next 7 days.
- Note any notable weather (storms, heat waves, freeze warnings, etc.).

Output format: a concise markdown table plus a 2-3 sentence summary highlighting anything interesting. Keep it short and readable.
