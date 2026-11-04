"""Placeholder binary_sensor platform; Task 8 replaces it."""

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import RvmConfigEntry


async def async_setup_entry(
    hass: HomeAssistant, entry: RvmConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    """Add nothing; Task 8 replaces this stub."""
