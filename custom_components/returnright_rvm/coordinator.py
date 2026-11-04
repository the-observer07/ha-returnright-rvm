"""Data update coordinator for the Return Right RVM integration."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import RvmAuthError, RvmBlockedError, RvmClient, RvmError
from .const import (
    BLOCKED_CYCLES_BEFORE_REPAIR,
    CONF_MACHINES,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL_MIN,
    DOMAIN,
    ISSUE_UPSTREAM_BLOCKED,
)
from .models import MachineData

_LOGGER = logging.getLogger(__name__)

type RvmConfigEntry = ConfigEntry[RvmCoordinator]


def _failure(err: RvmError) -> UpdateFailed:
    """Translate an upstream error into UpdateFailed."""
    if isinstance(err, RvmBlockedError):
        key = "upstream_blocked"
    elif isinstance(err, RvmAuthError):
        key = "auth_failed"
    else:
        key = "cannot_connect"
    return UpdateFailed(translation_domain=DOMAIN, translation_key=key)


class RvmCoordinator(DataUpdateCoordinator[dict[int, MachineData]]):
    """Poll the configured machines; data holds only fully successful ones."""

    config_entry: RvmConfigEntry

    def __init__(self, hass: HomeAssistant, entry: RvmConfigEntry, client: RvmClient) -> None:
        """Initialise the coordinator."""
        minutes = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_MIN)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(minutes=minutes),
        )
        self.client = client
        self._blocked_cycles = 0

    async def _async_update_data(self) -> dict[int, MachineData]:
        """Fetch status for every configured machine."""
        try:
            data = await self._fetch()
        except RvmBlockedError as err:
            self._blocked_cycles += 1
            if self._blocked_cycles >= BLOCKED_CYCLES_BEFORE_REPAIR:
                ir.async_create_issue(
                    self.hass,
                    DOMAIN,
                    ISSUE_UPSTREAM_BLOCKED,
                    is_fixable=False,
                    severity=ir.IssueSeverity.WARNING,
                    translation_key="upstream_blocked",
                )
            raise _failure(err) from err
        except RvmError as err:
            raise _failure(err) from err
        self._blocked_cycles = 0
        ir.async_delete_issue(self.hass, DOMAIN, ISSUE_UPSTREAM_BLOCKED)
        return data

    async def _fetch(self) -> dict[int, MachineData]:
        """Run one polling cycle."""
        tokens = await self.client.get_tokens()

        groups: dict[tuple[float, float, int], list[int]] = defaultdict(list)
        for conf in self.config_entry.data[CONF_MACHINES]:
            groups[(conf["lat"], conf["lng"], conf["radius"])].append(conf["id"])

        result: dict[int, MachineData] = {}
        for (lat, lng, radius), ids in groups.items():
            found = {m.id: m for m in await self.client.nearby(tokens, lat, lng, radius)}
            for rvm_id in ids:
                machine = found.get(rvm_id)
                if machine is None:
                    _LOGGER.warning("Machine %s not returned by nearby search", rvm_id)
                    continue
                try:
                    compartments = await self.client.bin_status(tokens, rvm_id)
                except RvmError as err:
                    _LOGGER.warning("Bin status failed for machine %s: %s", rvm_id, err)
                    continue
                result[rvm_id] = MachineData(machine, tuple(compartments))
        return result
