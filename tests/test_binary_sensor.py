"""Tests for the Return Right RVM bin full binary sensor."""

from dataclasses import replace

from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant

from .conftest import _refresh, _setup, make_compartment, make_machine

ENTITY_ID = "binary_sensor.rvm_1203_bin_full"


async def test_on_when_status_full_even_at_low_fill(
    hass: HomeAssistant, make_entry, patched_client
) -> None:
    patched_client.nearby_results[(1.30, 103.80)] = [replace(make_machine(1203), raw_status="FULL")]
    patched_client.bin_results[1203] = [make_compartment(5)]
    await _setup(hass, make_entry)

    assert hass.states.get(ENTITY_ID).state == STATE_ON


async def test_on_when_running_machine_at_exactly_100(
    hass: HomeAssistant, make_entry, patched_client
) -> None:
    patched_client.bin_results[1203] = [make_compartment(100)]
    await _setup(hass, make_entry)

    assert hass.states.get(ENTITY_ID).state == STATE_ON


async def test_off_at_99(hass: HomeAssistant, make_entry, patched_client) -> None:
    patched_client.bin_results[1203] = [make_compartment(99)]
    await _setup(hass, make_entry)

    assert hass.states.get(ENTITY_ID).state == STATE_OFF


async def test_off_with_zero_compartments(hass: HomeAssistant, make_entry, patched_client) -> None:
    patched_client.bin_results[1203] = []
    await _setup(hass, make_entry)

    assert hass.states.get(ENTITY_ID).state == STATE_OFF


async def test_unavailable_when_machine_dropped(
    hass: HomeAssistant, make_entry, patched_client
) -> None:
    entry = await _setup(hass, make_entry)
    assert hass.states.get(ENTITY_ID).state == STATE_OFF

    patched_client.nearby_results[(1.30, 103.80)] = []
    await _refresh(hass, entry)
    assert hass.states.get(ENTITY_ID).state == STATE_UNAVAILABLE

    patched_client.nearby_results[(1.30, 103.80)] = [make_machine(1203)]
    await _refresh(hass, entry)
    assert hass.states.get(ENTITY_ID).state == STATE_OFF


async def test_machine_appearing_late_gets_entity(
    hass: HomeAssistant, make_entry, patched_client
) -> None:
    patched_client.nearby_results[(1.30, 103.80)] = []
    entry = await _setup(hass, make_entry)
    assert hass.states.get(ENTITY_ID) is None

    patched_client.nearby_results[(1.30, 103.80)] = [make_machine(1203)]
    await _refresh(hass, entry)

    assert hass.states.get(ENTITY_ID).state == STATE_OFF
