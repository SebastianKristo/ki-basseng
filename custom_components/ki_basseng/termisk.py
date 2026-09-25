"""Varmemodellen: sol, varmetap, COP og nattsenking.

Ren Python uten Home Assistant, slik at den kan testes for seg.

Bassenget er ett stort varmelager. 40 m³ vann holder 1,163 kWh per grad per m³,
altså rundt 48 kWh for hver grad. Varmetapet går gjennom overflaten og er omtrent
proporsjonalt med forskjellen mellom vann og luft; tak eller duk kutter det meste.
Solen varmer, både direkte på vannflaten og via en eventuell solfanger.

Spørsmålet nattsenkingen skal svare på: lønner det seg å slå av varmepumpen noen
timer i natt og varme opp igjen etterpå?

Kaldere vann taper mindre varme, så senking sparer alltid litt *varme*. Men
varmepumpen kan bruke mer *strøm* på å levere den varmen igjen: om morgenen er
lufta kaldest og COP lavest, gjenoppvarmingen kan havne i dyre timer, og
sirkulasjonspumpen må gå så lenge varmepumpen jobber. Derfor simuleres begge
alternativene time for time, og senking velges bare når den faktisk sparer.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

# Vannets varmekapasitet: 4186 J/(kg·K) × 1000 kg/m³ / 3,6e6 J/kWh
KWH_PER_M3_K = 1.163
# Andel av sirkulasjonspumpens effekt som ender som varme i vannet
PUMP_HEAT_FRACTION = 0.7
# Andel av solinnstrålingen vannflaten tar opp uten tak
POOL_SOLAR_ABSORPTION = 0.75
# Virkningsgrad for en enkel, uglasert solfanger
COLLECTOR_EFFICIENCY = 0.5

CRITERION_BOTH = "begge"
CRITERION_COST = "kostnad"
CRITERION_ENERGY = "energi"
CRITERIA = [CRITERION_BOTH, CRITERION_COST, CRITERION_ENERGY]

# Vannet må være innenfor dette av målet når bassenget skal være klart
READY_MARGIN = 0.15
# Ligger vannet mer enn dette under målet, senkes det ikke før det er tatt igjen
BEHIND_MARGIN = 0.5

# Senking må spare minst dette for å være verdt å slå av varmepumpen
MIN_SAVING_KWH = 0.2
MIN_SAVING_SHARE = 0.02


# --------------------------------------------------------------------------
# Sol
# --------------------------------------------------------------------------
def sun_elevation(when: datetime, lat: float, lon: float) -> float:
    """Solhøyde i grader over horisonten (NOAA-tilnærming, ±0,5°)."""
    utc = when.astimezone(timezone.utc)
    doy = utc.timetuple().tm_yday
    hour = utc.hour + utc.minute / 60 + utc.second / 3600
    gamma = 2 * math.pi / 365 * (doy - 1 + (hour - 12) / 24)
    eqtime = 229.18 * (
        0.000075
        + 0.001868 * math.cos(gamma)
        - 0.032077 * math.sin(gamma)
        - 0.014615 * math.cos(2 * gamma)
        - 0.040849 * math.sin(2 * gamma)
    )
    decl = (
        0.006918
        - 0.399912 * math.cos(gamma)
        + 0.070257 * math.sin(gamma)
        - 0.006758 * math.cos(2 * gamma)
        + 0.000907 * math.sin(2 * gamma)
        - 0.002697 * math.cos(3 * gamma)
        + 0.00148 * math.sin(3 * gamma)
    )
    true_minutes = hour * 60 + eqtime + 4 * lon
    hour_angle = math.radians(true_minutes / 4 - 180)
    phi = math.radians(lat)
    cos_zenith = math.sin(phi) * math.sin(decl) + math.cos(phi) * math.cos(
        decl
    ) * math.cos(hour_angle)
    cos_zenith = max(-1.0, min(1.0, cos_zenith))
    return 90 - math.degrees(math.acos(cos_zenith))


def irradiance(elevation: float, cloud: float | None) -> float:
    """Globalstråling på horisontal flate i W/m².

    Klarvær etter Haurwitz, dempet for skydekke etter Kasten–Czeplak.
    `cloud` er andel 0–1; ukjent skydekke regnes som halvskyet.
    """
    if elevation <= 0:
        return 0.0
    sin_e = math.sin(math.radians(elevation))
    clear = 1098 * sin_e * math.exp(-0.057 / sin_e)
    c = 0.5 if cloud is None else max(0.0, min(1.0, cloud))
    return max(0.0, clear * (1 - 0.75 * c**3.4))


# --------------------------------------------------------------------------
# Bassenget
# --------------------------------------------------------------------------
@dataclass
class Pool:
    """Det modellen trenger å vite om bassenget og utstyret."""

    volume: float  # m³
    area: float  # m² vannflate
    u_open: float  # W/(m²·K) uten tak
    u_covered: float  # W/(m²·K) med tak
    cover_solar: float  # andel sol som slipper gjennom taket
    hp_nominal_w: float  # elektrisk effekt når varmepumpen går
    pump_w: float  # sirkulasjonspumpen
    collector_area: float = 0.0  # m² solfanger
    cop_factor: float = 1.0  # lært korreksjon av COP-kurven
    loss_factor: float = 1.0  # lært korreksjon av varmetapet

    @property
    def capacity_kwh_k(self) -> float:
        return self.volume * KWH_PER_M3_K

    def loss_w(self, water: float, air: float, covered: bool) -> float:
        u = self.u_covered if covered else self.u_open
        return u * self.area * (water - air) * self.loss_factor

    def solar_w(self, ghi: float, covered: bool, pump_on: bool) -> float:
        share = self.cover_solar if covered else 1.0
        gain = ghi * self.area * POOL_SOLAR_ABSORPTION * share
        if pump_on and self.collector_area > 0:
            gain += ghi * self.collector_area * COLLECTOR_EFFICIENCY
        return gain

    def cop(self, air: float, water: float) -> float:
        """Luft-til-vann-COP for bassengvarmepumper.

        Ligger rundt 5 ved 15 °C luft og 26 °C vann, faller med kaldere luft og
        varmere vann. Læres mot målt COP gjennom `cop_factor`.
        """
        base = 5.0 + 0.13 * (air - 15) - 0.06 * (water - 26)
        return max(1.5, min(9.0, base * self.cop_factor))


@dataclass
class Hour:
    """Forholdene i én time av horisonten."""

    start: datetime
    air: float
    ghi: float
    price: float | None
    filter_hour: bool  # sirkulasjonspumpen går uansett for filtreringens skyld


@dataclass
class Result:
    kwh: float
    cost: float
    temp_end: float
    temp_min: float
    reached_at: datetime | None
    hp_hours: float


def simulate(
    pool: Pool,
    hours: list[Hour],
    start_temp: float,
    target: float,
    covered: bool,
    off: set[int] = frozenset(),
) -> Result:
    """Simuler varmepumpen som termostat mot `target`, av i timene `off`.

    Når den er på, dekker den varmetapet og tar igjen det som mangler så fort
    kapasiteten tillater. Sirkulasjonspumpen må gå så lenge varmepumpen jobber;
    i filtreringstimer går den uansett og koster ikke ekstra.
    """
    temp = start_temp
    kwh = cost = hp_hours = 0.0
    temp_min = temp
    reached_at: datetime | None = None
    cap = pool.capacity_kwh_k
    for i, h in enumerate(hours):
        price = h.price if h.price is not None else 1.0
        base_pump = h.filter_hour
        gain = pool.solar_w(h.ghi, covered, base_pump)
        if base_pump:
            gain += pool.pump_w * PUMP_HEAT_FRACTION
        net_w = gain - pool.loss_w(temp, h.air, covered)

        frac = 0.0
        if i not in off:
            need_kwh = (target - temp) * cap - net_w / 1000
            if need_kwh > 0:
                cop = pool.cop(h.air, temp)
                # Går pumpen bare for varmepumpens skyld, bidrar den også med
                # egen spillvarme og eventuell solfanger mens den går
                extra_w = 0.0
                if not base_pump:
                    extra_w = (
                        pool.solar_w(h.ghi, covered, True)
                        - pool.solar_w(h.ghi, covered, False)
                        + pool.pump_w * PUMP_HEAT_FRACTION
                    )
                full_w = pool.hp_nominal_w * cop + extra_w
                frac = min(1.0, need_kwh * 1000 / full_w) if full_w > 0 else 0.0
                net_w += full_w * frac
                hp_kwh = pool.hp_nominal_w * frac / 1000
                pump_kwh = 0.0 if base_pump else pool.pump_w * frac / 1000
                kwh += hp_kwh + pump_kwh
                cost += (hp_kwh + pump_kwh) * price
                hp_hours += frac

        temp += net_w / 1000 / cap
        if frac > 0:
            # Termostaten stopper på settpunktet
            temp = min(temp, target)
        temp_min = min(temp_min, temp)
        if reached_at is None and temp >= target - 0.1:
            reached_at = h.start + timedelta(hours=1)

    # Sluttavregning: det som mangler på målet ved horisontens slutt må varmes
    # inn senere. Regn det som strøm i siste time, ellers ville et vindu som
    # bare utsetter oppvarmingen se ut som en besparelse.
    if hours and temp < target:
        last = hours[-1]
        price = last.price if last.price is not None else 1.0
        cop = pool.cop(last.air, temp)
        deficit = (target - temp) * cap / cop
        if not last.filter_hour:
            deficit *= 1 + pool.pump_w / pool.hp_nominal_w
        kwh += deficit
        cost += deficit * price
    return Result(
        kwh=round(kwh, 3),
        cost=round(cost, 3),
        temp_end=round(temp, 2),
        temp_min=round(temp_min, 2),
        reached_at=reached_at,
        hp_hours=round(hp_hours, 2),
    )


@dataclass
class SetbackDecision:
    """Svaret på «bør varmepumpen stå av i natt?»."""

    worth_it: bool
    start: datetime | None = None
    end: datetime | None = None
    reason: str = ""
    saving_kwh: float = 0.0
    saving_cost: float = 0.0
    baseline: Result | None = None
    best: Result | None = None
    candidates: int = 0
    evaluated: list[dict] = field(default_factory=list)

    def active(self, now: datetime) -> bool:
        return (
            self.worth_it
            and self.start is not None
            and self.end is not None
            and self.start <= now < self.end
        )


def optimise_setback(
    pool: Pool,
    hours: list[Hour],
    start_temp: float,
    target: float,
    covered: bool,
    night: set[int],
    deadline_index: int,
    max_drop: float,
    criterion: str = CRITERION_BOTH,
) -> SetbackDecision:
    """Finn det av-vinduet i natt som sparer mest, eller ingen.

    `hours[0]` er inneværende time. `night` er indeksene der varmepumpen får stå
    av; vinduet må være sammenhengende og ligge i natten. Vannet må være tilbake
    på `target` innen `deadline_index` (timen da bassenget skal være klart), og
    får aldri falle mer enn `max_drop` under målet.
    """
    if not hours or not night:
        return SetbackDecision(False, reason="Ingen natt-timer igjen før badeklar")

    horizon = hours[: max(1, min(len(hours), deadline_index))]
    baseline = simulate(pool, horizon, start_temp, target, covered)
    decision = SetbackDecision(False, baseline=baseline)
    if baseline.kwh <= 0:
        decision.reason = "Varmepumpen trenger ikke gå i natt uansett"
        return decision
    # Ligger vannet alt under målet, skal det tas igjen først. Og rekker ikke
    # varmepumpa målet selv om den går hele natta, er det ingenting å senke:
    # da ville senkingen bare gjort morgenen kaldere.
    if start_temp < target - BEHIND_MARGIN:
        decision.reason = "Vannet er under målet – tar igjen varmen først"
        return decision
    if baseline.temp_end < target - READY_MARGIN:
        decision.reason = "Varmepumpa rekker ikke målet selv om den går hele natta"
        return decision

    night_idx = sorted(i for i in night if i < len(horizon))
    best: tuple[float, int, int, Result] | None = None
    evaluated: list[dict] = []
    for a in night_idx:
        for b in night_idx:
            if b < a or any(i not in night for i in range(a, b + 1)):
                continue
            off = set(range(a, b + 1))
            res = simulate(pool, horizon, start_temp, target, covered, off)
            decision.candidates += 1
            ok_ready = res.temp_end >= target - READY_MARGIN
            ok_drop = res.temp_min >= target - max_drop
            save_kwh = baseline.kwh - res.kwh
            save_cost = baseline.cost - res.cost
            evaluated.append(
                {
                    "fra": horizon[a].start.strftime("%H:%M"),
                    "til": (horizon[b].start + timedelta(hours=1)).strftime("%H:%M"),
                    "kwh": res.kwh,
                    "kostnad": res.cost,
                    "temp_min": res.temp_min,
                    "klar": ok_ready,
                }
            )
            if not (ok_ready and ok_drop):
                continue
            if not _saves(criterion, baseline, save_kwh, save_cost):
                continue
            score = save_cost if criterion != CRITERION_ENERGY else save_kwh
            if best is None or score > best[0]:
                best = (score, a, b, res)

    decision.evaluated = sorted(
        evaluated, key=lambda e: e["kostnad"] if criterion != CRITERION_ENERGY else e["kwh"]
    )
    if best is None:
        klar = [e for e in evaluated if e["klar"]]
        if not klar:
            decision.reason = "Rekker ikke å varme opp igjen før badeklar"
        else:
            decision.reason = "Gjenoppvarming koster like mye som den sparer"
        return decision

    _, a, b, res = best
    decision.worth_it = True
    decision.start = horizon[a].start
    decision.end = horizon[b].start + timedelta(hours=1)
    decision.best = res
    decision.saving_kwh = round(baseline.kwh - res.kwh, 2)
    decision.saving_cost = round(baseline.cost - res.cost, 2)
    decision.reason = (
        f"Av {decision.start:%H:%M}–{decision.end:%H:%M} sparer "
        f"{decision.saving_kwh:.1f} kWh".replace(".", ",")
    )
    return decision


def _saves(criterion: str, baseline: Result, kwh: float, cost: float) -> bool:
    enough_kwh = kwh >= max(MIN_SAVING_KWH, baseline.kwh * MIN_SAVING_SHARE)
    enough_cost = cost > max(0.0, baseline.cost * MIN_SAVING_SHARE)
    if criterion == CRITERION_ENERGY:
        return enough_kwh
    if criterion == CRITERION_COST:
        return enough_cost
    # Begge: spar penger, men aldri ved å bruke mer strøm totalt
    return enough_cost and kwh >= 0


# --------------------------------------------------------------------------
# Læring
# --------------------------------------------------------------------------
def ema(old: float, new: float, alpha: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, old + alpha * (new - old)))


def chlorine_interval_days(base_days: float, water_temp: float | None) -> float:
    """Varmt vann tærer raskere på kloret: kortere intervall over 24 °C."""
    if water_temp is None or water_temp <= 24:
        return base_days
    # Omtrent dobbelt forbruk ved 32 °C
    factor = 1 + (water_temp - 24) / 8
    return max(1.0, base_days / factor)
