"""KI Basseng – sirkulasjon, varme og spreder i én integrasjon."""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import (
    ATTR_COUNT,
    ATTR_MINUTES,
    ATTR_NOTE,
    ATTR_PROFILE,
    ATTR_WHO,
    DOMAIN,
    PLATFORMS,
    PROFILE_OPTIONS,
    SERVICE_BOOST,
    SERVICE_LOG_CHLORINE,
    SERVICE_SET_PROFILE,
    SERVICE_START_SPREDER,
    SERVICE_STOP_SPREDER,
    SERVICE_UNDO_CHLORINE,
)
from .coordinator import KiBassengCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = KiBassengCoordinator(hass, entry)
    await coordinator.async_prepare()
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    _register_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        coordinator: KiBassengCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_persist()
        if not hass.data[DOMAIN]:
            for service in (
                SERVICE_START_SPREDER,
                SERVICE_STOP_SPREDER,
                SERVICE_BOOST,
                SERVICE_SET_PROFILE,
                SERVICE_LOG_CHLORINE,
                SERVICE_UNDO_CHLORINE,
            ):
                hass.services.async_remove(DOMAIN, service)
    return unloaded


async def _async_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


def _coordinators(hass: HomeAssistant, call: ServiceCall) -> list[KiBassengCoordinator]:
    entries = hass.data.get(DOMAIN, {})
    entry_id = call.data.get("entry_id")
    if entry_id and entry_id in entries:
        return [entries[entry_id]]
    return list(entries.values())


def _register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_START_SPREDER):
        return

    async def start_spreder(call: ServiceCall) -> None:
        for coordinator in _coordinators(hass, call):
            await coordinator.async_start_sprinkler(call.data.get(ATTR_MINUTES))

    async def stopp_spreder(call: ServiceCall) -> None:
        for coordinator in _coordinators(hass, call):
            await coordinator.async_stop_sprinkler("Stoppet")

    async def boost(call: ServiceCall) -> None:
        for coordinator in _coordinators(hass, call):
            await coordinator.async_boost(call.data.get(ATTR_MINUTES, 30))

    async def sett_profil(call: ServiceCall) -> None:
        for coordinator in _coordinators(hass, call):
            await coordinator.async_set_profile(call.data[ATTR_PROFILE])

    async def logg_klortablett(call: ServiceCall) -> None:
        for coordinator in _coordinators(hass, call):
            await coordinator.async_log_chlorine(
                call.data.get(ATTR_COUNT, 1),
                call.data.get(ATTR_NOTE, ""),
                call.data.get(ATTR_WHO, ""),
            )

    async def angre_klortablett(call: ServiceCall) -> None:
        for coordinator in _coordinators(hass, call):
            await coordinator.async_undo_chlorine()

    hass.services.async_register(
        DOMAIN,
        SERVICE_LOG_CHLORINE,
        logg_klortablett,
        schema=vol.Schema(
            {
                vol.Optional("entry_id"): cv.string,
                vol.Optional(ATTR_COUNT, default=1): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=20)
                ),
                vol.Optional(ATTR_NOTE, default=""): cv.string,
                vol.Optional(ATTR_WHO, default=""): cv.string,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_UNDO_CHLORINE,
        angre_klortablett,
        schema=vol.Schema({vol.Optional("entry_id"): cv.string}),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_START_SPREDER,
        start_spreder,
        schema=vol.Schema(
            {
                vol.Optional("entry_id"): cv.string,
                vol.Optional(ATTR_MINUTES): vol.All(
                    vol.Coerce(float), vol.Range(min=1, max=120)
                ),
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_STOP_SPREDER,
        stopp_spreder,
        schema=vol.Schema({vol.Optional("entry_id"): cv.string}),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_BOOST,
        boost,
        schema=vol.Schema(
            {
                vol.Optional("entry_id"): cv.string,
                vol.Optional(ATTR_MINUTES, default=30): vol.All(
                    vol.Coerce(float), vol.Range(min=5, max=240)
                ),
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_PROFILE,
        sett_profil,
        schema=vol.Schema(
            {
                vol.Optional("entry_id"): cv.string,
                vol.Required(ATTR_PROFILE): vol.In(PROFILE_OPTIONS),
            }
        ),
    )
