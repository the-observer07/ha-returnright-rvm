"""Tests for the Return Right RVM sensors."""

from dataclasses import replace
from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from custom_components.returnright_rvm.models import Compartment

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


async def _setup(hass: HomeAssistant, make_entry):
    entry = make_entry([MACHINE])
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _refresh(hass: HomeAssistant, entry) -> None:
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()


async def test_status_sensor_state_and_attributes(
    hass: HomeAssistant, make_entry, patched_client
) -> None:
    patched_client.nearby_results[(1.30, 103.80)] = [
        replace(make_machine(1203), remarks="Near lift", opening_hours="24h")
    ]
    await _setup(hass, make_entry)

    state = hass.states.get("sensor.rvm_1203_status")
    assert state.state == "running"
    assert state.attributes["raw_status"] == "RUNNING"
    assert state.attributes["address"] == "1 Test Road"
    assert state.attributes["remarks"] == "Near lift"
    assert state.attributes["opening_hours"] == "24h"


@pytest.mark.parametrize("raw", ["ERROR", "offline", None])
async def test_status_sensor_maps_unknown_statuses_to_offline(
    hass: HomeAssistant, make_entry, patched_client, raw
) -> None:
    patched_client.nearby_results[(1.30, 103.80)] = [replace(make_machine(1203), raw_status=raw)]
    await _setup(hass, make_entry)

    assert hass.states.get("sensor.rvm_1203_status").state == "offline"


async def test_busiest_fill_is_max_compartment(
    hass: HomeAssistant, make_entry, patched_client
) -> None:
    patched_client.bin_results[1203] = [
        replace(make_compartment(), type="CAN", fill_pct=40),
        replace(make_compartment(), type="GLASS", fill_pct=85),
    ]
    await _setup(hass, make_entry)

    state = hass.states.get("sensor.rvm_1203_busiest_fill")
    assert state.state == "85"
    assert state.attributes["unit_of_measurement"] == "%"


async def test_zero_compartments_gives_unknown_busiest_and_no_compartment_entities(
    hass: HomeAssistant, make_entry, patched_client
) -> None:
    patched_client.bin_results[1203] = []
    entry = await _setup(hass, make_entry)

    assert hass.states.get("sensor.rvm_1203_busiest_fill").state == STATE_UNKNOWN
    registry = er.async_get(hass)
    unique_ids = {e.unique_id for e in er.async_entries_for_config_entry(registry, entry.entry_id)}
    assert not any("_fill_" in uid for uid in unique_ids)


async def test_one_fill_sensor_per_compartment_type(
    hass: HomeAssistant, make_entry, patched_client
) -> None:
    patched_client.bin_results[1203] = [
        replace(make_compartment(), type="CAN PET", fill_pct=40),
        replace(make_compartment(), type="GLASS", fill_pct=10),
    ]
    entry = await _setup(hass, make_entry)

    state = hass.states.get("sensor.rvm_1203_can_pet_fill")
    assert state.state == "40"
    assert "Can Pet" in state.attributes["friendly_name"]
    assert state.attributes["last_updated"] == "2026-01-01T00:00:00+00:00"
    assert hass.states.get("sensor.rvm_1203_glass_fill").state == "10"
    registry = er.async_get(hass)
    assert registry.async_get_entity_id("sensor", entry.domain, "1203_fill_can_pet")
    assert registry.async_get_entity_id("sensor", entry.domain, "1203_fill_glass")


async def test_new_compartment_appearing_later_adds_entity_without_reload(
    hass: HomeAssistant, make_entry, patched_client
) -> None:
    entry = await _setup(hass, make_entry)
    assert hass.states.get("sensor.rvm_1203_glass_fill") is None

    patched_client.bin_results[1203] = [
        make_compartment(),
        replace(make_compartment(), type="GLASS", fill_pct=55),
    ]
    await _refresh(hass, entry)

    assert hass.states.get("sensor.rvm_1203_glass_fill").state == "55"


async def test_entities_unavailable_when_machine_dropped_from_data(
    hass: HomeAssistant, make_entry, patched_client
) -> None:
    entry = await _setup(hass, make_entry)
    assert hass.states.get("sensor.rvm_1203_status").state == "running"

    patched_client.nearby_results[(1.30, 103.80)] = []
    await _refresh(hass, entry)
    assert hass.states.get("sensor.rvm_1203_status").state == STATE_UNAVAILABLE
    assert hass.states.get("sensor.rvm_1203_busiest_fill").state == STATE_UNAVAILABLE

    patched_client.nearby_results[(1.30, 103.80)] = [make_machine(1203)]
    await _refresh(hass, entry)
    assert hass.states.get("sensor.rvm_1203_status").state == "running"
    assert hass.states.get("sensor.rvm_1203_busiest_fill").state == "40"


async def test_compartment_returning_after_absence_is_available_again(
    hass: HomeAssistant, make_entry, patched_client
) -> None:
    entry = await _setup(hass, make_entry)
    patched_client.bin_results[1203] = []
    await _refresh(hass, entry)
    patched_client.bin_results[1203] = [make_compartment(60)]
    await _refresh(hass, entry)

    assert hass.states.get("sensor.rvm_1203_can_fill").state == "60"


async def test_last_updated_sensor_disabled_by_default(
    hass: HomeAssistant, make_entry, patched_client
) -> None:
    entry = await _setup(hass, make_entry)

    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id("sensor", entry.domain, "1203_bin_last_updated")
    assert entity_id
    assert registry.async_get(entity_id).disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert hass.states.get(entity_id) is None


async def test_last_updated_sensor_reports_newest_compartment(
    hass: HomeAssistant, make_entry, patched_client
) -> None:
    patched_client.bin_results[1203] = [
        Compartment("CAN", 1, datetime(2026, 1, 1, tzinfo=UTC)),
        Compartment("GLASS", 1, datetime(2026, 2, 1, tzinfo=UTC)),
        Compartment("PET", 1, None),
    ]
    entry = await _setup(hass, make_entry)
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id("sensor", entry.domain, "1203_bin_last_updated")
    registry.async_update_entity(entity_id, disabled_by=None)
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == "2026-02-01T00:00:00+00:00"
