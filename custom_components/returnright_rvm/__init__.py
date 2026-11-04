"""The Return Right RVM integration."""

from __future__ import annotations

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .api import RvmClient, make_session
from .const import CONF_MACHINES, DOMAIN
from .coordinator import RvmConfigEntry, RvmCoordinator

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]


def _configured_ids(entry: RvmConfigEntry) -> set[str]:
    return {str(machine["id"]) for machine in entry.data[CONF_MACHINES]}


def _device_machine_ids(device: dr.DeviceEntry) -> set[str]:
    return {ident for domain, ident in device.identifiers if domain == DOMAIN}


async def async_setup_entry(hass: HomeAssistant, entry: RvmConfigEntry) -> bool:
    """Set up Return Right RVM from a config entry."""
    client = RvmClient(make_session())
    entry.async_on_unload(client.close)

    coordinator = RvmCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    configured = _configured_ids(entry)
    device_registry = dr.async_get(hass)
    for device in dr.async_entries_for_config_entry(device_registry, entry.entry_id):
        if not _device_machine_ids(device) & configured:
            device_registry.async_remove_device(device.id)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: RvmConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: RvmConfigEntry, device_entry: dr.DeviceEntry
) -> bool:
    """Allow deleting a device only when its machine is no longer configured."""
    return not _device_machine_ids(device_entry) & _configured_ids(entry)
