"""Binary sensors for the Return Right RVM integration."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import RvmConfigEntry, RvmCoordinator
from .entity import RvmEntity
from .models import is_bin_full, normalise_status

PARALLEL_UPDATES = 0

BIN_FULL = BinarySensorEntityDescription(key="bin_full", translation_key="bin_full")


class RvmBinFullSensor(RvmEntity, BinarySensorEntity):
    """On when the machine is full or any compartment is at 100%."""

    def __init__(self, coordinator: RvmCoordinator, rvm_id: int) -> None:
        """Initialise the binary sensor."""
        super().__init__(coordinator, rvm_id, BIN_FULL.key)
        self.entity_description = BIN_FULL

    @property
    def is_on(self) -> bool | None:
        """Return True if the bin is full."""
        data = self.machine_data
        if data is None:
            return None
        return is_bin_full(normalise_status(data.machine.raw_status), data.compartments)


async def async_setup_entry(
    hass: HomeAssistant, entry: RvmConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    """Set up the binary sensors and add new machines as they appear."""
    coordinator = entry.runtime_data
    known: set[int] = set()

    @callback
    def _add_new() -> None:
        new = [
            RvmBinFullSensor(coordinator, rvm_id)
            for rvm_id in (coordinator.data or {})
            if rvm_id not in known
        ]
        known.update(sensor.rvm_id for sensor in new)
        if new:
            async_add_entities(new)

    _add_new()
    entry.async_on_unload(coordinator.async_add_listener(_add_new))
