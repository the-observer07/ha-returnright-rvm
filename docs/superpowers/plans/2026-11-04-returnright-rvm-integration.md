# Return Right RVM Home Assistant Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A HACS custom integration that shows Singapore BCRS reverse vending machine status and bin fill levels as Home Assistant entities.

**Architecture:** One config entry holds the user's selected machines. One `DataUpdateCoordinator` fetches an upstream token pair once per cycle, then one `nearby` call per distinct search origin and one `bin-status` call per machine. A small async client over `curl_cffi` (Chrome impersonation) talks to the upstream API. Entities are coordinator-backed, one device per machine.

**Tech Stack:** Python 3.14, Home Assistant 2026.10.x, `curl_cffi==0.17.0`, `pytest-homeassistant-custom-component==0.13.375`, ruff, GitHub Actions (hassfest, HACS action).

**Spec:** `docs/superpowers/specs/2026-11-04-ha-returnright-rvm-design.md`

## Inputs needed from Royce before Task 1

- GitHub repo: resolved from `origin`: `the-observer07/ha-returnright-rvm`. So `documentation` is `https://github.com/the-observer07/ha-returnright-rvm`, `issue_tracker` is `https://github.com/the-observer07/ha-returnright-rvm/issues`, and `codeowners` is `["@the-observer07"]`.
- Licence: MIT (confirmed by Royce; OSI-approved, which the HACS default list requires).
- Brand icon: still needed. A 256x256 PNG for `brand/icon.png` (Task 9). Without one, Task 9 generates a plain placeholder and flags it.

## Global Constraints

- Domain `returnright_rvm`; display name `Return Right RVM`; `manifest.json` has `"iot_class": "cloud_polling"`, `"integration_type": "service"`, `"config_flow": true`, `"single_config_entry": true`, `"version": "0.1.0"`, `"requirements": ["curl_cffi==0.17.0"]`.
- Tests run on Python 3.14 with `pytest-homeassistant-custom-component==0.13.375` (pins `homeassistant==2026.10.4`); `pyproject.toml` sets `asyncio_mode = "auto"`. `hacs.json`: `{"name": "Return Right RVM", "homeassistant": "2026.10.0", "country": "SG"}`.
- Upstream: base `https://returnright.sg/px/ab0capi/v10`, header `x-bcrs-client: web`; data calls add `x-bcrs-map-token: <token>`. Endpoints: `GET /map-token` (`data.uuid`), `GET /{uuid}/locations/access-token` (`data.token`), `GET /{uuid}/locations/nearby?lat&lng&radius`, `GET /{uuid}/locations/rvms/{id}/bin-status`. Geocoding: OneMap `https://www.onemap.gov.sg/api/common/elastic/search?searchVal=<postcode>&returnGeom=Y&getAddrDetails=Y&pageNum=1`. Requests use `curl_cffi` `AsyncSession(impersonate="chrome")`. One token pair serves every call in a cycle.
- Polling: default 10 minutes, minimum 5, maximum 60, user-configurable. Search radius 1500 m.
- Status mapping, case-insensitive: `RUNNING`/`OPERATE`/`ONLINE` -> `running`; `FULL` -> `full`; anything else, including `ERROR`, `offline` and `None` -> `offline`. The raw value is kept as an attribute.
- Bin full = status `full`, or any compartment `fill_pct >= 100`.
- Hassfest rules for custom integrations: translations in `translations/en.json` only (no `strings.json`, no `[%key:...%]` references); no URLs or HTML in strings. Use `ConfigEntry.runtime_data` with `type RvmConfigEntry = ConfigEntry[RvmCoordinator]`, never `hass.data`. `DataUpdateCoordinator` is given `config_entry=`. `OptionsFlow` never assigns `self.config_entry`.
- Commit only when Royce has asked for commits. When committing, end the message with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.

## Review Focus

Inputs and conditions the spec implies that no obvious test covers, most likely first. Each has its test in the task that owns the code.

