# Return Right RVM for Home Assistant

Shows the status of Singapore BCRS (Beverage Container Return Scheme) reverse vending machines from [Return Right](https://returnright.sg) as Home Assistant sensors, so you can see whether a nearby machine is running or full before you go.

<!-- screenshots to be added -->

## Disclaimer

This is an unofficial integration. It is not affiliated with, endorsed by or supported by the operator of Return Right. It relies on an undocumented API that may change or stop working at any time. It polls gently on purpose (every 5 minutes by default, configurable down to every minute, at your own risk of being blocked).

## Installation (HACS custom repository)

1. In HACS, open the menu and choose **Custom repositories**.
2. Add `https://github.com/the-observer07/ha-returnright-rvm` with category **Integration**.
3. Download **Return Right RVM** and restart Home Assistant.

Requires Home Assistant 2026.10 or newer.

## Setup

1. Go to **Settings > Devices & services > Add integration** and choose **Return Right RVM**.
2. Enter a Singapore postcode.
3. Pick the machines to track from the machines found within 1.5 km. Each is listed with its distance, address and current status. Select at least one.

Only one instance of the integration can be set up. Use the options to change machines later.

## Entities

Each machine becomes a device named after the machine.

| Entity | Type | Notes |
|---|---|---|
| Status | Enum sensor | `running`, `full` or `offline`. Attributes: `raw_status`, `address`, `remarks`, `opening_hours`. `RUNNING`, `OPERATE` and `ONLINE` map to running, `FULL` to full, anything else to offline. |
| Busiest fill | Sensor (%) | Highest fill level across the machine's compartments. |
| `<Compartment>` fill | Sensor (%) | One per compartment type, with a `last_updated` attribute. Compartments that appear later are added without a reload. |
| Bin full | Binary sensor | On when the status is full or any compartment is at 100% or more. |
| Bin last updated | Timestamp sensor | Diagnostic; disabled by default. Newest compartment update time. |

If a machine is missing from an update, its entities become unavailable.

## Options

Open the integration and choose **Configure**:

- **Update interval**: minutes between updates, 1 to 60 (default 5). Short intervals make it more likely the service blocks requests.
- **Debug logging**: logs every update at debug level (see Settings > System > Logs > Show raw logs).
- **Add machines**: enter a postcode and pick more machines within 1.5 km (machines already tracked are not offered).
- **Remove machines**: pick machines to stop tracking. At least one must remain.

## Known limits

- Singapore BCRS machines only.
- Home Assistant 2026.10 or newer.
- 64-bit systems only (as is Home Assistant itself since 2025.12).
- Updates run every 5 minutes by default; the interval can be set from 1 to 60 minutes.
- If the service blocks requests, polling backs off automatically (doubling up to 15 minutes) until it succeeds again.

## Troubleshooting

**Repairs issue "Return Right is blocking requests"**: this appears after three consecutive update cycles are rejected by the Return Right service. Machine entities stay unavailable until requests are accepted again, and the issue clears itself after the next successful update. It may be a temporary block or a change to the service. If it persists open an issue at <https://github.com/the-observer07/ha-returnright-rvm/issues>.

**"No address was found for that postcode"**: check the Singapore postcode.

**"No new machines were found within 1.5 km"**: no (new) machines near that postcode; try another.

**"Unable to reach the Return Right service"**: a network error; try again later.
