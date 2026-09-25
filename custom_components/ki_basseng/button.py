"""Knapper for KI Basseng."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import KiBassengCoordinator
from .entity import KiBassengEntity


@dataclass(frozen=True, kw_only=True)
class KiButtonDescription(ButtonEntityDescription):
    action: Callable[[KiBassengCoordinator], Coroutine[Any, Any, None]]
    level: bool = False


BUTTONS: tuple[KiButtonDescription, ...] = (
    KiButtonDescription(
        key="start_spreder",
        name="Start spreder",
        icon="mdi:play",
        action=lambda c: c.async_start_sprinkler(),
    ),
    KiButtonDescription(
        key="stopp_spreder",
        name="Stopp spreder",
        icon="mdi:stop",
        action=lambda c: c.async_stop_sprinkler("Stoppet"),
    ),
    KiButtonDescription(
        key="boost_sirkulasjon",
        name="Boost sirkulasjon",
        icon="mdi:fan-plus",
        action=lambda c: c.async_boost(30),
    ),
    KiButtonDescription(
        key="logg_klortablett",
        name="Logg klortablett",
        icon="mdi:pill",
        action=lambda c: c.async_log_chlorine(1),
    ),
    KiButtonDescription(
        key="angre_klortablett",
        name="Angre siste klortablett",
        icon="mdi:undo",
        entity_category=EntityCategory.CONFIG,
        action=lambda c: c.async_undo_chlorine(),
    ),
    KiButtonDescription(
        key="nullstill_i_dag",
        name="Nullstill dagens tellere",
        icon="mdi:backup-restore",
        entity_category=EntityCategory.CONFIG,
        action=lambda c: c.async_reset_daily(),
    ),
    KiButtonDescription(
        key="fyll_bassenget",
        name="Fyll bassenget",
        icon="mdi:water-plus",
        level=True,
        action=lambda c: c.async_start_fill(),
    ),
    KiButtonDescription(
        key="stopp_pafylling",
        name="Stopp påfylling",
        icon="mdi:water-off",
        level=True,
        action=lambda c: c.async_stop_fill("Stoppet"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: KiBassengCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        KiBassengButton(coordinator, d) for d in BUTTONS if not d.level or coordinator.has_level
    )


class KiBassengButton(KiBassengEntity, ButtonEntity):
    entity_description: KiButtonDescription

    def __init__(
        self, coordinator: KiBassengCoordinator, description: KiButtonDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    async def async_press(self) -> None:
        await self.entity_description.action(self.coordinator)
