"""Felles grunnlag for alle KI Basseng-entiteter."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, NAME, VERSION
from .coordinator import KiBassengCoordinator


class KiBassengEntity(CoordinatorEntity[KiBassengCoordinator]):
    """Alt havner på én enhet, «KI Basseng»."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: KiBassengCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.entry.entry_id)},
            name=coordinator.entry.title or NAME,
            manufacturer="KI",
            model="Bassengstyring",
            sw_version=VERSION,
        )

    @property
    def data(self) -> dict:
        return self.coordinator.data or {}
