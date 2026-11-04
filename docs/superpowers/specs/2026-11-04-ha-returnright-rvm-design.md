# Home Assistant integration for BCRS reverse vending machine status

Status: design approved in conversation 2026-11-04; written spec awaiting review.
Target repo: a new repo (to be created later), e.g. `ha-returnright-rvm`. This
file lives here until that repo exists, then moves with it.

## Goal

A HACS custom integration for Home Assistant. A user picks one or more
Singapore BCRS reverse vending machines (the ones on returnright.sg) and gets
each machine's status and bin fill levels as ordinary entities, which they add
to their own dashboards and automations. Intended to become a public HACS
release; the first milestone is a private install for the author.

## Non-goals (v1)

- No custom Lovelace card. Stock cards (tile, gauge, entities) cover the
  dashboard. A card can be added later.
- No dependency on, or changes to, this repo's relay or the LED firmware. The
  relay's client logic is duplicated, not shared, to avoid coupling two repos.
- No credentials, no reauth flow (the upstream API needs none).
- Singapore BCRS machines only.

## Decisions

| Question | Decision |
|---|---|
| Data source | Standalone: the integration calls the upstream API itself. Users do not run the relay. |
| Structure | One config entry, many machines (not one entry per machine). |
| Dashboard | Entities only for v1. |
| Release | Private custom-repo install first, then public HACS. |

## Upstream API (as used by `rvm_status_relay.py`)

Base `https://returnright.sg/px/ab0capi/v10`, header `x-bcrs-client: web`. The
upstream blocks clients that are not TLS-fingerprinted as a real browser, so
requests use `curl_cffi` with `impersonate="chrome"`.

1. `GET /map-token` -> `data.uuid`
2. `GET /{uuid}/locations/access-token` -> `data.token`
3. `GET /{uuid}/locations/nearby?lat&lng&radius` (headers add
   `x-bcrs-map-token: <token>`) -> `data[]` machine records: `id`, name,
   address, lat/lng, `distance`, `status`, `rvm_remarks`, `rvmOpeningHours`
4. `GET /{uuid}/locations/rvms/{id}/bin-status` (same headers) -> `data[]`
   compartments: `compartment_type`, `threshold_level` (fill %), `last_updated`

Postcode to coordinates uses OneMap
(`https://www.onemap.gov.sg/api/common/elastic/search`), as `find_machine.py` does.

`curl_cffi` 0.17.0 ships abi3 wheels for Python 3.10+ on Linux x86_64 and
aarch64 (glibc and musl) and armv7l (glibc only), so Home Assistant OS on 64-bit
hardware installs without compiling. 32-bit Alpine installs are unsupported and
documented as such.

## Structure

```
custom_components/returnright_rvm/
  __init__.py       set up the entry, forward to platforms
  api.py            async client
  coordinator.py    one DataUpdateCoordinator for all selected machines
  config_flow.py    setup flow + options flow
  sensor.py, binary_sensor.py, const.py, manifest.json, translations/en.json
hacs.json, README.md, LICENSE, tests/, .github/workflows/
```

### `api.py`

Async client over `curl_cffi`'s async session. Methods: `get_tokens()`,
`nearby(lat, lng, radius)`, `bin_status(rvm_id)`, plus postcode geocoding.
Raises distinct errors: cannot connect, bad/expired token, blocked by upstream
bot protection.

### Coordinator

Fixed interval, default 10 minutes, user-configurable with a 5 minute floor.
Each cycle: fetch tokens once; one `nearby` call per distinct location among
the selected machines; one `bin_status` call per machine. Returns a dict keyed
by machine id.

- One machine's `bin_status` failing makes only that machine's entities
  unavailable.
- A token, connection or block failure raises `UpdateFailed` for the cycle
  (all entities unavailable; Home Assistant logs once per outage and retries).
- Several consecutive blocked cycles raise a Repairs issue saying the upstream
  is blocking requests and the integration may need an update.

### Config and options flow

Setup: postcode -> multi-select of nearby machines (name, distance, address,
current status) -> one config entry holding the selected machine ids and their
coordinates. Options flow: change the poll interval, and re-run the search to
add or remove machines; removed machines have their devices and entities
cleaned up. Errors handled: postcode not found, no machines nearby, cannot
connect.

## Entities

One device per machine, named by the machine. Unique IDs are `{rvm_id}_{key}`.

| Entity | Type | Notes |
|---|---|---|
| Status | enum sensor | `running`, `full`, `offline`. Raw upstream status, address, remarks and opening hours as attributes. RUNNING/OPERATE/ONLINE -> running; FULL -> full; anything else -> offline. |
| Busiest fill | sensor, % | Highest compartment fill (what the LED firmware shows). |
| Per-compartment fill | sensor, % | One per `compartment_type`, with `last_updated` as an attribute. Created from the first data; compartments appearing later are added without a reload. |
| Bin full | binary sensor | On when status is FULL or any compartment >= 100%. |
| Bin last updated | timestamp sensor | Diagnostic, hidden by default. |

## Testing

`pytest` with `pytest-homeassistant-custom-component`.

- `api.py`: stubbed-session unit tests: parsing, error classification
  (unreachable, bad token, blocked).
- Coordinator: full success, one machine failing, whole-cycle failure, new
  compartment mid-run, consecutive-block counter raising the Repairs issue.
- Config and options flows: postcode with no match, no machines nearby,
  connection error, successful setup, adding and removing machines.
- Entities: status mapping; bin-full rule including FULL at low fill and a
  running machine at exactly 100%.
- Fixtures: a few real API responses recorded once and sanitised.

CI (GitHub Actions): pytest, ruff, hassfest, and the HACS validation action on
every push and pull request.

## Release

1. **v0.1, private:** install as a HACS custom repository on the author's Home
   Assistant and run it for about a week to surface real-world problems
   (especially upstream blocking).
2. **Public:** README with screenshots and setup steps, licence, `hacs.json`
   (minimum Home Assistant version, `country: SG`), a tagged GitHub release,
   then submission to the HACS default list. Brand-image requirements have
   changed recently; check the current rules at that point.
3. README states plainly that the integration is unofficial, not affiliated
   with the operator, depends on an undocumented API that may change, and
   polls gently on purpose.

## Open items

- Repo and domain names are provisional.
- Exact upstream status values beyond RUNNING/OPERATE/ONLINE/FULL are
  unknown; the offline mapping is a safe default and the raw value is kept in
  an attribute.
- Whether several machines near each other can share one `nearby` call
  (radius and distance limits) is to be confirmed against the live API when
  building the coordinator.
