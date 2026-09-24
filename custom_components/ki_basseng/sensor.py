"""Sensorer for KI Basseng."""

from __future__ import annotations

import re
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
    UnitOfIrradiance,
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


SETBACK_STATES = ["av", "aktiv", "planlagt", "lonner_seg_ikke"]


def _setback_state(s: dict) -> str:
    if not s.get("enabled"):
        return "av"
    if s.get("active"):
        return "aktiv"
    if s.get("worth_it"):
        return "planlagt"
    return "lonner_seg_ikke"


def _setback_attrs(s: dict) -> dict:
    def hhmm(value: Any) -> str | None:
        return value.strftime("%H:%M") if value is not None else None

    return {
        "begrunnelse": s.get("reason"),
        "fra": hhmm(s.get("start")),
        "til": hhmm(s.get("end")),
        "spart_kwh": s.get("saving_kwh"),
        "spart_kostnad": s.get("saving_cost"),
        "uten_senking_kwh": s.get("baseline_kwh"),
        "uten_senking_kostnad": s.get("baseline_cost"),
        "med_senking_kwh": s.get("setback_kwh"),
        "laveste_temperatur": s.get("lowest_temp"),
        "vurderte_vinduer": s.get("candidates"),
        "beste_alternativer": s.get("alternatives"),
    }


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
            "cop_modell": d.get("cop_model"),
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
            "modellestimat": d.get("temp_estimate"),
        },
    ),
    KiSensorDescription(
        key="maltemperatur",
        name="Måltemperatur",
        icon="mdi:thermometer-check",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        suggested_display_precision=1,
        value=lambda d, c: d.get("target_temp"),
        attrs=lambda d, c: {
            "onsket": d.get("wanted_temp"),
            "noen_hjemme": d.get("present"),
            "estimert_vanntemperatur": d.get("temp_estimate"),
        },
    ),
    KiSensorDescription(
        key="nattsenking",
        name="Nattsenking",
        icon="mdi:weather-night",
        device_class=SensorDeviceClass.ENUM,
        options=SETBACK_STATES,
        value=lambda d, c: _setback_state(d.get("setback") or {}),
        attrs=lambda d, c: _setback_attrs(d.get("setback") or {}),
    ),
    KiSensorDescription(
        key="nattsenking_besparelse",
        name="Nattsenking besparelse",
        icon="mdi:lightning-bolt-outline",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=1,
        value=lambda d, c: (d.get("setback") or {}).get("saving_kwh"),
        attrs=lambda d, c: {
            "kostnad": (d.get("setback") or {}).get("saving_cost"),
        },
    ),
    KiSensorDescription(
        key="varmetap",
        name="Varmetap",
        icon="mdi:waves-arrow-up",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value=lambda d, c: d.get("heat_loss_w"),
        attrs=lambda d, c: {
            "pooltak": d.get("covered"),
            "utetemperatur": d.get("outdoor"),
            "solgevinst_w": d.get("solar_gain_w"),
            "laert_tapsfaktor_uten_tak": (d.get("learned") or {}).get("loss_open"),
            "laert_tapsfaktor_med_tak": (d.get("learned") or {}).get("loss_covered"),
            "laert_cop_faktor": (d.get("learned") or {}).get("cop_factor"),
            "cop_modell": d.get("cop_model"),
        },
    ),
    KiSensorDescription(
        key="solinnstraling",
        name="Solinnstråling",
        icon="mdi:weather-sunny",
        native_unit_of_measurement=UnitOfIrradiance.WATTS_PER_SQUARE_METER,
        device_class=SensorDeviceClass.IRRADIANCE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value=lambda d, c: d.get("irradiance"),
        attrs=lambda d, c: {
            "solhoyde": d.get("sun_elevation"),
            "breddegrad": c.location[0],
            "lengdegrad": c.location[1],
        },
    ),
    KiSensorDescription(
        key="siste_klortablett",
        name="Siste klortablett",
        icon="mdi:pill",
        device_class=SensorDeviceClass.TIMESTAMP,
        value=lambda d, c: (d.get("chlorine") or {}).get("last"),
        attrs=lambda d, c: {
            "dager_siden": (d.get("chlorine") or {}).get("days_since"),
            "siste_7_dager": (d.get("chlorine") or {}).get("week"),
            "totalt": (d.get("chlorine") or {}).get("total"),
            "historikk": (d.get("chlorine") or {}).get("history"),
        },
    ),
    KiSensorDescription(
        key="neste_klortablett",
        name="Neste klortablett",
        icon="mdi:calendar-clock",
        device_class=SensorDeviceClass.TIMESTAMP,
        value=lambda d, c: (d.get("chlorine") or {}).get("next"),
        attrs=lambda d, c: {
            "intervall_dager": (d.get("chlorine") or {}).get("interval_days"),
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
        attrs = dict(self.entity_description.attrs(self.data, self.coordinator))
        if self.entity_description.key == "pumpemodus":
            # Markør slik kortet finner riktig sensor selv om entity_id har
            # fått en _2-hale fordi en gammel YAML-sensor tok navnet først.
            objekt = self.entity_id.split(".", 1)[-1]
            attrs["integrasjon"] = DOMAIN
            attrs["prefiks"] = re.sub(r"_pumpemodus(_\d+)?$", "", objekt)
        return attrs
