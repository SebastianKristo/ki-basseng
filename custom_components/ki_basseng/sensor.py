"""Sensorer for KI Basseng."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
    UnitOfVolume,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, MODES
from .coordinator import KiBassengCoordinator
from .entity import KiBassengEntity


@dataclass(frozen=True, kw_only=True)
class KiSensorDescription(SensorEntityDescription):
    """Beskrivelse med uthenter og ekstra attributter."""

    value: Callable[[dict, KiBassengCoordinator], Any]
    attrs: Callable[[dict, KiBassengCoordinator], dict] | None = None


SENSORS: tuple[KiSensorDescription, ...] = (
    KiSensorDescription(
        key="pumpemodus",
        name="Pumpemodus",
        icon="mdi:pump",
        device_class=SensorDeviceClass.ENUM,
        options=MODES,
        value=lambda d, c: d.get("mode"),
        attrs=lambda d, c: {
            "begrunnelse": d.get("reason"),
            "pumpe_gar": d.get("pump_on"),
            "plan_i_dag": d.get("plan"),
            "blokker": d.get("blocks"),
            "blokker_i_morgen": d.get("blocks_tomorrow"),
            "timer_planlagt": d.get("planned_hours"),
            "timer_behov": d.get("needed_hours"),
            "omsetningstid": d.get("turnover_hours"),
            "snittpris_plan": d.get("price_plan_avg"),
            "snittpris_dogn": d.get("price_day_avg"),
            "overstyrt": d.get("override"),
        },
    ),
    KiSensorDescription(
        key="omsetninger_i_dag",
        name="Omsetninger i dag",
        icon="mdi:autorenew",
        native_unit_of_measurement="x",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value=lambda d, c: d.get("turnovers_done"),
        attrs=lambda d, c: {
            "mal": d.get("turnovers_target"),
            "gjenstar": d.get("turnovers_left"),
            "anbefalt": d.get("recommended_turnovers"),
            "en_omsetning_timer": d.get("turnover_hours"),
        },
    ),
    KiSensorDescription(
        key="pumpet_volum_i_dag",
        name="Pumpet volum i dag",
        icon="mdi:water-pump",
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=1,
        value=lambda d, c: d.get("volume_today"),
    ),
    KiSensorDescription(
        key="pumpet_volum_totalt",
        name="Pumpet volum totalt",
        icon="mdi:water-pump",
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=1,
        value=lambda d, c: d.get("volume_total"),
    ),
    KiSensorDescription(
        key="pumpetid_i_dag",
        name="Pumpetid i dag",
        icon="mdi:timer-outline",
        native_unit_of_measurement=UnitOfTime.HOURS,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value=lambda d, c: d.get("runtime_today"),
        attrs=lambda d, c: {
            "minutter": round((d.get("runtime_today") or 0) * 60),
        },
    ),
    KiSensorDescription(
        key="neste_pumpestart",
        name="Neste pumpestart",
        icon="mdi:clock-start",
        device_class=SensorDeviceClass.TIMESTAMP,
        value=lambda d, c: d.get("next_start"),
    ),
    KiSensorDescription(
        key="pumpe_effekt",
        name="Pumpe effekt",
        icon="mdi:pump",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value=lambda d, c: d.get("pump_w"),
    ),
    KiSensorDescription(
        key="varmepumpe_effekt",
        name="Varmepumpe effekt",
        icon="mdi:heat-pump",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value=lambda d, c: d.get("hp_w"),
        attrs=lambda d, c: {
            "delta_t": d.get("delta_t"),
            "termisk_w": d.get("thermal_w"),
            "cop_malt": d.get("cop"),
        },
    ),
    KiSensorDescription(
        key="pumpe_energi_i_dag",
        name="Pumpe energi i dag",
        icon="mdi:lightning-bolt",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
        value=lambda d, c: d.get("pump_kwh_today"),
    ),
    KiSensorDescription(
        key="varmepumpe_energi_i_dag",
        name="Varmepumpe energi i dag",
        icon="mdi:lightning-bolt",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        suggested_display_precision=2,
        value=lambda d, c: d.get("hp_kwh_today"),
    ),
    KiSensorDescription(
        key="kostnad_i_dag",
        name="Kostnad i dag",
        icon="mdi:cash-clock",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value=lambda d, c: d.get("cost_today"),
        attrs=lambda d, c: {"pris_na": d.get("price_now")},
    ),
    KiSensorDescription(
        key="spart_i_dag",
        name="Spart i dag",
        icon="mdi:piggy-bank-outline",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value=lambda d, c: d.get("saved_today"),
        attrs=lambda d, c: {
            "sammenlignet_med": "pumpe i kontinuerlig drift",
            "snittpris_plan": d.get("price_plan_avg"),
            "snittpris_dogn": d.get("price_day_avg"),
        },
    ),
    KiSensorDescription(
        key="vanntemperatur",
        name="Vanntemperatur",
        icon="mdi:pool-thermometer",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value=lambda d, c: d.get("water_temp"),
        attrs=lambda d, c: {
            "kilde": "snitt inn/ut under sirkulasjon" if d.get("pump_on")
            else "innløpsføler",
        },
    ),
    KiSensorDescription(
        key="spreder_gjenstar",
        name="Spreder gjenstår",
        icon="mdi:sprinkler-variant",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        suggested_display_precision=0,
        value=lambda d, c: d.get("sprinkler_left"),
        attrs=lambda d, c: {
            "status": d.get("sprinkler_reason"),
            "brukt_i_dag_min": d.get("sprinkler_today"),
        },
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: KiBassengCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(KiBassengSensor(coordinator, d) for d in SENSORS)


class KiBassengSensor(KiBassengEntity, SensorEntity):
    """En sensor definert av en KiSensorDescription."""

    entity_description: KiSensorDescription

    def __init__(
        self, coordinator: KiBassengCoordinator, description: KiSensorDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description
        if description.key in ("kostnad_i_dag", "spart_i_dag"):
            self._attr_native_unit_of_measurement = coordinator.currency

    @property
    def native_value(self) -> Any:
        return self.entity_description.value(self.data, self.coordinator)

    @property
    def extra_state_attributes(self) -> dict | None:
        if self.entity_description.attrs is None:
            return None
        return self.entity_description.attrs(self.data, self.coordinator)
