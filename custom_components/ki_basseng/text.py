"""Tekstfelt for KI Basseng: hvem som kan legge i klortabletter."""

from __future__ import annotations

from homeassistant.components.text import TextEntity, TextMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import KiBassengCoordinator, split_names
from .entity import KiBassengEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: KiBassengCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([KiBassengChlorineNames(coordinator)])


class KiBassengChlorineNames(KiBassengEntity, TextEntity):
    """Navnene kortet viser som avhukingsknapper når en klortablett logges.

    Skrives kommaseparert. Mellomrom og duplikater ryddes bort, så «ida, Ida» blir
    ett navn.
    """

    _attr_name = "Navn i klorloggen"
    _attr_icon = "mdi:account-multiple-check"
    _attr_mode = TextMode.TEXT
    _attr_native_max = 255
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: KiBassengCoordinator) -> None:
        super().__init__(coordinator, "klor_navn")

    @property
    def native_value(self) -> str:
        return ", ".join(self.coordinator.chlorine_names)

    async def async_set_value(self, value: str) -> None:
        await self.coordinator.async_set_setting(
            "chlorine_names", ", ".join(split_names(value))
        )
