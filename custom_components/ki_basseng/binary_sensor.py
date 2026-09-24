"""Binærsensorer for KI Basseng."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import KiBassengCoordinator
from .entity import KiBassengEntity


@dataclass(frozen=True, kw_only=True)
class KiBinaryDescription(BinarySensorEntityDescription):
    value: Callable[[dict], bool | None]
    attrs: Callable[[dict], dict] | None = None


BINARY_SENSORS: tuple[KiBinaryDescription, ...] = (
    KiBinaryDescription(
        key="pumpe_skal_ga",
        name="Pumpe skal gå",
        icon="mdi:pump",
        value=lambda d: d.get("desired"),
        attrs=lambda d: {
            "modus": d.get("mode"),
            "begrunnelse": d.get("reason"),
        },
    ),
    KiBinaryDescription(
        key="spreder_kjorer",
        name="Spreder kjører",
        icon="mdi:sprinkler",
        device_class=BinarySensorDeviceClass.RUNNING,
        value=lambda d: d.get("sprinkler_running"),
        attrs=lambda d: {
            "gjenstar_min": d.get("sprinkler_left"),
            "brukt_i_dag_min": d.get("sprinkler_today"),
            "status": d.get("sprinkler_reason"),
        },
    ),
    KiBinaryDescription(
        key="manuell_overstyring",
        name="Manuell overstyring",
        icon="mdi:hand-back-right-outline",
        value=lambda d: d.get("override"),
        attrs=lambda d: {"til": d.get("override_until")},
    ),
    KiBinaryDescription(
        key="nattsenking_aktiv",
        name="Nattsenking aktiv",
        icon="mdi:weather-night",
        value=lambda d: d.get("setback_active"),
        attrs=lambda d: {
            "fra": (d.get("setback") or {}).get("start"),
            "til": (d.get("setback") or {}).get("end"),
            "begrunnelse": (d.get("setback") or {}).get("reason"),
        },
    ),
    KiBinaryDescription(
        key="klortablett_bor_legges_i",
        name="Klortablett bør legges i",
        icon="mdi:pill",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value=lambda d: (d.get("chlorine") or {}).get("due"),
        attrs=lambda d: {
            "neste": (d.get("chlorine") or {}).get("next"),
            "dager_siden": (d.get("chlorine") or {}).get("days_since"),
        },
    ),
    KiBinaryDescription(
        key="noen_hjemme",
        name="Noen hjemme",
        device_class=BinarySensorDeviceClass.PRESENCE,
        value=lambda d: d.get("present"),
    ),
    KiBinaryDescription(
        key="varmepumpe_venter",
        name="Varmepumpe venter",
        icon="mdi:heat-pump-outline",
        value=lambda d: d.get("hp_waiting"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: KiBassengCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(KiBassengBinarySensor(coordinator, d) for d in BINARY_SENSORS)


class KiBassengBinarySensor(KiBassengEntity, BinarySensorEntity):
    entity_description: KiBinaryDescription

    def __init__(
        self, coordinator: KiBassengCoordinator, description: KiBinaryDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        return self.entity_description.value(self.data)

    @property
    def extra_state_attributes(self) -> dict | None:
        if self.entity_description.attrs is None:
            return None
        return self.entity_description.attrs(self.data)
