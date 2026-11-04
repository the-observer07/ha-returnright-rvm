"""Config and options flows for the Return Right RVM integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    TextSelector,
)

from .api import (
    RvmBlockedError,
    RvmClient,
    RvmError,
    RvmPostcodeNotFoundError,
    make_session,
)
from .const import (
    CONF_MACHINES,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL_MIN,
    DOMAIN,
    MAX_SCAN_INTERVAL_MIN,
    MIN_SCAN_INTERVAL_MIN,
    POLL_RADIUS_M,
    SEARCH_RADIUS_M,
)
from .models import Machine, normalise_status

CONF_POSTCODE = "postcode"

POSTCODE_SCHEMA = vol.Schema({vol.Required(CONF_POSTCODE): TextSelector()})


def _label(machine: Machine) -> str:
    return (
        f"{machine.name} - {machine.distance_m:.0f} m - {machine.address}"
        f" ({normalise_status(machine.raw_status)})"
    )


def _select_schema(options: list[SelectOptionDict]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_MACHINES): SelectSelector(
                SelectSelectorConfig(options=options, multiple=True)
            )
        }
    )


class _SearchMixin:
    """Postcode search shared by the config and options flows."""

    _origin: tuple[float, float]
    _found: dict[int, Machine]

    async def _search(self, postcode: str, skip: set[int]) -> str | None:
        """Search near a postcode; return an error key or None."""
        client = RvmClient(make_session())
        try:
            lat, lng, _ = await client.geocode(postcode.strip())
            tokens = await client.get_tokens()
            machines = await client.nearby(tokens, lat, lng, SEARCH_RADIUS_M)
        except RvmPostcodeNotFoundError:
            return "postcode_not_found"
        except RvmBlockedError:
            return "upstream_blocked"
        except RvmError:
            return "cannot_connect"
        finally:
            await client.close()
        self._origin = (lat, lng)
        self._found = {m.id: m for m in machines if m.id not in skip}
        return None if self._found else "no_machines"

    def _picked(self, ids: list[str]) -> list[dict[str, Any]]:
        lat, lng = self._origin
        return [
            {
                "id": m.id,
                "name": m.name,
                "lat": lat,
                "lng": lng,
                "radius": POLL_RADIUS_M,
            }
            for m in (self._found[int(i)] for i in ids)
        ]

    def _pick_options(self) -> list[SelectOptionDict]:
        return [SelectOptionDict(value=str(m.id), label=_label(m)) for m in self._found.values()]


class RvmConfigFlow(_SearchMixin, ConfigFlow, domain=DOMAIN):
    """Set up the integration from a postcode."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> RvmOptionsFlow:
        """Return the options flow."""
        return RvmOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for a postcode and search for machines."""
        errors: dict[str, str] = {}
        if user_input is not None:
            error = await self._search(user_input[CONF_POSTCODE], set())
            if error is None:
                return await self.async_step_pick_machines()
            errors["base"] = error
        return self.async_show_form(step_id="user", data_schema=POSTCODE_SCHEMA, errors=errors)

    async def async_step_pick_machines(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose which machines to track."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if user_input[CONF_MACHINES]:
                return self.async_create_entry(
                    title="Return Right RVM",
                    data={CONF_MACHINES: self._picked(user_input[CONF_MACHINES])},
                    options={CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL_MIN},
                )
            errors["base"] = "no_selection"
        return self.async_show_form(
            step_id="pick_machines",
            data_schema=_select_schema(self._pick_options()),
            errors=errors,
        )


class RvmOptionsFlow(_SearchMixin, OptionsFlowWithReload):
    """Change the interval or the tracked machines."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show the options menu."""
        return self.async_show_menu(
            step_id="init",
            menu_options=["interval", "add_machines", "remove_machines"],
        )

    async def async_step_interval(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Set the polling interval."""
        if user_input is not None:
            return self.async_create_entry(
                data={CONF_SCAN_INTERVAL: int(user_input[CONF_SCAN_INTERVAL])}
            )
        current = self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL_MIN)
        schema = vol.Schema(
            {
                vol.Required(CONF_SCAN_INTERVAL, default=current): NumberSelector(
                    NumberSelectorConfig(
                        min=MIN_SCAN_INTERVAL_MIN,
                        max=MAX_SCAN_INTERVAL_MIN,
                        step=1,
                        mode=NumberSelectorMode.BOX,
                        unit_of_measurement="min",
                    )
                )
            }
        )
        return self.async_show_form(step_id="interval", data_schema=schema)

    async def async_step_add_machines(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Search for more machines by postcode."""
        errors: dict[str, str] = {}
        if user_input is not None:
            have = {m["id"] for m in self.config_entry.data[CONF_MACHINES]}
            error = await self._search(user_input[CONF_POSTCODE], have)
            if error is None:
                return await self.async_step_pick_machines()
            errors["base"] = error
        return self.async_show_form(
            step_id="add_machines", data_schema=POSTCODE_SCHEMA, errors=errors
        )

    async def async_step_pick_machines(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose which found machines to add."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if user_input[CONF_MACHINES]:
                return self._save_machines(
                    [
                        *self.config_entry.data[CONF_MACHINES],
                        *self._picked(user_input[CONF_MACHINES]),
                    ]
                )
            errors["base"] = "no_selection"
        return self.async_show_form(
            step_id="pick_machines",
            data_schema=_select_schema(self._pick_options()),
            errors=errors,
        )

    async def async_step_remove_machines(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Remove tracked machines."""
        current = self.config_entry.data[CONF_MACHINES]
        errors: dict[str, str] = {}
        if user_input is not None:
            gone = {int(i) for i in user_input[CONF_MACHINES]}
            kept = [m for m in current if m["id"] not in gone]
            if kept:
                return self._save_machines(kept)
            errors["base"] = "cannot_remove_all"
        options = [SelectOptionDict(value=str(m["id"]), label=m["name"]) for m in current]
        return self.async_show_form(
            step_id="remove_machines",
            data_schema=_select_schema(options),
            errors=errors,
        )

    def _save_machines(self, machines: list[dict[str, Any]]) -> ConfigFlowResult:
        """Store the machine list, then finish so the entry reloads."""
        self.hass.config_entries.async_update_entry(
            self.config_entry, data={CONF_MACHINES: machines}
        )
        # Options stay unchanged, so OptionsFlowWithReload would not reload.
        self.hass.config_entries.async_schedule_reload(self.config_entry.entry_id)
        return self.async_create_entry(data=dict(self.config_entry.options))
