# Changelog

## 0.1.0

First release.

- Config flow: enter a Singapore postcode, then pick reverse vending machines within 1.5 km. Only one instance can be set up.
- Options flow: change the update interval (1 to 60 minutes, default 5), add machines by postcode, remove machines (at least one must remain).
- One device per machine with these entities:
  - Status (enum sensor: running, full, offline) with raw status, address, remarks and opening hours as attributes.
  - Fill level (sensor, %, highest across compartments).
  - One fill sensor per compartment type (%), with a `last_updated` attribute; compartments that appear later are added without a reload.
  - Bin full (binary sensor).
  - Bin last updated (diagnostic timestamp sensor, disabled by default).
- Repairs issue "Return Right is blocking requests" after three consecutive update cycles rejected by the service; it clears after the next successful update.
- When the service blocks a request, polling backs off (interval doubles per blocked cycle, up to 15 minutes) and returns to normal after the next success.
