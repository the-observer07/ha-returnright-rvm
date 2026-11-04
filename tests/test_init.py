"""Tests for Return Right RVM entry setup, teardown and device cleanup."""

from unittest.mock import patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import issue_registry as ir

from custom_components.returnright_rvm import async_remove_config_entry_device
from custom_components.returnright_rvm.api import RvmBlockedError, RvmConnectionError
from custom_components.returnright_rvm.const import DOMAIN, ISSUE_UPSTREAM_BLOCKED
from custom_components.returnright_rvm.coordinator import blocked_cycles

from .conftest import make_compartment, make_machine

MACHINE = {"id": 1203, "name": "RVM 1203", "lat": 1.30, "lng": 103.80, "radius": 2000}


@pytest.fixture
def patched_client(fake_client):
    """Patch client creation so setup uses the fake client."""
    fake_client.nearby_results[(1.30, 103.80)] = [make_machine(1203)]
    fake_client.bin_results[1203] = [make_compartment()]
    with (
        patch("custom_components.returnright_rvm.make_session"),
        patch("custom_components.returnright_rvm.RvmClient", return_value=fake_client),
    ):
        yield fake_client


async def test_setup_and_unload_entry(hass: HomeAssistant, make_entry, patched_client) -> None:
    entry = make_entry([MACHINE])
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert 1203 in entry.runtime_data.data

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
    assert patched_client.closed == 1


async def test_setup_retries_when_first_refresh_fails(
    hass: HomeAssistant, make_entry, patched_client
) -> None:
    patched_client.tokens_result = RvmConnectionError("down")
    entry = make_entry([MACHINE])
    entry.add_to_hass(hass)

    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_stale_devices_are_removed_at_setup(
    hass: HomeAssistant, make_entry, patched_client
) -> None:
    entry = make_entry([MACHINE])
    entry.add_to_hass(hass)
    registry = dr.async_get(hass)
    for rvm_id in (999, 1203):
        registry.async_get_or_create(
            config_entry_id=entry.entry_id, identifiers={(DOMAIN, str(rvm_id))}
        )

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert registry.async_get_device_by_identifier((DOMAIN, "999"), entry.entry_id) is None
    assert registry.async_get_device_by_identifier((DOMAIN, "1203"), entry.entry_id)


async def test_remove_config_entry_device_only_for_deselected_machines(
    hass: HomeAssistant, make_entry
) -> None:
    entry = make_entry([MACHINE])
    entry.add_to_hass(hass)
    registry = dr.async_get(hass)
    kept = registry.async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, "1203")}
    )
    gone = registry.async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, "999")}
    )

    assert not await async_remove_config_entry_device(hass, entry, kept)
    assert await async_remove_config_entry_device(hass, entry, gone)


async def test_three_blocked_setup_retries_create_repair_issue(
    hass: HomeAssistant, make_entry, patched_client
) -> None:
    patched_client.tokens_result = RvmBlockedError("blocked")
    entry = make_entry([MACHINE])
    entry.add_to_hass(hass)
    registry = ir.async_get(hass)

    assert not await hass.config_entries.async_setup(entry.entry_id)
    assert entry.state is ConfigEntryState.SETUP_RETRY
    for _ in range(2):
        assert registry.async_get_issue(DOMAIN, ISSUE_UPSTREAM_BLOCKED) is None
        await hass.config_entries.async_reload(entry.entry_id)
        assert entry.state is ConfigEntryState.SETUP_RETRY
    assert registry.async_get_issue(DOMAIN, ISSUE_UPSTREAM_BLOCKED) is not None


async def test_removing_entry_deletes_issue_and_clears_count(
    hass: HomeAssistant, make_entry, patched_client
) -> None:
    patched_client.tokens_result = RvmBlockedError("blocked")
    entry = make_entry([MACHINE])
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    for _ in range(2):
        await hass.config_entries.async_reload(entry.entry_id)
    registry = ir.async_get(hass)
    assert registry.async_get_issue(DOMAIN, ISSUE_UPSTREAM_BLOCKED) is not None

    await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert registry.async_get_issue(DOMAIN, ISSUE_UPSTREAM_BLOCKED) is None
    assert blocked_cycles(entry.entry_id) == 0