1. A machine with **zero compartments**: busiest fill is unknown (`None`), bin-full is off, nothing crashes. (Task 2, Task 7)
2. **Null** `rvm_remarks` / `rvmOpeningHours` (seen on 10 of 67 machines in live data): attributes become `""`. (Task 2)
3. Machine statuses **outside the documented set** (`offline` lowercase, `ERROR`, `None`): map to `offline`, raw kept. (Task 2)
4. A configured machine **missing from `nearby`** (removed or moved upstream): only its entities go unavailable; the cycle still succeeds. (Task 4)
5. Options flow: **removing every machine** is refused, and **adding a machine already selected** is ignored. (Task 5)

---

### Task 1: Scaffold, toolchain and CI

**Files:**
- Create: `pyproject.toml`, `requirements_test.txt`, `.gitignore`, `LICENSE`, `hacs.json`, `.github/workflows/validate.yml`, `.github/workflows/tests.yml`
- Create: `custom_components/returnright_rvm/{__init__.py,manifest.json,const.py}`, `custom_components/returnright_rvm/translations/en.json`
- Create: `tests/__init__.py`, `tests/conftest.py`, `tests/test_manifest.py`

**Interfaces:**
- Produces (`const.py`): `DOMAIN`, `BASE_URL`, `ONEMAP_URL`, `SEARCH_RADIUS_M = 1500`, `CONF_MACHINES = "machines"`, `CONF_SCAN_INTERVAL = "scan_interval"`, `DEFAULT_SCAN_INTERVAL_MIN = 10`, `MIN_SCAN_INTERVAL_MIN = 5`, `MAX_SCAN_INTERVAL_MIN = 60`, `BLOCKED_CYCLES_BEFORE_REPAIR = 3`, `ISSUE_UPSTREAM_BLOCKED = "upstream_blocked"`, `STATUS_RUNNING = "running"`, `STATUS_FULL = "full"`, `STATUS_OFFLINE = "offline"`.
- Produces: `tests/conftest.py` autouse fixture enabling custom integrations (`enable_custom_integrations`).
- Produces: a working venv at `.venv` (gitignored) used by every later `pytest` command.

- [ ] **Step 1: Create the venv.** `pipx install uv` (or `pip install --user uv`), then `uv venv --python 3.14 .venv` and `uv pip install --python .venv/bin/python -r requirements_test.txt`. `requirements_test.txt` lists `pytest-homeassistant-custom-component==0.13.375`, `curl_cffi==0.17.0`, `ruff` pinned to whatever version resolves (write the resolved version back into the file). Expected: install finishes; `.venv/bin/python -c "import homeassistant, curl_cffi"` exits 0.
- [ ] **Step 2: Write the failing manifest test** in `tests/test_manifest.py`: `test_manifest_matches_spec` loads `manifest.json` and asserts `domain == "returnright_rvm"`, `iot_class == "cloud_polling"`, `integration_type == "service"`, `config_flow is True`, `single_config_entry is True`, `requirements == ["curl_cffi==0.17.0"]`, `version == "0.1.0"`, both `documentation` and `issue_tracker` start with `https://github.com/`, and `codeowners` is non-empty. Also `test_hacs_json_matches_spec` asserts the exact `hacs.json` dict above.
- [ ] **Step 3: Run it to verify it fails.** `.venv/bin/python -m pytest tests/test_manifest.py -v` -> FAIL (files missing).
- [ ] **Step 4: Create the files.** `manifest.json` per Global Constraints (keys ordered `domain`, `name`, then alphabetical; fill URLs and `codeowners` from the Inputs). `__init__.py` is an empty module for now. `const.py` as in Produces. `translations/en.json` is `{}` for now (later tasks add to it). `pyproject.toml` sets pytest `asyncio_mode = "auto"` and `testpaths = ["tests"]`, and ruff (line length 100, rules `E,F,I,UP,B`). `LICENSE` per Inputs. `.gitignore` covers `.venv`, `__pycache__`, `.pytest_cache`, `.ruff_cache`.
- [ ] **Step 5: Add CI.** `validate.yml`: the hassfest + HACS workflow below. `tests.yml`: on push and PR, `actions/setup-python` with `3.14`, `pip install -r requirements_test.txt`, then `ruff check .` and `pytest`.

