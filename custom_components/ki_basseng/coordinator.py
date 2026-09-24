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

from . import termisk
from .const import (
    CHLORINE_HISTORY,
    CONF_AREA,
    CONF_CLIMATE,
    CONF_COLLECTOR_AREA,
    CONF_COVER,
    CONF_CURRENCY,
    CONF_FLOW,
    CONF_HP_NOMINAL,
    CONF_HP_POWER_SENSOR,
    CONF_INFLOW,
    CONF_OUTDOOR,
    CONF_OUTFLOW,
    CONF_POWER_SENSOR,
    CONF_PRESENCE,
    CONF_PRICE_SENSOR,
    CONF_PUMP_POWER_SENSOR,
    CONF_PUMP_SWITCH,
    CONF_VALVE,
    CONF_VOLUME,
    CONF_WEATHER,
    DEFAULT_AREA,
    DEFAULT_COLLECTOR_AREA,
    DEFAULT_COUNTERS,
    DEFAULT_CURRENCY,
    DEFAULT_FLOW,
    DEFAULT_HP_NOMINAL,
    DEFAULT_LEARNED,
    DEFAULT_SETTINGS,
    DEFAULT_VOLUME,
    DOMAIN,
    FALLBACK_HOURS,
    HEAT_HYSTERESIS,
    HP_MARGIN_W,
    MODE_BOOST,
    MODE_FILTER,
    MODE_HEATING,
    MODE_MAINTENANCE,
    MODE_MANUAL,
    MODE_REST,
    MODE_SOLAR,
    NIGHT_HOURS,
    NIGHT_PENALTY,
    POWER_NOISE_W,
    PROFILE_AWAY,
    PROFILE_CUSTOM,
    PROFILES,
    SOLAR_MIN_IRRADIANCE,
    SOLAR_OVERSHOOT,
    STORAGE_VERSION,
)

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(seconds=30)
UNKNOWN = ("unknown", "unavailable", "none", "None", "")
PRESENT_STATES = ("home", "on", "true", "hjemme")
# Nattsenkingen regnes ut på nytt hvert tiende minutt
SETBACK_RECALC_MIN = 10
# Ikke start en ny senking rett etter at en ble avbrutt
SETBACK_HOLD_S = 1800
# Tapslæringen trenger et rolig vindu av en viss lengde
LOSS_WINDOW_S = 3 * 3600


def split_names(raw: Any) -> list[str]:
    """«Sebastian, Ida ,sebastian» → ["Sebastian", "Ida"]: trimmet, uten duplikater."""
    names: list[str] = []
    for part in str(raw or "").replace(";", ",").split(","):
        name = part.strip()
        if name and name.lower() not in (n.lower() for n in names):
            names.append(name)
    return names


