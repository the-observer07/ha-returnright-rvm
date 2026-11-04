"""Tests for Return Right RVM entry setup, teardown and device cleanup."""

from unittest.mock import patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from custom_components.returnright_rvm import async_remove_config_entry_device
from custom_components.returnright_rvm.api import RvmConnectionError
from custom_components.returnright_rvm.const import DOMAIN

from .conftest import make_compartment, make_machine

MACHINE = {"id": 1203, "name": "RVM 1203", "lat": 1.30, "lng": 103.80, "radius": 1500}


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
