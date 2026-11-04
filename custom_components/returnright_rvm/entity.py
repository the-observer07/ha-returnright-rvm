"""Base entity for the Return Right RVM integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_MACHINES, DOMAIN
from .coordinator import RvmCoordinator
from .models import MachineData


class RvmEntity(CoordinatorEntity[RvmCoordinator]):
    """Base class for entities belonging to one machine."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: RvmCoordinator, rvm_id: int, key: str) -> None:
        """Initialise the entity."""
        super().__init__(coordinator)
        self.rvm_id = rvm_id
        self._attr_unique_id = f"{rvm_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(rvm_id))},
            name=self._machine_name(),
            manufacturer="Return Right (BCRS)",
        )

    def _machine_name(self) -> str | None:
        data = self.machine_data
        if data is not None:
            return data.machine.name
        for conf in self.coordinator.config_entry.data[CONF_MACHINES]:
            if conf["id"] == self.rvm_id:
                return conf["name"]
        return None

    @property
    def machine_data(self) -> MachineData | None:
        """Return the latest data for this machine, if any."""
        return self.coordinator.data.get(self.rvm_id) if self.coordinator.data else None

    @property
    def available(self) -> bool:
        """Return True only while the machine is in the latest data."""
        return super().available and self.machine_data is not None