def _f(value: Any, default: Any = 0.0) -> Any:
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
        self._auto_rettet: int = 0
        self._save_pending: bool = False
        self._last_save: datetime | None = None

        # Varmemodellen
        self.learned: dict = dict(DEFAULT_LEARNED)
        self.chlorine: list[dict] = []
        self._prices_cache: tuple[dict[int, float], dict[int, float]] | None = None
        self._forecast: dict[datetime, tuple[Any, Any]] = {}
        self._forecast_at: datetime | None = None
        self._temp_est: float | None = None
        self._env: dict = {}
        self._setback: termisk.SetbackDecision | None = None
        self._setback_key: tuple | None = None
        self._setback_on: bool = False
        self._setback_ended: datetime | None = None
        self._setpoint_sent: tuple[float, datetime] | None = None
        self._loss_window: dict | None = None

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
        self.learned.update(stored.get("learned") or {})
        self.chlorine = list(stored.get("chlorine") or [])[-CHLORINE_HISTORY:]
        for key, value in DEFAULT_COUNTERS.items():
            self.counters.setdefault(key, value)

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
                "learned": self.learned,
                "chlorine": self.chlorine,
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
    def area(self) -> float:
        return max(_f(self.cfg(CONF_AREA), DEFAULT_AREA), 1.0)

    @property
    def collector_area(self) -> float:
        return max(_f(self.cfg(CONF_COLLECTOR_AREA), DEFAULT_COLLECTOR_AREA), 0.0)

    @property
    def turnover_hours(self) -> float:
        """Timer pumpedrift for én full omsetning av bassengvolumet."""
        return self.volume / self.flow

    @property
    def pump_on(self) -> bool:
        return self._pump_state

    async def _logbook(self, message: str, entity_id: str | None = None) -> None:
        """Skriv i loggboka hvis den finnes. Styringen skal aldri stoppe på den."""
        if not self.hass.services.has_service("logbook", "log"):
            return
        data = {"name": "KI Basseng", "message": message}
        if entity_id:
            data["entity_id"] = entity_id
        await self.hass.services.async_call("logbook", "log", data, blocking=False)

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
        self._prices_cache = None
        self._roll_day(now)
        power = self._accumulate(now)
        self._build_plan(now)
        await self._refresh_forecast(now)
        self._update_environment(now, power)
        self._plan_setback(now)
        mode, desired, reason = self._decide(now)
        await self._apply(mode, desired, now)
        await self._handle_sprinkler(now)
        await self._guard_setback(now)
        await self._guard_heatpump(now)
        await self._guard_setpoint(now)
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

        return {"pump_w": pump_w, "hp_w": hp_w, "price": price, "dt_s": dt_s}

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
        return self._num(CONF_PRICE_SENSOR)

    # -- priser og plan -----------------------------------------------
    def _prices(self) -> tuple[dict[int, float], dict[int, float]]:
        """Timespriser, lest én gang per tikk."""
        if self._prices_cache is None:
            self._prices_cache = self._read_prices()
        return self._prices_cache

    def _read_prices(self) -> tuple[dict[int, float], dict[int, float]]:
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

    def _heat_allowed(self, now: datetime) -> bool:
        """Får varmepumpen kreve sirkulasjon nå?

        Med smart nattsenking er det simuleringen som bestemmer når den skal stå
        av; ellers gjelder det faste varmevinduet.
        """
        if self._smart_setback_enabled():
            return not self._setback_on
        return self._heat_window(now)

    def _needs_heat(self) -> bool:
        temp = self._temp_est
        return temp is not None and temp < self.target_temp() - HEAT_HYSTERESIS

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

        heat = self._heat_running() or (self._hp_resume and self._needs_heat())
        if heat and self.settings["heat_priority"] and self._heat_allowed(now):
            return MODE_HEATING, True, "Varmepumpen varmer og trenger sirkulasjon"

        ghi = self._env.get("ghi", 0.0)
        temp = self._temp_est
        if (
            self.collector_area > 0
            and self.settings.get("solar_harvest")
            and ghi >= SOLAR_MIN_IRRADIANCE
            and temp is not None
            and temp < self.target_temp() + SOLAR_OVERSHOOT
        ):
            return MODE_SOLAR, True, f"Solfangeren har varme å gi ({ghi:.0f} W/m²)"

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

    # ------------------------------------------------------------------
    # Omgivelser: sted, sol, vær, tak og tilstedeværelse
    # ------------------------------------------------------------------
    @property
    def location(self) -> tuple[float, float]:
        return (self.hass.config.latitude, self.hass.config.longitude)

    def _outdoor_now(self) -> float | None:
        ute = self._num(CONF_OUTDOOR)
        if ute is not None:
            return ute
        weather = self._state(CONF_WEATHER)
        if weather is not None:
            return _f(weather.attributes.get("temperature"), None)
        return None

    def _cloud_now(self) -> float | None:
        weather = self._state(CONF_WEATHER)
        if weather is None:
            return None
        cloud = _f(weather.attributes.get("cloud_coverage"), None)
        return None if cloud is None else cloud / 100

    async def _refresh_forecast(self, now: datetime) -> None:
        """Hent timesvarsel for temperatur og skydekke hver halvtime."""
        weather = self.cfg(CONF_WEATHER)
        if not weather:
            return
        if self._forecast_at and (now - self._forecast_at).total_seconds() < 1800:
            return
        self._forecast_at = now
        try:
            response = await self.hass.services.async_call(
                "weather",
                "get_forecasts",
                {"entity_id": weather, "type": "hourly"},
                blocking=True,
                return_response=True,
            )
        except Exception as err:  # noqa: BLE001 – værmeldingen er et tillegg
            _LOGGER.debug("Fikk ikke timesvarsel fra %s: %s", weather, err)
            return
        rows = ((response or {}).get(weather) or {}).get("forecast") or []
        forecast: dict[datetime, tuple[Any, Any]] = {}
        for row in rows:
            stamp = dt_util.parse_datetime(str(row.get("datetime", "")))
            if stamp is None:
                continue
            key = dt_util.as_utc(stamp).replace(minute=0, second=0, microsecond=0)
            forecast[key] = (row.get("temperature"), row.get("cloud_coverage"))
        if forecast:
            self._forecast = forecast

    def _hours_ahead(self, now: datetime, count: int) -> list[termisk.Hour]:
        """Luft, sol, pris og filtreringsplan time for time fremover."""
        today, tomorrow = self._prices()
        lat, lon = self.location
        air_now = self._outdoor_now()
        cloud_now = self._cloud_now()
        start = dt_util.as_utc(now).replace(minute=0, second=0, microsecond=0)
        hours: list[termisk.Hour] = []
        for i in range(count):
            utc = start + timedelta(hours=i)
            local = dt_util.as_local(utc)
            day = (local.date() - now.date()).days
            prices = today if day == 0 else tomorrow if day == 1 else {}
            plan = self._plan if day == 0 else self._plan_tomorrow if day == 1 else []
            temp_fc, cloud_fc = self._forecast.get(utc, (None, None))
            air = _f(temp_fc, None)
            if air is None:
                air = air_now if air_now is not None else 15.0
            cloud = _f(cloud_fc, None)
            cloud = cloud / 100 if cloud is not None else cloud_now
            elevation = termisk.sun_elevation(utc + timedelta(minutes=30), lat, lon)
            hours.append(
                termisk.Hour(
                    start=local,
                    air=air,
                    ghi=termisk.irradiance(elevation, cloud),
                    price=prices.get(local.hour),
                    filter_hour=local.hour in plan,
                )
            )
        return hours

    def present(self) -> bool:
        """Er noen hjemme? Ferieprofil betyr borte; ingen entiteter betyr hjemme."""
        if self.settings.get("profile") == PROFILE_AWAY:
            return False
        entities = self.cfg(CONF_PRESENCE) or []
        if isinstance(entities, str):
            entities = [entities]
        known = False
        for entity in entities:
            state = self.hass.states.get(entity)
            if state is None or state.state in UNKNOWN:
                continue
            known = True
            if state.state.lower() in PRESENT_STATES:
                return True
            if entity.startswith("zone.") and _f(state.state) > 0:
                return True
        return not known

    def covered(self) -> bool:
        """Ligger taket på? En cover-entitet er «closed» når bassenget er dekket."""
        state = self._state(CONF_COVER)
        if state is None:
            return bool(self.settings.get("cover_on"))
        if state.entity_id.startswith("cover."):
            return state.state in ("closed", "closing")
        return state.state == "on"

    def target_temp(self) -> float:
        """Temperaturen bassenget skal holde nå.

        Eier vi settpunktet, er det ønsket temperatur minus borte-senking. Ellers
        er det varmepumpens eget settpunkt som gjelder.
        """
        wanted = _f(self.settings.get("target_temp"), 27)
        if not self.settings.get("manage_setpoint"):
            climate = self._state(CONF_CLIMATE)
            if climate is None:
                return wanted
            return _f(climate.attributes.get("temperature"), wanted)
        if not self.present():
            wanted -= _f(self.settings.get("away_drop"), 0)
        return wanted

    def _pool(self, covered: bool) -> termisk.Pool:
        s = self.settings
        return termisk.Pool(
            volume=self.volume,
            area=self.area,
            u_open=_f(s.get("u_open"), 15),
            u_covered=_f(s.get("u_covered"), 5),
            cover_solar=_f(s.get("cover_solar"), 60) / 100,
            hp_nominal_w=_f(self.cfg(CONF_HP_NOMINAL), DEFAULT_HP_NOMINAL),
            pump_w=_f(s.get("pump_baseline"), 800),
            collector_area=self.collector_area,
            cop_factor=_f(self.learned.get("cop_factor"), 1.0),
            loss_factor=_f(
                self.learned.get("loss_covered" if covered else "loss_open"), 1.0
            ),
        )

    # -- vanntemperatur og læring --------------------------------------
    def _measured_temp(self) -> float | None:
        """Vanntemperatur vi stoler på: bare når vannet har sirkulert en stund.

        Står pumpen, måler følerne vannet som står i røret.
        """
        since = (dt_util.utcnow() - self._pump_changed_at).total_seconds()
        if not self.pump_on or since < 180:
            return None
        inn = self._num(CONF_INFLOW)
        if inn is None:
            return None
        ut = self._num(CONF_OUTFLOW)
        # Innløpet er bassengvannet; utløpet er etter varmepumpen
        return inn if ut is None or ut >= inn else (inn + ut) / 2

    def _measured_cop(self, power: dict) -> tuple[float | None, float | None, float | None]:
        inn = self._num(CONF_INFLOW)
        ut = self._num(CONF_OUTFLOW)
        delta = round(ut - inn, 2) if (inn is not None and ut is not None) else None
        thermal = (
            round(self.flow * 1162.8 * delta)
            if (delta is not None and self.pump_on and 0.05 < delta < 3)
            else None
        )
        cop = (
            round(thermal / power["hp_w"], 2)
            if (thermal and power["hp_w"] > 300)
            else None
        )
        return delta, thermal, cop

    def _update_environment(self, now: datetime, power: dict) -> None:
        """Oppdater sol, luft, tak, estimert vanntemperatur og lærte faktorer."""
        covered = self.covered()
        lat, lon = self.location
        elevation = termisk.sun_elevation(now, lat, lon)
        ghi = termisk.irradiance(elevation, self._cloud_now())
        air = self._outdoor_now()
        pool = self._pool(covered)
        delta, thermal, cop = self._measured_cop(power)

        measured = self._measured_temp()
        if measured is not None:
            self._temp_est = measured
        elif self._temp_est is None:
            self._temp_est = self._water_temp()
        elif power["dt_s"] and air is not None:
            # Ingen pålitelig måling: la modellen føre temperaturen videre
            net = pool.solar_w(ghi, covered, self.pump_on) - pool.loss_w(
                self._temp_est, air, covered
            )
            if self.pump_on:
                net += power["pump_w"] * termisk.PUMP_HEAT_FRACTION
            if thermal:
                net += thermal
            self._temp_est += net * power["dt_s"] / 3_600_000 / pool.capacity_kwh_k

        temp = self._temp_est
        if cop and air is not None and temp is not None:
            raw = pool.cop(air, temp) / max(pool.cop_factor, 0.01)
            self.learned["cop_factor"] = round(
                termisk.ema(pool.cop_factor, cop / raw, 0.01, 0.5, 1.6), 4
            )
            self.learned["cop_samples"] = int(self.learned.get("cop_samples", 0)) + 1

        self._learn_loss(now, measured, air, covered, elevation, power)

        loss = pool.loss_w(temp, air, covered) if (temp is not None and air is not None) else None
        solar = pool.solar_w(ghi, covered, self.pump_on)
        self._env = {
            "elevation": round(elevation, 1),
            "ghi": round(ghi, 0),
            "air": air,
            "covered": covered,
            "present": self.present(),
            "target": round(self.target_temp(), 1),
            "loss_w": round(loss) if loss is not None else None,
            "solar_w": round(solar),
            "delta_t": delta,
            "thermal_w": thermal,
            "cop": cop,
            "cop_model": round(pool.cop(air, temp), 2)
            if (air is not None and temp is not None)
            else None,
        }

    def _learn_loss(
        self,
        now: datetime,
        measured: float | None,
        air: float | None,
        covered: bool,
        elevation: float,
        power: dict,
    ) -> None:
        """Lær varmetapet av rolige netter.

        Når pumpen går, varmepumpen står og solen er nede, er det bare
        pumpevarmen inn og varmetapet ut. Over noen timer gir fallet i
        temperatur hvor stort tapet faktisk er, og faktoren justeres mot det.
        """
        calm = (
            measured is not None
            and air is not None
            and power["hp_w"] < POWER_NOISE_W
            and elevation < -2
        )
        window = self._loss_window
        if not calm or (window and window["covered"] != covered):
            self._loss_window = None
            return
        if window is None:
            self._loss_window = {
                "t0": now, "temp0": measured, "air_sum": air, "n": 1, "covered": covered
            }
            return
        window["air_sum"] += air
        window["n"] += 1
        seconds = (now - window["t0"]).total_seconds()
        if seconds < LOSS_WINDOW_S:
            return
        self._loss_window = None
        pool = self._pool(covered)
        hours = seconds / 3600
        drop = window["temp0"] - measured
        if drop < 0.2:
            return
        observed = drop * pool.capacity_kwh_k * 1000 / hours + power["pump_w"] * (
            termisk.PUMP_HEAT_FRACTION
        )
        mean_water = (window["temp0"] + measured) / 2
        mean_air = window["air_sum"] / window["n"]
        raw = pool.loss_w(mean_water, mean_air, covered) / max(pool.loss_factor, 0.01)
        if raw < 200:
            return
        key = "loss_covered" if covered else "loss_open"
        self.learned[key] = round(
            termisk.ema(pool.loss_factor, observed / raw, 0.2, 0.3, 3.0), 3
        )
        self.learned["loss_samples"] = int(self.learned.get("loss_samples", 0)) + 1
        self._save_pending = True
        _LOGGER.info("Varmetap lært (%s): faktor %.2f", key, self.learned[key])

    # -- nattsenking ---------------------------------------------------
    def _smart_setback_enabled(self) -> bool:
        return bool(
            self.settings.get("smart_setback")
            and self.settings.get("manage_heatpump")
            and self.cfg(CONF_CLIMATE)
        )

    def _plan_setback(self, now: datetime) -> None:
        """Avgjør om varmepumpen bør stå av en stund i natt.

        Horisonten går fra nå til varmevinduet starter (badeklar). Natten er
        timene mellom varmevinduets slutt og start. Regnes ut på nytt hvert
        tiende minutt, så beslutningen følger vannet, været og prisene.
        """
        if not self._smart_setback_enabled():
            self._setback = None
            return
        key = (now.date(), now.hour, now.minute // SETBACK_RECALC_MIN)
        if key == self._setback_key:
            return
        self._setback_key = key

        start_h = int(_f(self.settings.get("heat_start"), 6)) % 24
        end_h = int(_f(self.settings.get("heat_end"), 22)) % 24
        horizon = (start_h - now.hour) % 24 or 24
        if start_h == end_h:
            self._setback = termisk.SetbackDecision(False, reason="Varmevinduet dekker hele døgnet")
            return
        if self._temp_est is None:
            self._setback = termisk.SetbackDecision(False, reason="Mangler vanntemperatur")
            return

        def is_night(hour: int) -> bool:
            if end_h < start_h:
                return end_h <= hour < start_h
            return hour >= end_h or hour < start_h

        hours = self._hours_ahead(now, horizon)
        night = {i for i, h in enumerate(hours) if is_night(h.start.hour)}
        covered = self.covered()
        self._setback = termisk.optimise_setback(
            self._pool(covered),
            hours,
            self._temp_est,
            self.target_temp(),
            covered,
            night,
            horizon,
            _f(self.settings.get("max_drop"), 3),
            self.settings.get("setback_criterion") or termisk.CRITERION_BOTH,
        )

    async def _guard_setback(self, now: datetime) -> None:
        """Slå varmepumpen av og på etter nattsenkingens vindu."""
        climate = self.cfg(CONF_CLIMATE)
        active = (
            self._smart_setback_enabled()
            and self._setback is not None
            and self._setback.active(now)
        )
        if active == self._setback_on or not climate:
            return
        if active and self._setback_ended and (
            (now - self._setback_ended).total_seconds() < SETBACK_HOLD_S
        ):
            return

        state = self.hass.states.get(climate)
        if active:
            self._setback_on = True
            if state is not None and state.state not in UNKNOWN and state.state != "off":
                self._hp_target = _f(state.attributes.get("temperature"), None)
                await self.hass.services.async_call(
                    "climate", "set_hvac_mode",
                    {"entity_id": climate, "hvac_mode": "off"}, blocking=False,
                )
            self._hp_resume = True
            melding = (
                f"Nattsenking {self._setback.start:%H:%M}–{self._setback.end:%H:%M}: "
                f"sparer {self._setback.saving_kwh:.1f} kWh "
                f"({self._setback.saving_cost:.2f} {self.currency})."
            )
        else:
            self._setback_on = False
            self._setback_ended = now
            # Sperren setter den på igjen når sirkulasjonen er i gang
            self._hp_resume = True
            melding = "Nattsenkingen er over, varmepumpa varmer igjen."
        _LOGGER.info(melding)
        await self._logbook(melding, climate)

    async def _guard_setpoint(self, now: datetime) -> None:
        """Hold varmepumpens settpunkt på ønsket temperatur (minus borte-senking)."""
        climate = self.cfg(CONF_CLIMATE)
        if not climate or not self.settings.get("manage_setpoint"):
            return
        target = round(self.target_temp(), 1)
        self._hp_target = target
        state = self.hass.states.get(climate)
        if state is None or state.state in UNKNOWN or state.state == "off":
            return
        current = _f(state.attributes.get("temperature"), None)
        if current is not None and abs(current - target) < 0.05:
            return
        # Samme verdi sendes ikke oftere enn hvert annet minutt, i tilfelle
        # varmepumpa runder av eller ignorerer den
        if self._setpoint_sent and self._setpoint_sent[0] == target and (
            (now - self._setpoint_sent[1]).total_seconds() < 120
        ):
            return
        self._setpoint_sent = (target, now)
        await self.hass.services.async_call(
            "climate", "set_temperature",
            {"entity_id": climate, "temperature": target}, blocking=False,
        )
        _LOGGER.debug("Settpunkt %s → %s", current, target)

    # ------------------------------------------------------------------
    # Klortabletter
    # ------------------------------------------------------------------
    @property
    def chlorine_names(self) -> list[str]:
        return split_names(self.settings.get("chlorine_names", ""))

    async def async_log_chlorine(
        self, count: int = 1, note: str = "", who: str = ""
    ) -> None:
        now = dt_util.now()
        self.chlorine.append(
            {
                "tid": now.isoformat(),
                "antall": int(count),
                "notat": note or "",
                "hvem": (who or "").strip(),
                "vanntemp": round(self._temp_est, 1) if self._temp_est is not None else None,
            }
        )
        self.chlorine = self.chlorine[-CHLORINE_HISTORY:]
        self.counters["chlorine_total"] = int(self.counters.get("chlorine_total", 0)) + int(count)
        self._save_pending = True
        flertall = "er" if count != 1 else ""
        hvem = f" av {who.strip()}" if who and who.strip() else ""
        await self._logbook(
            f"{int(count)} klortablett{flertall} lagt i{hvem}"
            + (f": {note}" if note else "")
        )
        await self.async_request_refresh()

    async def async_undo_chlorine(self) -> None:
        if not self.chlorine:
            return
        last = self.chlorine.pop()
        self.counters["chlorine_total"] = max(
            0, int(self.counters.get("chlorine_total", 0)) - int(last.get("antall", 1))
        )
        self._save_pending = True
        await self.async_request_refresh()

    def _chlorine_info(self, now: datetime) -> dict:
        last = None
        if self.chlorine:
            last = dt_util.parse_datetime(str(self.chlorine[-1].get("tid")))
        interval = termisk.chlorine_interval_days(
            _f(self.settings.get("chlorine_days"), 7), self._temp_est
        )
        next_at = last + timedelta(days=interval) if last else None
        week_ago = now - timedelta(days=7)
        week = 0
        per_person: dict[str, int] = {}
        for row in self.chlorine:
            stamp = dt_util.parse_datetime(str(row.get("tid")))
            if stamp and stamp >= week_ago:
                week += int(row.get("antall", 1))
            who = row.get("hvem") or ""
            if who:
                per_person[who] = per_person.get(who, 0) + int(row.get("antall", 1))
        return {
            "last": last,
            "next": next_at,
            "due": next_at is None or now >= next_at,
            "interval_days": round(interval, 1),
            "week": week,
            "total": int(self.counters.get("chlorine_total", 0)),
            "history": list(reversed(self.chlorine[-10:])),
            # Kompakt logg til kalenderen i kortet: dato, antall og hvem
            "log": [
                {"tid": r.get("tid"), "antall": r.get("antall", 1), "hvem": r.get("hvem", "")}
                for r in self.chlorine
            ],
            "names": self.chlorine_names,
            "per_person": per_person,
            "days_since": round((now - last).total_seconds() / 86400, 1) if last else None,
        }

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

        self._auto_rettet += 1
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
        await self._logbook(
            "Varmepumpa hadde gått i auto og er satt tilbake til heat.", climate
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
            if self._setback_on:
                return
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
        # Alt som påvirker varmemodellen gir ny vurdering av nattsenkingen
        self._setback_key = None
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
        if mode in (MODE_FILTER, MODE_HEATING, MODE_BOOST, MODE_SOLAR):
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
        env = self._env
        setback = self._setback
        chlorine = self._chlorine_info(now)

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
            "delta_t": env.get("delta_t"),
            "thermal_w": env.get("thermal_w"),
            "cop": env.get("cop"),
            "cop_model": env.get("cop_model"),
            "temp_estimate": round(self._temp_est, 2) if self._temp_est is not None else None,
            "target_temp": env.get("target"),
            "wanted_temp": _f(self.settings.get("target_temp"), 27),
            "present": env.get("present"),
            "covered": env.get("covered"),
            "outdoor": env.get("air"),
            "sun_elevation": env.get("elevation"),
            "irradiance": env.get("ghi"),
            "heat_loss_w": env.get("loss_w"),
            "solar_gain_w": env.get("solar_w"),
            "learned": dict(self.learned),
            "setback": self._setback_snapshot(setback, now),
            "setback_active": self._setback_on,
            "chlorine": chlorine,
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

    def _setback_snapshot(
        self, setback: termisk.SetbackDecision | None, now: datetime
    ) -> dict:
        if not self._smart_setback_enabled():
            return {"enabled": False, "reason": "Smart nattsenking er av"}
        if setback is None:
            return {"enabled": True, "reason": "Ikke beregnet ennå"}
        base = setback.baseline
        best = setback.best
        return {
            "enabled": True,
            "worth_it": setback.worth_it,
            "active": self._setback_on,
            "start": setback.start,
            "end": setback.end,
            "reason": setback.reason,
            "saving_kwh": setback.saving_kwh,
            "saving_cost": setback.saving_cost,
            "baseline_kwh": base.kwh if base else None,
            "baseline_cost": base.cost if base else None,
            "setback_kwh": best.kwh if best else None,
            "lowest_temp": best.temp_min if best else None,
            "candidates": setback.candidates,
            "alternatives": setback.evaluated[:5],
        }

    def _pump_cost_today(self) -> float:
        """Hva pumpen faktisk har kostet i dag, til bruk i besparelsen."""
        total_kwh = self.counters["pump_kwh_today"] + self.counters["hp_kwh_today"]
        if total_kwh <= 0:
            return 0.0
        andel = self.counters["pump_kwh_today"] / total_kwh
        return self.counters["cost_today"] * andel