```yaml
name: Validate
on:
  push:
  pull_request:
  schedule:
    - cron: "0 0 * * *"
  workflow_dispatch:
jobs:
  hassfest:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: home-assistant/actions/hassfest@master
  hacs:
    runs-on: ubuntu-latest
    steps:
      - uses: hacs/action@main
        with:
          category: integration
```
- [ ] **Step 6: Run tests and lint.** `.venv/bin/python -m pytest -v` -> PASS; `.venv/bin/ruff check .` -> no findings.
- [ ] **Step 7: Commit** `chore: scaffold integration, test toolchain and CI`.

---

### Task 2: Models and status logic

**Files:**
- Create: `custom_components/returnright_rvm/models.py`, `tests/test_models.py`

**Interfaces:**
- Consumes: `const.STATUS_*`.
- Produces (`models.py`), all frozen `slots` dataclasses unless noted:
  - `Compartment(type: str, fill_pct: int, last_updated: datetime | None)`
  - `Machine(id: int, name: str, address: str, postal_code: str, lat: float, lng: float, distance_m: float, raw_status: str | None, remarks: str, opening_hours: str)`
  - `MachineData(machine: Machine, compartments: tuple[Compartment, ...])`
  - `parse_machine(record: dict[str, Any]) -> Machine`; `parse_compartment(record: dict[str, Any]) -> Compartment`
  - `normalise_status(raw: str | None) -> str` (returns a `STATUS_*` value)
  - `busiest_fill(compartments: Iterable[Compartment]) -> int | None`
  - `is_bin_full(status: str, compartments: Iterable[Compartment]) -> bool`

