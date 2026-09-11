"""Driftsprofil for KI Basseng."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, PROFILE_OPTIONS
from .coordinator import KiBassengCoordinator
from .entity import KiBassengEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: KiBassengCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([KiBassengProfile(coordinator)])


class KiBassengProfile(KiBassengEntity, SelectEntity):
    """Setter omsetningsmål og puls i ett grep."""

    _attr_name = "Driftsprofil"
    _attr_icon = "mdi:tune-variant"
    _attr_options = PROFILE_OPTIONS

    def __init__(self, coordinator: KiBassengCoordinator) -> None:
        super().__init__(coordinator, "driftsprofil")

    @property
    def current_option(self) -> str:
        return self.coordinator.settings.get("profile", PROFILE_OPTIONS[0])

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_set_profile(option)
