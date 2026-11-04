"""Tests for the Return Right RVM config and options flows."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.data_entry_flow import FlowResultType, InvalidData
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.returnright_rvm.api import (
    RvmBlockedError,
    RvmConnectionError,
    RvmPostcodeNotFoundError,
    Tokens,
)
from custom_components.returnright_rvm.const import (
    CONF_MACHINES,
    CONF_SCAN_INTERVAL,
    DOMAIN,
    POLL_RADIUS_M,
    SEARCH_RADIUS_M,
)

from .conftest import make_machine

ORIGIN = (1.3, 103.8)


class FlowClient:
    """Scriptable RvmClient stand-in for flows."""

    def __init__(self) -> None:
        self.geocode_result = (*ORIGIN, "1 Test Road")
        self.tokens_error: Exception | None = None
        self.machines = [make_machine(1), make_machine(2)]
        self.closed = 0
        self.nearby_radii: list[int] = []

    async def geocode(self, postcode):
        if isinstance(self.geocode_result, Exception):
            raise self.geocode_result
        return self.geocode_result

    async def get_tokens(self):
        if self.tokens_error:
            raise self.tokens_error
        return Tokens(uuid="u", token="t")

    async def nearby(self, tokens, lat, lng, radius_m):
        self.nearby_radii.append(radius_m)
        return self.machines

    async def close(self):
        self.closed += 1


@pytest.fixture
def client():
    fake = FlowClient()
    fake.setup = AsyncMock(return_value=True)
    with (
        patch("custom_components.returnright_rvm.config_flow.RvmClient", lambda s: fake),
        patch("custom_components.returnright_rvm.config_flow.make_session"),
        patch(
            "custom_components.returnright_rvm.async_setup_entry",
            fake.setup,
            create=True,
        ),
        patch(
            "custom_components.returnright_rvm.async_unload_entry",
            AsyncMock(return_value=True),
            create=True,
        ),
    ):
        yield fake


def _spec(rvm_id):
    return {
        "id": rvm_id,
        "name": f"RVM {rvm_id}",
        "lat": ORIGIN[0],
        "lng": ORIGIN[1],
        "radius": POLL_RADIUS_M,
    }


async def _start(hass, postcode="123456"):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    return await hass.config_entries.flow.async_configure(result["flow_id"], {"postcode": postcode})


async def test_user_flow_creates_entry_with_selected_machines(hass, client):
    result = await _start(hass)
    assert result["step_id"] == "pick_machines"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_MACHINES: ["2"]}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Return Right RVM"
    (machine,) = result["data"][CONF_MACHINES]
    assert machine == {
        "id": 2,
        "name": "RVM 2",
        "lat": ORIGIN[0],
        "lng": ORIGIN[1],
        "radius": POLL_RADIUS_M,
    }
    assert isinstance(machine["lat"], float)
    assert result["options"] == {CONF_SCAN_INTERVAL: 5}
    assert client.closed >= 1


async def test_flow_searches_with_search_radius_but_stores_poll_radius(hass, client):
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_MACHINES: ["2"]}
    )
    assert client.nearby_radii == [SEARCH_RADIUS_M] == [1500]
    assert result["data"][CONF_MACHINES][0]["radius"] == POLL_RADIUS_M == 2000


@pytest.mark.parametrize(
    ("setup", "error"),
    [
        ("postcode", "postcode_not_found"),
        ("empty", "no_machines"),
        ("connect", "cannot_connect"),
        ("blocked", "upstream_blocked"),
    ],
)
async def test_user_flow_errors(hass, client, setup, error):
    if setup == "postcode":
        client.geocode_result = RvmPostcodeNotFoundError("x")
    elif setup == "empty":
        client.machines = []
    elif setup == "connect":
        client.tokens_error = RvmConnectionError("x")
    else:
        client.tokens_error = RvmBlockedError("x")
    result = await _start(hass)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": error}
    assert client.closed >= 1


async def test_submitting_no_machines_shows_no_selection(hass, client):
    result = await _start(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_MACHINES: []})
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "no_selection"}


async def test_second_setup_is_aborted(hass, client):
    MockConfigEntry(domain=DOMAIN, data={CONF_MACHINES: []}).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


async def _options(hass, make_entry, specs=(1,)):
    entry = make_entry([_spec(i) for i in specs], {CONF_SCAN_INTERVAL: 10})
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.MENU
    return entry, result


async def _menu(hass, result, option):
    return await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": option}
    )


async def test_options_interval_is_saved(hass, client, make_entry):
    entry, result = await _options(hass, make_entry)
    result = await _menu(hass, result, "interval")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SCAN_INTERVAL: 30}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_SCAN_INTERVAL] == 30


async def test_options_accepts_one_minute_interval(hass, client, make_entry):
    entry, result = await _options(hass, make_entry)
    result = await _menu(hass, result, "interval")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SCAN_INTERVAL: 1}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_SCAN_INTERVAL] == 1


async def test_options_rejects_interval_below_1(hass, client, make_entry):
    _, result = await _options(hass, make_entry)
    result = await _menu(hass, result, "interval")
    with pytest.raises(InvalidData):
        await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_SCAN_INTERVAL: 0}
        )


async def test_options_add_machines_merges_and_ignores_duplicates(hass, client, make_entry):
    client.machines = [make_machine(1), make_machine(2), make_machine(3)]
    entry, result = await _options(hass, make_entry)
    result = await _menu(hass, result, "add_machines")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"postcode": "123456"}
    )
    assert result["step_id"] == "pick_machines"
    offered = [o["value"] for o in result["data_schema"].schema[CONF_MACHINES].config["options"]]
    assert offered == ["2", "3"]
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_MACHINES: ["2"]}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert [m["id"] for m in entry.data[CONF_MACHINES]] == [1, 2]
    assert entry.data[CONF_MACHINES][1]["lat"] == ORIGIN[0]


async def test_options_add_machines_only_duplicates_shows_no_machines(hass, client, make_entry):
    client.machines = [make_machine(1)]
    _, result = await _options(hass, make_entry)
    result = await _menu(hass, result, "add_machines")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"postcode": "123456"}
    )
    assert result["errors"] == {"base": "no_machines"}


async def test_options_remove_machines_updates_entry_data(hass, client, make_entry):
    entry, result = await _options(hass, make_entry, specs=(1, 2))
    result = await _menu(hass, result, "remove_machines")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_MACHINES: ["1"]}
    )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert [m["id"] for m in entry.data[CONF_MACHINES]] == [2]


async def test_options_remove_all_is_refused(hass, client, make_entry):
    entry, result = await _options(hass, make_entry, specs=(1, 2))
    result = await _menu(hass, result, "remove_machines")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_MACHINES: ["1", "2"]}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_remove_all"}
    assert len(entry.data[CONF_MACHINES]) == 2


async def _reloads(hass, client, make_entry, option, step_input, specs=(1,)):
    """Run an options step and return how many extra setups it caused."""
    client.machines = [make_machine(1), make_machine(2)]
    _, result = await _options(hass, make_entry, specs=specs)
    before = client.setup.call_count
    result = await _menu(hass, result, option)
    if option == "add_machines":
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"postcode": "123456"}
        )
    await hass.config_entries.options.async_configure(result["flow_id"], step_input)
    await hass.async_block_till_done()
    return client.setup.call_count - before


async def test_options_add_machines_reloads_entry(hass, client, make_entry):
    assert await _reloads(hass, client, make_entry, "add_machines", {CONF_MACHINES: ["2"]}) == 1


async def test_options_remove_machines_reloads_entry(hass, client, make_entry):
    assert (
        await _reloads(hass, client, make_entry, "remove_machines", {CONF_MACHINES: ["1"]}, (1, 2))
        == 1
    )


async def test_options_interval_reloads_entry_once(hass, client, make_entry):
    assert await _reloads(hass, client, make_entry, "interval", {CONF_SCAN_INTERVAL: 30}) == 1
