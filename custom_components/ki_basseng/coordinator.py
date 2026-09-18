"""Motoren i KI Basseng: planlegging, styring, telleverk."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    CONF_CLIMATE,
    CONF_CURRENCY,
    CONF_FLOW,
    CONF_HP_NOMINAL,
    CONF_HP_POWER_SENSOR,
    CONF_INFLOW,
    CONF_OUTDOOR,
    CONF_OUTFLOW,
    CONF_POWER_SENSOR,
    CONF_PRICE_SENSOR,
    CONF_PUMP_POWER_SENSOR,
    CONF_PUMP_SWITCH,
    CONF_VALVE,
    CONF_VOLUME,
    DEFAULT_COUNTERS,
    DEFAULT_CURRENCY,
    DEFAULT_FLOW,
    DEFAULT_HP_NOMINAL,
    DEFAULT_SETTINGS,
    DEFAULT_VOLUME,
    DOMAIN,
    FALLBACK_HOURS,
    HP_MARGIN_W,
    MODE_BOOST,
    MODE_FILTER,
    MODE_HEATING,
    MODE_MAINTENANCE,
    MODE_MANUAL,
    MODE_REST,
    NIGHT_HOURS,
    NIGHT_PENALTY,
    POWER_NOISE_W,
    PROFILE_CUSTOM,
    PROFILES,
    STORAGE_VERSION,
)

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=30)
UNKNOWN = ("unknown", "unavailable", "none", "None", "")


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


class KiBassengCoordinator(DataUpdateCoordinator[dict]):
    """Holder styr på sirkulasjon, varme, energi og spreder."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass, _LOGGER, name=DOMAIN, update_interval=SCAN_INTERVAL
        )
        self.entry = entry
        self._store: Store = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")
        self.settings: dict = dict(DEFAULT_SETTINGS)
        self.counters: dict = dict(DEFAULT_COUNTERS)

        self._day: str | None = None
        self._last_tick: datetime | None = None
        self._plan: list[int] = []
        self._plan_tomorrow: list[int] = []
        self._plan_signature: tuple | None = None

        self._commanded: bool | None = None
        self._commanded_at: datetime | None = None
        self._override_until: datetime | None = None
        self._pump_changed_at: datetime = dt_util.utcnow()
        self._pump_state: bool = False

        self._boost_until: datetime | None = None
        self._sprinkler_until: datetime | None = None
        self._sprinkler_started: datetime | None = None
        self._sprinkler_reason: str = "Klar"

        self._hp_resume: bool = False
        self._hp_target: float | None = None
        self._save_pending: bool = False
        self._last_save: datetime | None = None

    # ------------------------------------------------------------------
    # Oppsett
    # ------------------------------------------------------------------
    def cfg(self, key: str, default: Any = None) -> Any:
        return {**self.entry.data, **self.entry.options}.get(key, default)

    async def async_prepare(self) -> None:
        """Les lagret tilstand og koble opp lyttere."""
        stored = await self._store.async_load() or {}
        self.settings.update(stored.get("settings") or {})
        self.counters.update(stored.get("counters") or {})
        self._day = stored.get("day")
        self.counters.setdefault("sprinkler_last", 0.0)

        # Basislast kan være endret i options etter oppsett
        if "pump_baseline" not in (stored.get("settings") or {}):
            self.settings["pump_baseline"] = _f(
                self.cfg("pump_baseline_w"), self.settings["pump_baseline"]
            )

        pump = self.cfg(CONF_PUMP_SWITCH)
        if pump:
            state = self.hass.states.get(pump)
            self._pump_state = state is not None and state.state == "on"
            self.entry.async_on_unload(
                async_track_state_change_event(
                    self.hass, [pump], self._async_pump_changed
                )
            )

    async def async_persist(self) -> None:
        await self._store.async_save(
            {
                "settings": self.settings,
                "counters": self.counters,
                "day": self._day,
            }
        )
        self._save_pending = False

    # ------------------------------------------------------------------
    # Hjelpere mot HA-tilstander
    # ------------------------------------------------------------------
    def _state(self, key: str) -> Any:
        entity = self.cfg(key)
        if not entity:
            return None
        state = self.hass.states.get(entity)
        if state is None or state.state in UNKNOWN:
            return None
        return state

    def _num(self, key: str) -> float | None:
        state = self._state(key)
        if state is None:
            return None
        try:
            return float(state.state)
        except (TypeError, ValueError):
            return None

    @property
    def volume(self) -> float:
        return _f(self.cfg(CONF_VOLUME), DEFAULT_VOLUME)

    @property
    def flow(self) -> float:
        return max(_f(self.cfg(CONF_FLOW), DEFAULT_FLOW), 0.1)

    @property
    def currency(self) -> str:
        return self.cfg(CONF_CURRENCY) or DEFAULT_CURRENCY

    @property
    def turnover_hours(self) -> float:
        """Timer pumpedrift for én full omsetning av bassengvolumet."""
        return self.volume / self.flow

    @property
    def pump_on(self) -> bool:
        return self._pump_state

    # ------------------------------------------------------------------
    # Lyttere
    # ------------------------------------------------------------------
    @callback
    def _async_pump_changed(self, event: Event) -> None:
        new = event.data.get("new_state")
        if new is None or new.state in UNKNOWN:
            return
        is_on = new.state == "on"
        if is_on == self._pump_state:
            return
        self._pump_state = is_on
        self._pump_changed_at = dt_util.utcnow()

        # Var dette oss, eller en hånd på bryteren?
        ours = (
            self._commanded is not None
            and self._commanded == is_on
            and self._commanded_at is not None
            and (dt_util.utcnow() - self._commanded_at).total_seconds() < 20
        )
        if not ours and self.settings["auto"]:
            minutes = _f(self.settings.get("override_minutes"), 60)
            if minutes > 0:
                self._override_until = dt_util.now() + timedelta(minutes=minutes)
                _LOGGER.debug("Manuell overstyring til %s", self._override_until)

    # ------------------------------------------------------------------
    # Hovedløkke
    # ------------------------------------------------------------------
    async def _async_update_data(self) -> dict:
        now = dt_util.now()
        self._roll_day(now)
        power = self._accumulate(now)
        self._build_plan(now)
        mode, desired, reason = self._decide(now)
        await self._apply(mode, desired, now)
        await self._handle_sprinkler(now)
        await self._guard_heatpump(now)
        # Rekkefølgen betyr noe: sperren over kan nettopp ha satt den til «off», og
        # `_hp_resume` hindrer da at vakthunden tvinger den på igjen.
        await self._guard_auto_mode(now)

        eldre_enn_5_min = (
            self._last_save is None
            or (now - self._last_save).total_seconds() > 300
        )
        if self._save_pending or eldre_enn_5_min:
            self._last_save = now
            await self.async_persist()

        return self._snapshot(now, mode, desired, reason, power)

    # -- døgnrullering ------------------------------------------------
    def _roll_day(self, now: datetime) -> None:
        today = now.date().isoformat()
        if self._day == today:
            return
        if self._day is not None:
            _LOGGER.debug(
                "Nytt døgn: %.1f m³ pumpet, %.2f kWh",
                self.counters["volume_today"],
                self.counters["pump_kwh_today"],
            )
        self._day = today
        for key in (
            "volume_today",
            "runtime_today",
            "pump_kwh_today",
            "hp_kwh_today",
            "cost_today",
            "cost_reference",
            "sprinkler_today",
        ):
            self.counters[key] = 0.0
        self._plan_signature = None
        self._save_pending = True

    # -- telleverk ----------------------------------------------------
    def _accumulate(self, now: datetime) -> dict:
        last, self._last_tick = self._last_tick, now
        dt_s = 0.0 if last is None else (now - last).total_seconds()
        dt_s = max(0.0, min(dt_s, 300.0))

        pump_w, hp_w = self._split_power()
        price = self._price_now()

        if dt_s and self.pump_on:
            self.counters["volume_today"] += self.flow * dt_s / 3600
            self.counters["volume_total"] += self.flow * dt_s / 3600
            self.counters["runtime_today"] += dt_s

        if dt_s:
            pump_kwh = pump_w * dt_s / 3_600_000
            hp_kwh = hp_w * dt_s / 3_600_000
            self.counters["pump_kwh_today"] += pump_kwh
            self.counters["hp_kwh_today"] += hp_kwh
            if price is not None:
                self.counters["cost_today"] += (pump_kwh + hp_kwh) * price
                # Referanse: pumpen hadde gått hele døgnet, slik den gjorde før
                baseline_kwh = (
                    _f(self.settings.get("pump_baseline"), 800) * dt_s / 3_600_000
                )
                self.counters["cost_reference"] += baseline_kwh * price

        return {"pump_w": pump_w, "hp_w": hp_w, "price": price}

    def _split_power(self) -> tuple[float, float]:
        """Del den kombinerte smartpluggen i pumpe og varmepumpe.

        Smartpluggen måler begge. Pumpen ligger på en kjent basislast når
        den går, og resten tilhører varmepumpen. Bryterens tilstand brukes
        som fasit på om pumpen faktisk trekker noe, i stedet for å gjette
        ut fra terskelen alene.
        """
        direct_pump = self._num(CONF_PUMP_POWER_SENSOR)
        direct_hp = self._num(CONF_HP_POWER_SENSOR)
        if direct_pump is not None or direct_hp is not None:
            return (direct_pump or 0.0, direct_hp or 0.0)

        total = self._num(CONF_POWER_SENSOR)
        baseline = _f(self.settings.get("pump_baseline"), 800)
        if total is None:
            pump_w = baseline if self.pump_on else 0.0
            hp_w = _f(self.cfg(CONF_HP_NOMINAL), DEFAULT_HP_NOMINAL) if (
                self.pump_on and self._heat_running()
            ) else 0.0
            return (pump_w, hp_w)

        if total < POWER_NOISE_W:
            return (0.0, 0.0)
        if not self.pump_on:
            return (0.0, total)
        if total > baseline + HP_MARGIN_W:
            return (baseline, round(total - baseline, 1))
        return (round(total, 1), 0.0)

    def _price_now(self) -> float | None:
        state = self._state(CONF_PRICE_SENSOR)
        if state is None:
            return None
        try:
            return float(state.state)
        except (TypeError, ValueError):
            return None

    # -- priser og plan -----------------------------------------------
    def _prices(self) -> tuple[dict[int, float], dict[int, float]]:
        """Hent timespriser. Støtter Nordpool, ENTSO-e og enkle lister."""
        state = self._state(CONF_PRICE_SENSOR)
        today: dict[int, float] = {}
        tomorrow: dict[int, float] = {}
        if state is None:
            return today, tomorrow
        attrs = state.attributes

        def from_raw(raw: Any, target: dict[int, float]) -> None:
            if not isinstance(raw, list):
                return
            for row in raw:
                if not isinstance(row, dict):
                    continue
                value = row.get("value", row.get("price"))
                start = row.get("start", row.get("time"))
                if value is None or start is None:
                    continue
                stamp = dt_util.parse_datetime(str(start))
                if stamp is None:
                    continue
                target[dt_util.as_local(stamp).hour] = _f(value)

        def from_list(values: Any, target: dict[int, float]) -> None:
            if not isinstance(values, list) or len(values) < 12:
                return
            step = max(1, len(values) // 24)
            for hour in range(24):
                idx = hour * step
                if idx < len(values) and values[idx] is not None:
                    target.setdefault(hour, _f(values[idx]))

        from_raw(attrs.get("raw_today") or attrs.get("prices_today"), today)
        from_raw(attrs.get("raw_tomorrow") or attrs.get("prices_tomorrow"), tomorrow)
        if not today:
            from_list(attrs.get("today"), today)
        if not tomorrow:
            from_list(attrs.get("tomorrow"), tomorrow)
        return today, tomorrow

    def _needed_hours(self) -> float:
        return self.turnover_hours * _f(self.settings.get("turnovers"), 1.5)

    def _build_plan(self, now: datetime) -> None:
        today, tomorrow = self._prices()
        signature = (
            now.date().isoformat(),
            round(self._needed_hours(), 2),
            int(_f(self.settings.get("daytime_hours"), 2)),
            tuple(sorted(today.items())),
            tuple(sorted(tomorrow.items())),
        )
        if signature == self._plan_signature:
            return
        self._plan_signature = signature
        hours = max(1, round(self._needed_hours()))
        self._plan = self._pick_hours(today, hours, now.hour)
        self._plan_tomorrow = self._pick_hours(tomorrow, hours, None) if tomorrow else []

    def _pick_hours(
        self, prices: dict[int, float], count: int, protect_before: int | None
    ) -> list[int]:
        """Velg de billigste timene, men hold av noen dagtimer.

        Timer som allerede er passert i dag beholdes hvis de var planlagt,
        slik at planen ikke hopper rundt utover ettermiddagen.
        """
        if len(prices) < 12:
            return sorted(FALLBACK_HOURS[:count])

        keep: list[int] = []
        if protect_before is not None:
            keep = [h for h in self._plan if h < protect_before]
        count = max(0, count - len(keep))

        def score(hour: int) -> float:
            return prices[hour] + (NIGHT_PENALTY if hour in NIGHT_HOURS else 0.0)

        available = [h for h in prices if h not in keep]
        daytime_target = int(_f(self.settings.get("daytime_hours"), 2))
        chosen: list[int] = []

        daytime = sorted(
            [h for h in available if 10 <= h < 18], key=score
        )[: min(daytime_target, count)]
        chosen.extend(daytime)

        rest = sorted([h for h in available if h not in chosen], key=score)
        chosen.extend(rest[: max(0, count - len(chosen))])
        return sorted(set(keep + chosen))

    # -- beslutning ---------------------------------------------------
    def _heat_running(self) -> bool:
        state = self._state(CONF_CLIMATE)
        if state is None or state.state == "off":
            return False
        action = state.attributes.get("hvac_action")
        if action in ("heating", "cooling"):
            return True
        current = _f(state.attributes.get("current_temperature"), -99)
        target = _f(state.attributes.get("temperature"), -99)
        return current > -50 and target > -50 and current < target - 0.15

    def _heat_window(self, now: datetime) -> bool:
        start = int(_f(self.settings.get("heat_start"), 0))
        end = int(_f(self.settings.get("heat_end"), 24))
        if start == end:
            return True
        if start < end:
            return start <= now.hour < end
        return now.hour >= start or now.hour < end

    @property
    def turnovers_done(self) -> float:
        return self.counters["volume_today"] / max(self.volume, 0.1)

    @property
    def turnovers_left(self) -> float:
        return max(0.0, _f(self.settings.get("turnovers"), 1.5) - self.turnovers_done)

    def _decide(self, now: datetime) -> tuple[str, bool | None, str]:
        if not self.settings["auto"]:
            return MODE_MANUAL, None, "Automatikken er av"

        if self._override_until and now < self._override_until:
            igjen = int((self._override_until - now).total_seconds() // 60) + 1
            return MODE_MANUAL, None, f"Manuell overstyring i {igjen} min til"
        self._override_until = None

        if self._boost_until and now < self._boost_until:
            igjen = int((self._boost_until - now).total_seconds() // 60) + 1
            return MODE_BOOST, True, f"Boost i {igjen} min til"
        self._boost_until = None

        heat = self._heat_running()
        if heat and self.settings["heat_priority"] and self._heat_window(now):
            return MODE_HEATING, True, "Varmepumpen varmer og trenger sirkulasjon"

        left = self.turnovers_left
        if left > 0.005:
            if self.settings["price_control"] and self._plan:
                if now.hour in self._plan:
                    return (
                        MODE_FILTER,
                        True,
                        f"Planlagt filtrering, {left:.2f} omsetninger igjen",
                    )
                return (
                    MODE_REST,
                    False,
                    f"Venter på billig time, {left:.2f} omsetninger igjen",
                )
            return MODE_FILTER, True, f"Filtrerer, {left:.2f} omsetninger igjen"

        pulse = _f(self.settings.get("pulse_minutes"), 0)
        if pulse > 0:
            on = now.minute < pulse
            return (
                MODE_MAINTENANCE,
                on,
                f"Dagens mål er nådd, {int(pulse)} min sirkulasjon per time",
            )
        return MODE_REST, False, "Dagens mål er nådd"

    async def _apply(self, mode: str, desired: bool | None, now: datetime) -> None:
        pump = self.cfg(CONF_PUMP_SWITCH)
        if not pump or desired is None or desired == self.pump_on:
            return

        # Ikke slå av en pumpe som nettopp startet
        running_s = (dt_util.utcnow() - self._pump_changed_at).total_seconds()
        min_runtime = _f(self.settings.get("min_runtime"), 15) * 60
        if not desired and self.pump_on and running_s < min_runtime:
            return
        if desired and not self.pump_on and running_s < 120:
            return

        self._commanded = desired
        self._commanded_at = dt_util.utcnow()
        await self.hass.services.async_call(
            "switch",
            "turn_on" if desired else "turn_off",
            {"entity_id": pump},
            blocking=False,
        )
        _LOGGER.debug("Pumpe %s (%s)", "på" if desired else "av", mode)

    # -- varmepumpa hopper i auto -------------------------------------
    async def _guard_auto_mode(self, now: datetime) -> None:
        """Setter varmepumpa tilbake til «heat» når den selv går i «auto».

        Pumpa bytter modus på egen hånd — etter strømbrudd, etter en app-oppdatering,
        eller bare fordi den vil. I «auto» styrer den etter sin egen logikk og kan
        kjøle bassenget like gjerne som å varme det.

        To ting gjør dette trygt å kjøre hvert minutt:

        · Vi rører den bare når den står i «auto». «off» er noe vi selv setter når
          sirkulasjonen er av, og «heat» er der vi vil være.
        · Er den nettopp satt til «off» av sperren under, lar vi den være. Ellers ville
          de to reglene slåss: én slår av, den andre slår på igjen.
        """
        climate = self.cfg(CONF_CLIMATE)
        if not climate or not self.settings.get("force_heat", True):
            return
        state = self.hass.states.get(climate)
        if state is None or state.state != "auto":
            return
        # Har vi selv slått den av nettopp, skal den ikke tvinges på igjen
        if self._hp_resume:
            return

        self._auto_rettet = getattr(self, "_auto_rettet", 0) + 1
        await self.hass.services.async_call(
            "climate",
            "set_hvac_mode",
            {"entity_id": climate, "hvac_mode": "heat"},
            blocking=False,
        )
        _LOGGER.info(
            "Varmepumpa sto i auto og er satt tilbake til heat (%s. gang)",
            self._auto_rettet,
        )
        await self.hass.services.async_call(
            "logbook",
            "log",
            {"name": "KI Basseng",
             "message": "Varmepumpa hadde gått i auto og er satt tilbake til heat.",
             "entity_id": climate},
            blocking=False,
        )

    # -- varmepumpesperre ---------------------------------------------
    async def _guard_heatpump(self, now: datetime) -> None:
        climate = self.cfg(CONF_CLIMATE)
        if not climate or not self.settings["manage_heatpump"]:
            return
        state = self.hass.states.get(climate)
        if state is None or state.state in UNKNOWN:
            return

        since = (dt_util.utcnow() - self._pump_changed_at).total_seconds()

        if not self.pump_on and state.state != "off" and since > 60:
            self._hp_target = _f(state.attributes.get("temperature"), 26)
            self._hp_resume = True
            await self.hass.services.async_call(
                "climate",
                "set_hvac_mode",
                {"entity_id": climate, "hvac_mode": "off"},
                blocking=False,
            )
            _LOGGER.info("Varmepumpe av: ingen sirkulasjon")
            return

        if self.pump_on and self._hp_resume and since > 120:
            mode = self.data.get("mode") if self.data else None
            if mode == MODE_MAINTENANCE and not self.settings["pulse_with_heat"]:
                return
            if self._hp_target is not None:
                await self.hass.services.async_call(
                    "climate",
                    "set_temperature",
                    {"entity_id": climate, "temperature": self._hp_target},
                    blocking=False,
                )
            await self.hass.services.async_call(
                "climate",
                "set_hvac_mode",
                {"entity_id": climate, "hvac_mode": "heat"},
                blocking=False,
            )
            self._hp_resume = False
            _LOGGER.info("Varmepumpe på igjen: sirkulasjonen er tilbake")

    # ------------------------------------------------------------------
    # Spreder
    # ------------------------------------------------------------------
    @property
    def sprinkler_running(self) -> bool:
        return self._sprinkler_until is not None

    @property
    def sprinkler_left(self) -> float:
        if self._sprinkler_until is None:
            return 0.0
        return max(
            0.0, (self._sprinkler_until - dt_util.now()).total_seconds() / 60
        )

    async def async_start_sprinkler(self, minutes: float | None = None) -> None:
        valve = self.cfg(CONF_VALVE)
        if not valve:
            self._sprinkler_reason = "Ingen vannventil er satt opp"
            return
        if self.sprinkler_running:
            return

        minutes = minutes or _f(self.settings.get("sprinkler_duration"), 10)
        brukt = self.counters["sprinkler_today"]
        maks = _f(self.settings.get("sprinkler_daily_max"), 60)
        if maks > 0 and brukt + minutes > maks:
            minutes = max(0.0, maks - brukt)
            if minutes < 1:
                self._sprinkler_reason = f"Dagens grense på {int(maks)} min er brukt opp"
                self.async_update_listeners()
                return

        ute = self._num(CONF_OUTDOOR)
        if self.settings["frost_guard"] and ute is not None and ute < 2:
            self._sprinkler_reason = f"Frostvakt: det er {ute:.0f} °C ute"
            self.async_update_listeners()
            return

        self._sprinkler_started = dt_util.now()
        self._sprinkler_until = self._sprinkler_started + timedelta(minutes=minutes)
        self._sprinkler_reason = "Spreder går"
        await self.hass.services.async_call(
            "switch", "turn_on", {"entity_id": valve}, blocking=False
        )
        self.async_update_listeners()

    async def async_stop_sprinkler(self, reason: str = "Klar") -> None:
        valve = self.cfg(CONF_VALVE)
        if self._sprinkler_started is not None:
            brukt = (dt_util.now() - self._sprinkler_started).total_seconds() / 60
            self.counters["sprinkler_today"] += max(0.0, brukt)
            self.counters["sprinkler_last"] = dt_util.now().timestamp()
            self._save_pending = True
        self._sprinkler_until = None
        self._sprinkler_started = None
        self._sprinkler_reason = reason
        if valve:
            await self.hass.services.async_call(
                "switch", "turn_off", {"entity_id": valve}, blocking=False
            )
        self.async_update_listeners()

    async def _handle_sprinkler(self, now: datetime) -> None:
        if self._sprinkler_until and now >= self._sprinkler_until:
            await self.async_stop_sprinkler("Ferdig")
            return

        if not self.settings["sprinkler_program"] or self.sprinkler_running:
            return
        if not (10 <= now.hour < 20):
            return
        interval = _f(self.settings.get("sprinkler_interval"), 4)
        if interval <= 0:
            return
        siden = now.timestamp() - _f(self.counters.get("sprinkler_last"), 0)
        if siden < interval * 3600:
            return
        await self.async_start_sprinkler()

    async def async_boost(self, minutes: float = 30) -> None:
        self._boost_until = dt_util.now() + timedelta(minutes=minutes)
        self._override_until = None
        await self.async_request_refresh()

    async def async_reset_daily(self) -> None:
        for key in (
            "volume_today",
            "runtime_today",
            "pump_kwh_today",
            "hp_kwh_today",
            "cost_today",
            "cost_reference",
            "sprinkler_today",
        ):
            self.counters[key] = 0.0
        self._plan_signature = None
        await self.async_persist()
        await self.async_request_refresh()

    # ------------------------------------------------------------------
    # Innstillinger fra entiteter
    # ------------------------------------------------------------------
    async def async_set_setting(self, key: str, value: Any) -> None:
        if self.settings.get(key) == value:
            return
        self.settings[key] = value
        if key in ("turnovers", "pulse_minutes"):
            profile = self.settings.get("profile")
            preset = PROFILES.get(profile)
            if preset and _f(preset.get(key)) != _f(value):
                self.settings["profile"] = PROFILE_CUSTOM
        if key in ("turnovers", "daytime_hours"):
            self._plan_signature = None
        self._save_pending = True
        await self.async_request_refresh()

    async def async_set_profile(self, profile: str) -> None:
        preset = PROFILES.get(profile)
        self.settings["profile"] = profile
        if preset:
            self.settings.update(preset)
        self._plan_signature = None
        self._save_pending = True
        await self.async_request_refresh()

    # ------------------------------------------------------------------
    # Utdata til entitetene
    # ------------------------------------------------------------------
    def _blocks(self, hours: list[int]) -> list[str]:
        blocks: list[str] = []
        start = prev = None
        for hour in hours:
            if start is None:
                start = hour
            elif hour != prev + 1:
                blocks.append(f"{start:02d}:00-{prev + 1:02d}:00")
                start = hour
            prev = hour
        if start is not None:
            blocks.append(f"{start:02d}:00-{prev + 1:02d}:00")
        return blocks

    def _next_start(self, now: datetime, mode: str) -> datetime | None:
        if mode in (MODE_FILTER, MODE_HEATING, MODE_BOOST):
            return None
        if mode == MODE_MAINTENANCE:
            return (now + timedelta(hours=1)).replace(
                minute=0, second=0, microsecond=0
            )
        kommende = [h for h in self._plan if h > now.hour]
        if kommende:
            return now.replace(
                hour=kommende[0], minute=0, second=0, microsecond=0
            )
        if self._plan_tomorrow:
            i_morgen = now + timedelta(days=1)
            return i_morgen.replace(
                hour=self._plan_tomorrow[0], minute=0, second=0, microsecond=0
            )
        return None

    def _water_temp(self) -> float | None:
        inn = self._num(CONF_INFLOW)
        ut = self._num(CONF_OUTFLOW)
        if inn is not None and ut is not None and self.pump_on:
            return round((inn + ut) / 2, 2)
        if inn is not None:
            return round(inn, 2)
        state = self._state(CONF_CLIMATE)
        if state is not None:
            temp = state.attributes.get("current_temperature")
            if temp is not None:
                return round(_f(temp), 2)
        return None

    def _recommended(self, temp: float | None) -> float:
        """Varmt vann = raskere algevekst = flere omsetninger."""
        if temp is None:
            return 1.5
        if temp < 16:
            return 1.0
        if temp < 22:
            return 1.5
        if temp < 27:
            return 2.0
        return 2.5

    def _snapshot(
        self,
        now: datetime,
        mode: str,
        desired: bool | None,
        reason: str,
        power: dict,
    ) -> dict:
        temp = self._water_temp()
        prices_today, _ = self._prices()
        plan_prices = [prices_today[h] for h in self._plan if h in prices_today]
        snitt_plan = round(sum(plan_prices) / len(plan_prices), 3) if plan_prices else None
        snitt_dogn = (
            round(sum(prices_today.values()) / len(prices_today), 3)
            if prices_today
            else None
        )
        inn = self._num(CONF_INFLOW)
        ut = self._num(CONF_OUTFLOW)
        delta = round(ut - inn, 2) if (inn is not None and ut is not None) else None
        termisk = (
            round(self.flow * 1162.8 * delta)
            if (delta is not None and self.pump_on and 0.05 < delta < 3)
            else None
        )
        cop = (
            round(termisk / power["hp_w"], 2)
            if (termisk and power["hp_w"] > 300)
            else None
        )

        return {
            "mode": mode,
            "desired": desired,
            "reason": reason,
            "pump_on": self.pump_on,
            "plan": list(self._plan),
            "plan_tomorrow": list(self._plan_tomorrow),
            "blocks": self._blocks(self._plan),
            "blocks_tomorrow": self._blocks(self._plan_tomorrow),
            "next_start": self._next_start(now, mode),
            "planned_hours": len(self._plan),
            "needed_hours": round(self._needed_hours(), 2),
            "turnover_hours": round(self.turnover_hours, 2),
            "turnovers_done": round(self.turnovers_done, 3),
            "turnovers_target": _f(self.settings.get("turnovers"), 1.5),
            "turnovers_left": round(self.turnovers_left, 3),
            "recommended_turnovers": self._recommended(temp),
            "volume_today": round(self.counters["volume_today"], 2),
            "volume_total": round(self.counters["volume_total"], 2),
            "runtime_today": round(self.counters["runtime_today"] / 3600, 2),
            "pump_w": round(power["pump_w"], 1),
            "hp_w": round(power["hp_w"], 1),
            "pump_kwh_today": round(self.counters["pump_kwh_today"], 3),
            "hp_kwh_today": round(self.counters["hp_kwh_today"], 3),
            "cost_today": round(self.counters["cost_today"], 2),
            "saved_today": round(
                self.counters["cost_reference"] - self._pump_cost_today(), 2
            ),
            "price_now": power["price"],
            "price_plan_avg": snitt_plan,
            "price_day_avg": snitt_dogn,
            "water_temp": temp,
            "delta_t": delta,
            "thermal_w": termisk,
            "cop": cop,
            "override_until": self._override_until,
            "override": self._override_until is not None
            and now < self._override_until,
            "boost_until": self._boost_until,
            "sprinkler_running": self.sprinkler_running,
            "sprinkler_left": round(self.sprinkler_left, 1),
            "sprinkler_today": round(self.counters["sprinkler_today"], 1),
            "sprinkler_reason": self._sprinkler_reason,
            "hp_waiting": self._hp_resume,
            "currency": self.currency,
        }

    def _pump_cost_today(self) -> float:
        """Hva pumpen faktisk har kostet i dag, til bruk i besparelsen."""
        total_kwh = self.counters["pump_kwh_today"] + self.counters["hp_kwh_today"]
        if total_kwh <= 0:
            return 0.0
        andel = self.counters["pump_kwh_today"] / total_kwh
        return self.counters["cost_today"] * andel
