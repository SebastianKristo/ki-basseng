"""Oppsett av KI Basseng via brukergrensesnittet."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
)

from .const import (
    CONF_CLIMATE,
    CONF_CURRENCY,
    CONF_FLOW,
    CONF_HP_NOMINAL,
    CONF_HP_POWER_SENSOR,
    CONF_INFLOW,
    CONF_OUTDOOR,
    CONF_OUTFLOW,
    CONF_POWER_SENSOR,
    CONF_PRICE_SENSOR,
    CONF_PUMP_BASELINE,
    CONF_PUMP_POWER_SENSOR,
    CONF_PUMP_SWITCH,
    CONF_VALVE,
    CONF_VOLUME,
    DEFAULT_CURRENCY,
    DEFAULT_FLOW,
    DEFAULT_HP_NOMINAL,
    DEFAULT_PUMP_BASELINE,
    DEFAULT_VOLUME,
    DOMAIN,
    NAME,
)


def _entity(domain: str | list[str], device_class: str | None = None) -> EntitySelector:
    config: dict[str, Any] = {"domain": domain}
    if device_class:
        config["device_class"] = device_class
    return EntitySelector(EntitySelectorConfig(**config))


def _number(minimum: float, maximum: float, step: float, unit: str) -> NumberSelector:
    return NumberSelector(
        NumberSelectorConfig(
            min=minimum,
            max=maximum,
            step=step,
            unit_of_measurement=unit,
            mode=NumberSelectorMode.BOX,
        )
    )


MALING_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_PUMP_SWITCH): _entity(["switch", "input_boolean"]),
        vol.Optional(CONF_POWER_SENSOR): _entity("sensor", "power"),
        vol.Optional(CONF_PUMP_POWER_SENSOR): _entity("sensor", "power"),
        vol.Optional(CONF_HP_POWER_SENSOR): _entity("sensor", "power"),
        vol.Optional(CONF_PRICE_SENSOR): _entity("sensor"),
    }
)

UTSTYR_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_CLIMATE): _entity("climate"),
        vol.Optional(CONF_INFLOW): _entity("sensor", "temperature"),
        vol.Optional(CONF_OUTFLOW): _entity("sensor", "temperature"),
        vol.Optional(CONF_OUTDOOR): _entity("sensor", "temperature"),
        vol.Optional(CONF_VALVE): _entity(["switch", "valve", "input_boolean"]),
    }
)


def _basseng_schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                CONF_VOLUME, default=defaults.get(CONF_VOLUME, DEFAULT_VOLUME)
            ): _number(1, 200, 0.01, "m³"),
            vol.Required(
                CONF_FLOW, default=defaults.get(CONF_FLOW, DEFAULT_FLOW)
            ): _number(1, 60, 0.1, "m³/t"),
            vol.Required(
                CONF_PUMP_BASELINE,
                default=defaults.get(CONF_PUMP_BASELINE, DEFAULT_PUMP_BASELINE),
            ): _number(50, 5000, 10, "W"),
            vol.Required(
                CONF_HP_NOMINAL,
                default=defaults.get(CONF_HP_NOMINAL, DEFAULT_HP_NOMINAL),
            ): _number(100, 10000, 10, "W"),
            vol.Required(
                CONF_CURRENCY, default=defaults.get(CONF_CURRENCY, DEFAULT_CURRENCY)
            ): TextSelector(),
        }
    )


class KiBassengConfigFlow(ConfigFlow, domain=DOMAIN):
    """Tre steg: måling, utstyr, basseng."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_utstyr()
        return self.async_show_form(step_id="user", data_schema=MALING_SCHEMA)

    async def async_step_utstyr(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_basseng()
        return self.async_show_form(step_id="utstyr", data_schema=UTSTYR_SCHEMA)

    async def async_step_basseng(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._data.update(user_input)
            await self.async_set_unique_id(self._data[CONF_PUMP_SWITCH])
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=NAME, data=self._data)
        return self.async_show_form(
            step_id="basseng", data_schema=_basseng_schema({})
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> KiBassengOptionsFlow:
        return KiBassengOptionsFlow()


class KiBassengOptionsFlow(OptionsFlow):
    """Endre entiteter og bassengdata i ettertid."""

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    @property
    def _current(self) -> dict[str, Any]:
        return {**self.config_entry.data, **self.config_entry.options}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="init", menu_options=["maling", "utstyr", "basseng"]
        )

    def _with_defaults(self, schema: vol.Schema) -> vol.Schema:
        current = self._current
        fields: dict[Any, Any] = {}
        for key, value in schema.schema.items():
            name = str(key)
            if name in current and current[name] not in (None, ""):
                fields[
                    vol.Optional(name, default=current[name])
                ] = value
            else:
                fields[vol.Optional(name)] = value
        return vol.Schema(fields)

    async def _save(self, user_input: dict[str, Any]) -> ConfigFlowResult:
        options = {**self.config_entry.options, **user_input}
        return self.async_create_entry(title="", data=options)

    async def async_step_maling(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return await self._save(user_input)
        return self.async_show_form(
            step_id="maling", data_schema=self._with_defaults(MALING_SCHEMA)
        )

    async def async_step_utstyr(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return await self._save(user_input)
        return self.async_show_form(
            step_id="utstyr", data_schema=self._with_defaults(UTSTYR_SCHEMA)
        )

    async def async_step_basseng(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return await self._save(user_input)
        return self.async_show_form(
            step_id="basseng", data_schema=_basseng_schema(self._current)
        )
