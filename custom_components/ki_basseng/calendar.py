"""Klorloggen som kalender i Home Assistant.

Hvert innslag er en hendelse, og neste forfallsdag er en heldagshendelse.
Kalenderen kan skrives til: en hendelse lagt inn i kalenderpanelet blir et
innslag i loggen, og en slettet hendelse forsvinner fra loggen. Tittelen på en ny
hendelse kan være et navn («Ida») eller «Klortablett · Ida».
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any

from homeassistant.components.calendar import (
    CalendarEntity,
    CalendarEntityFeature,
    CalendarEvent,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .coordinator import KiBassengCoordinator
from .entity import KiBassengEntity

NESTE_UID = "neste"
VARIGHET = timedelta(minutes=15)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: KiBassengCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([KiBassengChlorineCalendar(coordinator)])


def who_from_summary(summary: str, names: list[str]) -> str:
    """«Klortablett · Ida», «Ida» eller «klor ida» → «Ida» når navnet er kjent."""
    tekst = (summary or "").strip()
    if "·" in tekst:
        tekst = tekst.split("·", 1)[1].split("(")[0].strip()
    for name in names:
        if name.lower() in tekst.lower().split() or name.lower() == tekst.lower():
            return name
    if tekst and tekst.lower() not in ("klortablett", "klor", "klortabletter"):
        return tekst
    return ""


class KiBassengChlorineCalendar(KiBassengEntity, CalendarEntity):
    _attr_name = "Klorlogg"
    _attr_icon = "mdi:pill"
    _attr_supported_features = (
        CalendarEntityFeature.CREATE_EVENT | CalendarEntityFeature.DELETE_EVENT
    )

    def __init__(self, coordinator: KiBassengCoordinator) -> None:
        super().__init__(coordinator, "klorlogg")

    def _events(self) -> list[CalendarEvent]:
        events: list[CalendarEvent] = []
        for row in self.coordinator.chlorine:
            start = dt_util.parse_datetime(str(row.get("tid")))
            if start is None:
                continue
            start = dt_util.as_local(start)
            events.append(
                CalendarEvent(
                    start=start,
                    end=start + VARIGHET,
                    summary=self.coordinator.chlorine_summary(row),
                    description=row.get("notat") or None,
                    uid=str(row.get("tid")),
                )
            )
        neste = (self.data.get("chlorine") or {}).get("next")
        if neste is not None:
            dag = dt_util.as_local(neste).date()
            events.append(
                CalendarEvent(
                    start=dag,
                    end=dag + timedelta(days=1),
                    summary="Klortablett bør legges i",
                    uid=NESTE_UID,
                )
            )
        return events

    @property
    def event(self) -> CalendarEvent | None:
        now = dt_util.now()
        kommende = [e for e in self._events() if e.end_datetime_local >= now]
        return min(kommende, key=lambda e: e.start_datetime_local, default=None)

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        return [
            e
            for e in self._events()
            if e.end_datetime_local > start_date and e.start_datetime_local < end_date
        ]

    async def async_create_event(self, **kwargs: Any) -> None:
        start = kwargs.get("dtstart")
        if isinstance(start, date) and not isinstance(start, datetime):
            # Heldagshendelse: midt på dagen, så den ikke glir over i nabodøgnet
            start = datetime.combine(start, time(12, 0), tzinfo=dt_util.DEFAULT_TIME_ZONE)
        who = who_from_summary(kwargs.get("summary", ""), self.coordinator.chlorine_names)
        await self.coordinator.async_log_chlorine(
            1, kwargs.get("description") or "", who, when=start
        )

    async def async_delete_event(
        self,
        uid: str,
        recurrence_id: str | None = None,
        recurrence_range: str | None = None,
    ) -> None:
        if uid == NESTE_UID:
            raise HomeAssistantError("Forfallsdagen regnes ut og kan ikke slettes")
        if not await self.coordinator.async_delete_chlorine(uid):
            raise HomeAssistantError("Fant ikke klortabletten i loggen")
