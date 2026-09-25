"""Tallinnstillinger for KI Basseng."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import KiBassengCoordinator
from .entity import KiBassengEntity


@dataclass(frozen=True, kw_only=True)
class KiNumberDescription(NumberEntityDescription):
    setting: str
    level: bool = False


NUMBERS: tuple[KiNumberDescription, ...] = (
    KiNumberDescription(
        key="omsetninger_mal",
        name="Omsetninger per døgn",
        icon="mdi:autorenew",
        setting="turnovers",
        native_min_value=0.25,
        native_max_value=4,
        native_step=0.25,
        native_unit_of_measurement="x",
        mode=NumberMode.SLIDER,
    ),
    KiNumberDescription(
        key="vedlikeholdspuls",
        name="Vedlikeholdspuls",
        icon="mdi:timer-play-outline",
        setting="pulse_minutes",
        native_min_value=0,
        native_max_value=30,
        native_step=1,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        mode=NumberMode.SLIDER,
    ),
    KiNumberDescription(
        key="minste_kjoretid",
        name="Minste kjøretid",
        icon="mdi:timer-lock-outline",
        setting="min_runtime",
        native_min_value=0,
        native_max_value=60,
        native_step=5,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        entity_category=EntityCategory.CONFIG,
    ),
    KiNumberDescription(
        key="overstyring_varighet",
        name="Manuell overstyring varer",
        icon="mdi:hand-back-right-outline",
        setting="override_minutes",
        native_min_value=0,
        native_max_value=480,
        native_step=15,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        entity_category=EntityCategory.CONFIG,
    ),
    KiNumberDescription(
        key="dagtimer",
        name="Dagtimer i planen",
        icon="mdi:white-balance-sunny",
        setting="daytime_hours",
        native_min_value=0,
        native_max_value=6,
        native_step=1,
        native_unit_of_measurement="t",
        entity_category=EntityCategory.CONFIG,
    ),
    KiNumberDescription(
        key="varmevindu_start",
        name="Varmevindu start",
        icon="mdi:weather-sunset-up",
        setting="heat_start",
        native_min_value=0,
        native_max_value=23,
        native_step=1,
        entity_category=EntityCategory.CONFIG,
    ),
    KiNumberDescription(
        key="varmevindu_slutt",
        name="Varmevindu slutt",
        icon="mdi:weather-sunset-down",
        setting="heat_end",
        native_min_value=0,
        native_max_value=24,
        native_step=1,
        entity_category=EntityCategory.CONFIG,
    ),
    KiNumberDescription(
        key="pumpe_basislast",
        name="Pumpe basislast",
        icon="mdi:flash-outline",
        setting="pump_baseline",
        native_min_value=50,
        native_max_value=5000,
        native_step=10,
        native_unit_of_measurement=UnitOfPower.WATT,
        entity_category=EntityCategory.CONFIG,
    ),
    KiNumberDescription(
        key="spreder_varighet",
        name="Spreder varighet",
        icon="mdi:timer-sand",
        setting="sprinkler_duration",
        native_min_value=1,
        native_max_value=60,
        native_step=1,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        mode=NumberMode.SLIDER,
    ),
    KiNumberDescription(
        key="spreder_intervall",
        name="Spreder intervall",
        icon="mdi:repeat",
        setting="sprinkler_interval",
        native_min_value=0,
        native_max_value=24,
        native_step=1,
        native_unit_of_measurement="t",
    ),
    KiNumberDescription(
        key="onsket_temperatur",
        name="Ønsket temperatur",
        icon="mdi:pool-thermometer",
        setting="target_temp",
        native_min_value=10,
        native_max_value=40,
        native_step=0.5,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        mode=NumberMode.BOX,
    ),
    KiNumberDescription(
        key="borte_senking",
        name="Senking når ingen er hjemme",
        icon="mdi:home-export-outline",
        setting="away_drop",
        native_min_value=0,
        native_max_value=10,
        native_step=0.5,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    ),
    KiNumberDescription(
        key="maks_nattsenking",
        name="Maks nattsenking",
        icon="mdi:thermometer-minus",
        setting="max_drop",
        native_min_value=0.5,
        native_max_value=6,
        native_step=0.5,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_category=EntityCategory.CONFIG,
    ),
    KiNumberDescription(
        key="varmetap_uten_tak",
        name="Varmetap uten tak",
        icon="mdi:waves-arrow-up",
        setting="u_open",
        native_min_value=1,
        native_max_value=60,
        native_step=0.5,
        native_unit_of_measurement="W/m²K",
        entity_category=EntityCategory.CONFIG,
    ),
    KiNumberDescription(
        key="varmetap_med_tak",
        name="Varmetap med tak",
        icon="mdi:pool",
        setting="u_covered",
        native_min_value=0.5,
        native_max_value=30,
        native_step=0.5,
        native_unit_of_measurement="W/m²K",
        entity_category=EntityCategory.CONFIG,
    ),
    KiNumberDescription(
        key="sol_gjennom_tak",
        name="Sol gjennom taket",
        icon="mdi:weather-sunny",
        setting="cover_solar",
        native_min_value=0,
        native_max_value=100,
        native_step=5,
        native_unit_of_measurement=PERCENTAGE,
        entity_category=EntityCategory.CONFIG,
    ),
    KiNumberDescription(
        key="klortablett_intervall",
        name="Klortablett intervall",
        icon="mdi:calendar-refresh",
        setting="chlorine_days",
        native_min_value=1,
        native_max_value=30,
        native_step=0.5,
        native_unit_of_measurement="d",
        entity_category=EntityCategory.CONFIG,
    ),
    KiNumberDescription(
        key="frost_varme_under",
        name="Frostsikring: varme på under",
        icon="mdi:radiator",
        setting="frost_house_min",
        native_min_value=-5,
        native_max_value=15,
        native_step=0.5,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_category=EntityCategory.CONFIG,
    ),
    KiNumberDescription(
        key="frost_sirkulasjon_under",
        name="Frostsikring: sirkulasjon under",
        icon="mdi:snowflake-thermometer",
        setting="frost_pump_below",
        native_min_value=-15,
        native_max_value=5,
        native_step=0.5,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_category=EntityCategory.CONFIG,
    ),
    KiNumberDescription(
        key="vinter_omsetninger",
        name="Omsetninger per døgn om vinteren",
        icon="mdi:autorenew",
        setting="winter_turnovers",
        native_min_value=0,
        native_max_value=2,
        native_step=0.25,
        native_unit_of_measurement="x",
        entity_category=EntityCategory.CONFIG,
    ),
    KiNumberDescription(
        key="spreder_maks",
        name="Spreder maks per døgn",
        icon="mdi:water-alert-outline",
        setting="sprinkler_daily_max",
        native_min_value=0,
        native_max_value=240,
        native_step=10,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        entity_category=EntityCategory.CONFIG,
    ),
    KiNumberDescription(
        key="torr_for_varsel",
        name="Tørr før varsel",
        icon="mdi:timer-sand",
        setting="level_dry_minutes",
        level=True,
        native_min_value=5,
        native_max_value=240,
        native_step=5,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
    ),
    KiNumberDescription(
        key="maks_pafylling",
        name="Maks påfylling",
        icon="mdi:timer-lock-outline",
        setting="fill_max_minutes",
        level=True,
        native_min_value=5,
        native_max_value=480,
        native_step=5,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: KiBassengCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        KiBassengNumber(coordinator, d) for d in NUMBERS if not d.level or coordinator.has_level
    )


class KiBassengNumber(KiBassengEntity, NumberEntity):
    entity_description: KiNumberDescription

    def __init__(
        self, coordinator: KiBassengCoordinator, description: KiNumberDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float:
        return float(
            self.coordinator.settings.get(self.entity_description.setting, 0) or 0
        )

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_setting(
            self.entity_description.setting, float(value)
        )