- [ ] **Step 1: Write failing tests** in `tests/test_models.py` (use the record shapes recorded in Task 3's fixtures; inline small dicts here):
  - `test_parse_machine_maps_upstream_keys`: `{"id":1203,"locationName":"Cold Storage Serangoon Nex","address":"23 Serangoon Central #B2-44/45 NEX, 556083","postalCode":"556083","latitude":"1.350819","longitude":"103.872500","status":"RUNNING","rvm_remarks":"r","rvmOpeningHours":"Mon - Sun:  24 Hrs","distance":321.03}` -> `name`, `lat == 1.350819` (float from string), `lng == 103.8725`, `distance_m == 321.03`, `remarks == "r"`.
  - `test_parse_machine_null_remarks_and_hours_become_empty_strings` (Review Focus 2): `rvm_remarks` and `rvmOpeningHours` as `None`, then as absent -> both `""`.
  - `test_parse_compartment_reads_iso_utc_timestamp`: `{"compartment_type":"CAN PET","threshold_level":40,"last_updated":"2026-11-04T02:24:34.000Z"}` -> `type "CAN PET"`, `fill_pct 40`, tz-aware UTC datetime; and a missing/`None` `last_updated` -> `None`.
  - `test_normalise_status` parametrised (Review Focus 3): `RUNNING`, `OPERATE`, `ONLINE`, `running` -> `running`; `FULL`, `full` -> `full`; `ERROR`, `offline`, `""`, `None`, `"SOMETHING_NEW"` -> `offline`.
  - `test_busiest_fill`: fills 20 and 65 -> 65; single -> that value; `[]` -> `None` (Review Focus 1).
  - `test_is_bin_full`: `("full", [20])` True; `("running", [100])` True; `("running", [99])` False; `("running", [20, 100])` True; `("offline", [])` False; `("running", [])` False.
- [ ] **Step 2: Run to verify failure.** `.venv/bin/python -m pytest tests/test_models.py -v` -> FAIL (module missing).
- [ ] **Step 3: Implement `models.py`.** Parse timestamps with `datetime.fromisoformat` (handles the `Z` suffix on 3.14); `parse_machine` coerces `latitude`/`longitude` with `float()` and uses `record.get(...) or ""` for remarks/hours.
- [ ] **Step 4: Run to verify pass,** plus `.venv/bin/ruff check .`.
- [ ] **Step 5: Commit** `feat: models and status logic`.

---

### Task 3: Async API client

**Files:**
- Create: `custom_components/returnright_rvm/api.py`, `tests/test_api.py`
- Create: `tests/fixtures/{map_token,access_token,nearby_1500,bin_status_1157,bin_status_1203,blocked_response,invalid_token_response}` (copied from `/tmp/rvm-fixtures/`; JSON files keep `.json`, the two `.txt` stay `.txt`) and `tests/fixtures/nearby_statuses.json`

**Interfaces:**
- Consumes: `models.parse_machine`, `models.parse_compartment`, `const.BASE_URL`, `const.ONEMAP_URL`.
- Produces (`api.py`):
  - `Tokens(uuid: str, token: str)` frozen dataclass
  - `RvmError(Exception)`; subclasses `RvmConnectionError`, `RvmBlockedError`, `RvmAuthError`, `RvmPostcodeNotFoundError`
  - `class RvmClient` with `__init__(self, session)`, `async get_tokens(self) -> Tokens`, `async nearby(self, tokens: Tokens, lat: float, lng: float, radius_m: int) -> list[Machine]`, `async bin_status(self, tokens: Tokens, rvm_id: int) -> list[Compartment]`, `async geocode(self, postcode: str) -> tuple[float, float, str]` (lat, lng, address), `async close(self) -> None`
  - `make_session() -> AsyncSession` (`curl_cffi.requests.AsyncSession(impersonate="chrome")`)
- The `session` only needs `async get(url, headers=None)` returning an object with `.status_code`, `.headers` (mapping), `.text`, `.json()`, and `async close()`, so tests use a stub.

Error classification (decided here, from the recorded live responses): a transport exception from `session.get` -> `RvmConnectionError`; HTTP 403 with a non-JSON content type (the gateway's HTML page) or any 200 whose body is not JSON -> `RvmBlockedError`; HTTP 403 with a JSON body (`{"status":"fail","message":"Forbidden"}`, the bad-token reply) -> `RvmAuthError`; any other non-200 -> `RvmConnectionError`.

- [ ] **Step 1: Copy fixtures** from `/tmp/rvm-fixtures/` into `tests/fixtures/`. `nearby_statuses.json`: build by hand a `{"status":"ok","data":[...]}` with four machines taken from `nearby_5000.json` (ids 1156 `FULL`, 2820 `ERROR`, 3098 `offline`, plus one `RUNNING` with `null` remarks and hours if present, otherwise edit one). Confirm the access-token fixture holds only `REDACTED-*` values.
- [ ] **Step 2: Write failing tests** in `tests/test_api.py` with a `StubSession` (queue of canned responses, records requested URLs and headers):
  - `test_get_tokens_chains_map_token_then_access_token`: URLs requested in order `.../map-token`, `.../{uuid}/locations/access-token`; returns `Tokens`; both carry `x-bcrs-client: web`.
  - `test_nearby_sends_token_header_and_parses_all_machines`: using `nearby_1500.json`, returns 18 `Machine`s, first has `id == 1203`; request URL contains `lat=`, `lng=`, `radius=1500`; header `x-bcrs-map-token` equals the token.
  - `test_bin_status_returns_compartments`: `bin_status_1157.json` -> one `Compartment("CAN PET", 40, ...)`; URL ends `/locations/rvms/1157/bin-status`.
  - `test_bin_status_empty_data_returns_empty_list`.
  - `test_forbidden_html_is_blocked`: `blocked_response.txt` body with content type `text/html` and status 403 -> `RvmBlockedError`.
  - `test_forbidden_json_is_auth_error`: `invalid_token_response.txt` -> `RvmAuthError` (not Blocked).
  - `test_200_with_non_json_body_is_blocked`; `test_500_is_connection_error`; `test_transport_exception_is_connection_error`.
  - `test_geocode_returns_lat_lng_address`: OneMap-shaped stub (`{"results":[{"LATITUDE":"1.35","LONGITUDE":"103.87","ADDRESS":"X"}]}`) -> `(1.35, 103.87, "X")`; empty `results` -> `RvmPostcodeNotFoundError`.
  - `test_close_closes_session`.
- [ ] **Step 3: Run to verify failure,** then **Step 4: implement `api.py`** (private helper `_get_json(url, headers) -> Any` applies the classification above; `geocode` does not use the bot-protection headers but uses the same session). **Step 5: run to verify pass** and `ruff check .`.
- [ ] **Step 6: Commit** `feat: async upstream client with recorded fixtures`.

---

### Task 4: Coordinator

**Files:**
- Create: `custom_components/returnright_rvm/coordinator.py`, `tests/test_coordinator.py`
- Modify: `custom_components/returnright_rvm/translations/en.json` (add `issues.upstream_blocked.{title,description}`), `tests/conftest.py` (fixtures building a `MockConfigEntry` and a fake client)

**Interfaces:**
- Consumes: `RvmClient`, `Tokens`, `RvmError` subclasses, `Machine`, `MachineData`, `const.*`.
- Produces (`coordinator.py`):
  - `type RvmConfigEntry = ConfigEntry[RvmCoordinator]`
  - `class RvmCoordinator(DataUpdateCoordinator[dict[int, MachineData]])` with `__init__(self, hass: HomeAssistant, entry: RvmConfigEntry, client: RvmClient)` (passes `config_entry=entry`; interval from `entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_MIN)` minutes) and `async _async_update_data(self) -> dict[int, MachineData]`.
- Entry data shape (used by Tasks 5-6): `entry.data[CONF_MACHINES] = [{"id": int, "name": str, "lat": float, "lng": float, "radius": int}]`, where `lat`/`lng`/`radius` are the search origin the machine was picked from.
- The returned dict contains only machines that fully succeeded this cycle; entities read availability from `rvm_id in coordinator.data`.

Cycle: `get_tokens()` once; group configured machines by `(lat, lng, radius)`; one `nearby` per group; for each configured machine found in its group's results, `bin_status`. A `RvmError` from `get_tokens` or `nearby` fails the whole cycle (`UpdateFailed` with `translation_domain=DOMAIN`, `translation_key` `cannot_connect` / `upstream_blocked` / `auth_failed`). A `RvmError` from one `bin_status` drops only that machine. A configured machine absent from `nearby` is dropped (Review Focus 4). A counter of consecutive cycles that raised `RvmBlockedError` reaching `BLOCKED_CYCLES_BEFORE_REPAIR` creates a Repairs issue `ISSUE_UPSTREAM_BLOCKED` (`IssueSeverity.WARNING`, `is_fixable=False`, `translation_key="upstream_blocked"`); any non-blocked cycle resets the counter and deletes the issue.

- [ ] **Step 1: Write failing tests** with a `FakeClient` (scriptable results/exceptions per method, counts calls):
  - `test_success_returns_data_keyed_by_id`
  - `test_tokens_fetched_once_per_cycle_for_many_machines`: 3 machines -> `get_tokens` called once, `bin_status` called 3 times.
  - `test_machines_sharing_an_origin_share_one_nearby_call`; `test_distinct_origins_each_get_a_nearby_call`.
  - `test_one_bin_status_failure_drops_only_that_machine`
  - `test_machine_missing_from_nearby_is_dropped_and_cycle_succeeds` (Review Focus 4)
  - `test_connection_error_raises_update_failed` / `test_auth_error_raises_update_failed`
  - `test_blocked_three_cycles_creates_repair_issue` (issue absent after 2 cycles, present after 3), and `test_success_after_blocked_deletes_issue_and_resets_counter`.
  - `test_scan_interval_comes_from_options`: `entry.options = {CONF_SCAN_INTERVAL: 15}` -> `coordinator.update_interval == timedelta(minutes=15)`; default is 10 minutes.
- [ ] **Step 2: Run to verify failure,** then **Step 3: implement** `coordinator.py` and the `issues` strings. **Step 4: run to verify pass** and `ruff check .`.
- [ ] **Step 5: Commit** `feat: coordinator with partial-failure handling and blocked-upstream repair`.

---

### Task 5: Config flow and options flow

**Files:**
- Create: `custom_components/returnright_rvm/config_flow.py`, `tests/test_config_flow.py`
- Modify: `custom_components/returnright_rvm/translations/en.json` (`config.*`, `options.*`)

**Interfaces:**
- Consumes: `RvmClient`, `make_session`, `Tokens`, `Machine`, `RvmError` subclasses, `const.*`, entry data shape from Task 4.
- Produces: `RvmConfigFlow(ConfigFlow, domain=DOMAIN)` with `async_step_user` (postcode form -> `geocode` -> tokens -> `nearby(SEARCH_RADIUS_M)`) and `async_step_pick_machines` (multi-select, options labelled `"{name} - {distance:.0f} m - {address} ({status})"`, at least one required); creates an entry titled `Return Right RVM` with `data={CONF_MACHINES: [...]}` and `options={CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL_MIN}`. Form errors: `postcode_not_found`, `no_machines`, `cannot_connect`, `upstream_blocked`, `no_selection`.
- Produces: `RvmOptionsFlow(OptionsFlowWithReload)` returned by `async_get_options_flow(config_entry)` with no args to the flow class. Menu steps: `interval` (number, `MIN`..`MAX` minutes), `add_machines` (postcode -> pick; skips ids already selected, Review Focus 5), `remove_machines` (multi-select of current machines; error `cannot_remove_all` if it would empty the list). Adding/removing writes `CONF_MACHINES` via `hass.config_entries.async_update_entry(self.config_entry, data=...)` before creating the options entry.

- [ ] **Step 1: Write failing tests** (patch `RvmClient` with a fake; use `hass.config_entries.flow` and `.options`):
  - `test_user_flow_creates_entry_with_selected_machines`: asserts `result["type"] == FlowResultType.CREATE_ENTRY`, title, `data[CONF_MACHINES]` entries have `id`, `name`, float `lat`/`lng` (the geocoded origin), `radius == 1500`, and options default interval 10.
  - `test_unknown_postcode_shows_postcode_not_found`; `test_no_machines_nearby_shows_no_machines`; `test_connection_error_shows_cannot_connect`; `test_blocked_shows_upstream_blocked`; `test_submitting_no_machines_shows_no_selection`.
  - `test_second_setup_is_aborted` (`single_instance_allowed`).
  - `test_options_interval_is_saved`; `test_options_rejects_interval_below_5` (schema validation error).
  - `test_options_add_machines_merges_and_ignores_duplicates`
  - `test_options_remove_machines_updates_entry_data`; `test_options_remove_all_is_refused` (Review Focus 5).
- [ ] **Step 2: Run to verify failure,** **Step 3: implement,** **Step 4: run to verify pass** and `ruff check .`. Strings in `en.json` are written out in full (no `[%key:...%]`).
- [ ] **Step 5: Commit** `feat: config and options flows`.

---

### Task 6: Integration setup, teardown and base entity

**Files:**
- Modify: `custom_components/returnright_rvm/__init__.py`
- Create: `custom_components/returnright_rvm/entity.py`, `tests/test_init.py`

**Interfaces:**
- Consumes: `RvmClient`, `make_session`, `RvmCoordinator`, `RvmConfigEntry`, `const.*`.
- Produces: `async_setup_entry(hass, entry: RvmConfigEntry) -> bool` (create session + client, build coordinator, `await coordinator.async_config_entry_first_refresh()`, set `entry.runtime_data`, remove stale devices, forward platforms `[Platform.SENSOR, Platform.BINARY_SENSOR]`, register `entry.async_on_unload(client.close)`); `async_unload_entry`; `async_remove_config_entry_device(hass, entry, device_entry) -> bool` (True only if the device's machine id is no longer configured).
- Produces (`entity.py`): `class RvmEntity(CoordinatorEntity[RvmCoordinator])` with `_attr_has_entity_name = True`, `__init__(self, coordinator: RvmCoordinator, rvm_id: int, key: str)`, `unique_id == f"{rvm_id}_{key}"`, `device_info` (identifiers `(DOMAIN, str(rvm_id))`, name = machine name, manufacturer `"Return Right (BCRS)"`), `machine_data -> MachineData | None`, and `available` true only when `rvm_id in coordinator.data`.
- Machine name for `device_info` comes from `coordinator.data[rvm_id].machine.name`, falling back to the name stored in `entry.data`.

- [ ] **Step 1: Write failing tests** (patched client):
  - `test_setup_and_unload_entry`: entry reaches `LOADED`, then `NOT_LOADED`; the fake session's `close` was awaited.
  - `test_setup_retries_when_first_refresh_fails`: entry state `SETUP_RETRY`.
  - `test_stale_devices_are_removed_at_setup`: pre-register a device for machine 999 under the entry, set up with only machine 1203 configured -> device 999 gone, 1203 kept.
  - `test_remove_config_entry_device_only_for_deselected_machines`.
- [ ] **Step 2: Run to verify failure,** **Step 3: implement,** **Step 4: run to verify pass** and `ruff check .`.
- [ ] **Step 5: Commit** `feat: entry setup/teardown, stale-device cleanup, base entity`.

---

### Task 7: Sensors

**Files:**
- Create: `custom_components/returnright_rvm/sensor.py`, `tests/test_sensor.py`
- Modify: `custom_components/returnright_rvm/translations/en.json` (`entity.sensor.*`)

**Interfaces:**
- Consumes: `RvmEntity`, `MachineData`, `normalise_status`, `busiest_fill`, `STATUS_*`.
- Produces: platform `async_setup_entry(hass, entry, async_add_entities)` that adds, per machine: `status` (`SensorDeviceClass.ENUM`, options `[running, full, offline]`, attributes `raw_status`, `address`, `remarks`, `opening_hours`), `busiest_fill` (`%`, `SensorStateClass.MEASUREMENT`, `None` when no compartments), `bin_last_updated` (`SensorDeviceClass.TIMESTAMP`, `EntityCategory.DIAGNOSTIC`, disabled by default, newest compartment `last_updated`), and one `compartment_fill` per compartment type (`translation_key="compartment_fill"`, placeholder `compartment` = the type title-cased, `unique_id = f"{rvm_id}_fill_{slug(type)}"`, attribute `last_updated`). New machines or compartments appearing after setup are added through a coordinator listener with a `known` set; ids missing from the data are discarded from `known` so they are re-added if they return.

- [ ] **Step 1: Write failing tests** (setup a loaded entry with a fake client):
  - `test_status_sensor_state_and_attributes`: `RUNNING` -> `running`; attributes include raw `RUNNING`, remarks, opening hours.
  - `test_status_sensor_maps_unknown_statuses_to_offline` (`ERROR`, lowercase `offline`) (Review Focus 3).
  - `test_busiest_fill_is_max_compartment`; `test_zero_compartments_gives_unknown_busiest_and_no_compartment_entities` (Review Focus 1).
  - `test_one_fill_sensor_per_compartment_type` with `CAN PET` and `GLASS`, state `40`, entity name contains `Can Pet`.
  - `test_new_compartment_appearing_later_adds_entity_without_reload`.
  - `test_entities_unavailable_when_machine_dropped_from_data` and recover when it returns.
  - `test_last_updated_sensor_disabled_by_default`.
- [ ] **Step 2: Run to verify failure,** **Step 3: implement,** **Step 4: run to verify pass** and `ruff check .`.
- [ ] **Step 5: Commit** `feat: status and fill sensors`.

---

### Task 8: Bin full binary sensor

**Files:**
- Create: `custom_components/returnright_rvm/binary_sensor.py`, `tests/test_binary_sensor.py`
- Modify: `custom_components/returnright_rvm/translations/en.json` (`entity.binary_sensor.bin_full.name`)

**Interfaces:**
- Consumes: `RvmEntity`, `models.is_bin_full`, `normalise_status`.
- Produces: one `bin_full` binary sensor per machine, state `is_bin_full(normalise_status(raw_status), compartments)`; same `known`-set dynamic-add listener as Task 7.

- [ ] **Step 1: Write failing tests:** `test_on_when_status_full_even_at_low_fill`; `test_on_when_running_machine_at_exactly_100`; `test_off_at_99`; `test_off_with_zero_compartments` (Review Focus 1); `test_unavailable_when_machine_dropped`.
- [ ] **Step 2: Run to verify failure,** **Step 3: implement,** **Step 4: run to verify pass** and `ruff check .`.
- [ ] **Step 5: Commit** `feat: bin full binary sensor`.

---

### Task 9: README, brand icon and release readiness

**Files:**
- Modify: `README.md`
- Create: `custom_components/returnright_rvm/brand/icon.png`, `CHANGELOG.md`

- [ ] **Step 1: Write the README.** Sections: what it does; install as a HACS custom repository (repository URL, category Integration); setup (postcode, pick machines); entities table (as in the spec); options (interval, add/remove machines); known limits (Singapore BCRS only, 32-bit Alpine unsupported because `curl_cffi` publishes no musl armv7l wheel, 5 minute polling floor); the disclaimer (unofficial, not affiliated with the operator, undocumented API that may change, polls gently on purpose); troubleshooting for the Repairs issue "upstream blocking requests".
- [ ] **Step 2: Add `brand/icon.png`** (256x256, trimmed, optimised) supplied by Royce. If none was supplied, generate a plain placeholder with a throwaway script outside the repo and tell Royce it is a placeholder.
- [ ] **Step 3: `CHANGELOG.md`** with a `0.1.0` entry listing the entities and flows.
- [ ] **Step 4: Run the whole suite and lint.** `.venv/bin/python -m pytest -v` all PASS; `.venv/bin/ruff check .` clean. Hassfest and the HACS action only run in CI after the first push; read their results there and fix any finding.
- [ ] **Step 5: Commit** `docs: README, changelog, brand icon`.

---

### Task 10: Private v0.1 install and release (needs Royce's go-ahead)

**Files:** none (repository settings and a tag).

- [ ] **Step 1 (Royce):** push to GitHub; set the repo description, topics (`home-assistant`, `hacs`, `integration`) and enable issues, which the HACS action checks. Confirm the `Validate` and `tests` workflows are green.
- [ ] **Step 2 (Royce):** in your Home Assistant, HACS -> Custom repositories -> add the repo as Integration; install; restart; add the integration with your postcode and pick your machines. Expected: devices appear with the status, fill and bin-full entities.
- [ ] **Step 3 (Royce):** run for about a week. Watch for the Repairs "upstream blocking" issue, unavailable entities and log warnings; record problems as issues.
- [ ] **Step 4:** only after that week and Royce's explicit approval, tag `v0.1.0` and create a GitHub release. Submitting to the HACS default list is a separate later decision.
