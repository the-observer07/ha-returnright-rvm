"""Sensors for the Return Right RVM integration."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import STATUS_FULL, STATUS_OFFLINE, STATUS_RUNNING
from .coordinator import RvmConfigEntry, RvmCoordinator
from .entity import RvmEntity
from .models import Compartment, MachineData, busiest_fill, normalise_status

PARALLEL_UPDATES = 0


def _newest_update(data: MachineData) -> datetime | None:
    stamps = [c.last_updated for c in data.compartments if c.last_updated]
    return max(stamps, default=None)


def _status_attributes(data: MachineData) -> dict[str, Any]:
    machine = data.machine
    return {
        "raw_status": machine.raw_status,
        "address": machine.address,
        "remarks": machine.remarks,
        "opening_hours": machine.opening_hours,
    }


@dataclass(frozen=True, kw_only=True)
class RvmSensorDescription(SensorEntityDescription):
    """Describes a per-machine sensor."""

    value_fn: Callable[[MachineData], str | int | datetime | None]
    attributes_fn: Callable[[MachineData], dict[str, Any]] | None = None


SENSORS: tuple[RvmSensorDescription, ...] = (
    RvmSensorDescription(
        key="status",
        translation_key="status",
        device_class=SensorDeviceClass.ENUM,
        options=[STATUS_RUNNING, STATUS_FULL, STATUS_OFFLINE],
        value_fn=lambda data: normalise_status(data.machine.raw_status),
        attributes_fn=_status_attributes,
    ),
    RvmSensorDescription(
        key="busiest_fill",
        translation_key="busiest_fill",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: busiest_fill(data.compartments),
    ),
    RvmSensorDescription(
        key="bin_last_updated",
        translation_key="bin_last_updated",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_newest_update,
    ),
)


def _slug(compartment_type: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", compartment_type.lower()).strip("_")


class RvmSensor(RvmEntity, SensorEntity):
    """A per-machine sensor."""

    entity_description: RvmSensorDescription

    def __init__(
        self, coordinator: RvmCoordinator, rvm_id: int, description: RvmSensorDescription
    ) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, rvm_id, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> str | int | datetime | None:
        """Return the sensor value."""
        data = self.machine_data
        return self.entity_description.value_fn(data) if data else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return extra attributes, if the sensor defines any."""
        data = self.machine_data
        fn = self.entity_description.attributes_fn
        return fn(data) if data and fn else None


class RvmCompartmentSensor(RvmEntity, SensorEntity):
    """Fill level of one compartment type."""

    _attr_translation_key = "compartment_fill"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator: RvmCoordinator, rvm_id: int, compartment_type: str) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator, rvm_id, f"fill_{_slug(compartment_type)}")
        self.compartment_type = compartment_type
        self._attr_translation_placeholders = {"compartment": compartment_type.title()}

    @property
    def _compartment(self) -> Compartment | None:
        data = self.machine_data
        if data is None:
            return None
        return next((c for c in data.compartments if c.type == self.compartment_type), None)

    @property
    def native_value(self) -> int | None:
        """Return the fill percentage."""
        compartment = self._compartment
        return compartment.fill_pct if compartment else None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return when the compartment was last updated."""
        compartment = self._compartment
        if compartment is None:
            return None
        updated = compartment.last_updated
        return {"last_updated": updated.isoformat() if updated else None}


async def async_setup_entry(
    hass: HomeAssistant, entry: RvmConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    """Set up sensors and add new machines or compartments as they appear."""
    coordinator = entry.runtime_data
    known: set[str] = set()

    @callback
    def _add_new() -> None:
        new: list[SensorEntity] = []
        for rvm_id, data in (coordinator.data or {}).items():
            for description in SENSORS:
                uid = f"{rvm_id}_{description.key}"
                if uid not in known:
                    known.add(uid)
                    new.append(RvmSensor(coordinator, rvm_id, description))
            for compartment in data.compartments:
                uid = f"{rvm_id}_fill_{_slug(compartment.type)}"
                if uid not in known:
                    known.add(uid)
                    new.append(RvmCompartmentSensor(coordinator, rvm_id, compartment.type))
        if new:
            async_add_entities(new)

    _add_new()
    entry.async_on_unload(coordinator.async_add_listener(_add_new))
