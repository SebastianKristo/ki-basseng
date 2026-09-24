"""Brytere som styrer oppførselen til KI Basseng."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import KiBassengCoordinator
from .entity import KiBassengEntity


@dataclass(frozen=True, kw_only=True)
class KiSwitchDescription(SwitchEntityDescription):
    setting: str


SWITCHES: tuple[KiSwitchDescription, ...] = (
    KiSwitchDescription(
        key="automatikk",
        name="Automatikk",
        icon="mdi:robot-outline",
        setting="auto",
    ),
    KiSwitchDescription(
        key="prisstyring",
        name="Prisstyring",
        icon="mdi:cash-clock",
        setting="price_control",
    ),
    KiSwitchDescription(
        key="varmeprioritet",
        name="Varmeprioritet",
        icon="mdi:heat-wave",
        setting="heat_priority",
    ),
    KiSwitchDescription(
        key="styr_varmepumpe",
        name="Styr varmepumpe",
        icon="mdi:heat-pump-outline",
        setting="manage_heatpump",
        entity_category=EntityCategory.CONFIG,
    ),
    KiSwitchDescription(
        key="tving_heat",
        name="Tving varmepumpa til heat",
        icon="mdi:fire",
        setting="force_heat",
        entity_category=EntityCategory.CONFIG,
    ),
    KiSwitchDescription(
        key="puls_med_varme",
        name="Puls med varme",
        icon="mdi:fire-circle",
        setting="pulse_with_heat",
        entity_category=EntityCategory.CONFIG,
    ),
    KiSwitchDescription(
        key="spreder_program",
        name="Spreder-program",
        icon="mdi:sprinkler-variant",
        setting="sprinkler_program",
    ),
    KiSwitchDescription(
        key="smart_nattsenking",
        name="Smart nattsenking",
        icon="mdi:weather-night",
        setting="smart_setback",
    ),
    KiSwitchDescription(
        key="styr_settpunkt",
        name="Styr settpunkt",
        icon="mdi:thermometer-auto",
        setting="manage_setpoint",
        entity_category=EntityCategory.CONFIG,
    ),
    KiSwitchDescription(
        key="pooltak_pa",
        name="Pooltak på",
        icon="mdi:pool",
        setting="cover_on",
    ),
    KiSwitchDescription(
        key="solvarme",
        name="Solvarme",
        icon="mdi:solar-power-variant",
        setting="solar_harvest",
        entity_category=EntityCategory.CONFIG,
    ),
    KiSwitchDescription(
        key="frostvakt",
        name="Frostvakt",
        icon="mdi:snowflake-alert",
        setting="frost_guard",
        entity_category=EntityCategory.CONFIG,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: KiBassengCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(KiBassengSwitch(coordinator, d) for d in SWITCHES)


class KiBassengSwitch(KiBassengEntity, SwitchEntity):
    entity_description: KiSwitchDescription

    def __init__(
        self, coordinator: KiBassengCoordinator, description: KiSwitchDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.settings.get(self.entity_description.setting))

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_setting(self.entity_description.setting, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_set_setting(self.entity_description.setting, False)
