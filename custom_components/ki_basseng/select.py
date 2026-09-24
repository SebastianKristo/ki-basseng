"""Valg for KI Basseng: driftsprofil og hva nattsenkingen skal spare."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, PROFILE_OPTIONS
from .coordinator import KiBassengCoordinator
from .entity import KiBassengEntity
from .termisk import CRITERIA


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: KiBassengCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([KiBassengProfile(coordinator), KiBassengCriterion(coordinator)])


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


class KiBassengCriterion(KiBassengEntity, SelectEntity):
    """Hva nattsenkingen må spare for å slå av varmepumpen.

    begge: penger, men aldri ved å bruke mer strøm. kostnad: bare penger.
    energi: bare kWh, uansett pris.
    """

    _attr_name = "Nattsenking skal spare"
    _attr_icon = "mdi:scale-balance"
    _attr_options = CRITERIA
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: KiBassengCoordinator) -> None:
        super().__init__(coordinator, "nattsenking_kriterium")

    @property
    def current_option(self) -> str:
        return self.coordinator.settings.get("setback_criterion", CRITERIA[0])

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.async_set_setting("setback_criterion", option)
