"""Konstanter for KI Basseng."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "ki_basseng"
NAME = "KI Basseng"
VERSION = "1.0.1"
STORAGE_VERSION = 1

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]

# --------------------------------------------------------------------------
# Konfigurasjon (config entry data/options)
# --------------------------------------------------------------------------
CONF_PUMP_SWITCH = "pump_switch"
CONF_POWER_SENSOR = "power_sensor"
CONF_PUMP_POWER_SENSOR = "pump_power_sensor"
CONF_HP_POWER_SENSOR = "hp_power_sensor"
CONF_PRICE_SENSOR = "price_sensor"

CONF_CLIMATE = "climate_entity"
CONF_INFLOW = "inflow_sensor"
CONF_OUTFLOW = "outflow_sensor"
CONF_OUTDOOR = "outdoor_sensor"
CONF_VALVE = "valve_switch"

CONF_VOLUME = "volume_m3"
CONF_FLOW = "flow_m3h"
CONF_PUMP_BASELINE = "pump_baseline_w"
CONF_HP_NOMINAL = "hp_nominal_w"
CONF_CURRENCY = "currency"

DEFAULT_VOLUME = 40.95
DEFAULT_FLOW = 11.3
DEFAULT_PUMP_BASELINE = 800.0
DEFAULT_HP_NOMINAL = 1470.0
DEFAULT_CURRENCY = "SEK"

# Under denne effekten regnes alt som «av» (målestøy fra smartpluggen)
POWER_NOISE_W = 25.0
# Hvor mye over basislasten varmepumpen må ligge før den regnes som i gang
HP_MARGIN_W = 100.0

# --------------------------------------------------------------------------
# Driftsmodus
# --------------------------------------------------------------------------
MODE_MANUAL = "manuell"
MODE_REST = "hvile"
MODE_MAINTENANCE = "vedlikehold"
MODE_FILTER = "filtrering"
MODE_HEATING = "oppvarming"
MODE_BOOST = "boost"
MODE_SPRINKLER = "spreder"

MODES = [
    MODE_MANUAL,
    MODE_REST,
    MODE_MAINTENANCE,
    MODE_FILTER,
    MODE_HEATING,
    MODE_BOOST,
    MODE_SPRINKLER,
]

# --------------------------------------------------------------------------
# Profiler: setter omsetningsmål og puls i ett grep
# --------------------------------------------------------------------------
PROFILE_ECO = "eco"
PROFILE_BALANCED = "balansert"
PROFILE_READY = "badeklar"
PROFILE_AWAY = "ferie"
PROFILE_CUSTOM = "egendefinert"

PROFILES: dict[str, dict[str, float]] = {
    PROFILE_ECO: {"turnovers": 1.0, "pulse_minutes": 5},
    PROFILE_BALANCED: {"turnovers": 1.5, "pulse_minutes": 10},
    PROFILE_READY: {"turnovers": 2.5, "pulse_minutes": 15},
    PROFILE_AWAY: {"turnovers": 0.75, "pulse_minutes": 0},
}
PROFILE_OPTIONS = [*PROFILES, PROFILE_CUSTOM]

# --------------------------------------------------------------------------
# Innstillinger som styres fra entiteter (lagres i .storage)
# --------------------------------------------------------------------------
DEFAULT_SETTINGS: dict = {
    # brytere
    "auto": True,
    "price_control": True,
    "heat_priority": True,
    "manage_heatpump": True,
    "pulse_with_heat": False,
    # Varmepumpa hopper selv over i «auto» av og til. I auto styrer den etter sin egen
    # logikk og kan like gjerne kjøle som varme, så den skal tilbake til «heat».
    "force_heat": True,
    "sprinkler_program": False,
    "frost_guard": True,
    # tall
    "turnovers": 1.5,
    "pulse_minutes": 10.0,
    "min_runtime": 15.0,
    "override_minutes": 60.0,
    "daytime_hours": 2.0,
    "heat_start": 6.0,
    "heat_end": 22.0,
    "pump_baseline": DEFAULT_PUMP_BASELINE,
    "sprinkler_duration": 10.0,
    "sprinkler_interval": 4.0,
    "sprinkler_daily_max": 60.0,
    # valg
    "profile": PROFILE_BALANCED,
}

DEFAULT_COUNTERS: dict = {
    "volume_today": 0.0,
    "volume_total": 0.0,
    "runtime_today": 0.0,  # sekunder
    "pump_kwh_today": 0.0,
    "hp_kwh_today": 0.0,
    "cost_today": 0.0,
    "cost_reference": 0.0,  # hva døgndrift ville kostet så langt
    "sprinkler_today": 0.0,  # minutter
    "sprinkler_last": 0.0,  # timestamp
}

# Reserveplan når prisdata mangler: spredt over døgnet, tyngde på dagtid
FALLBACK_HOURS = [7, 13, 8, 20, 14, 9, 21, 15, 6, 12, 19, 22, 10, 16]
# Nattillegg i planleggingen: strøm er billig kl. 03, men bassenget
# får ikke skummet av seg løv mens alle sover.
NIGHT_PENALTY = 0.20
NIGHT_HOURS = range(0, 6)

SIGNAL_UPDATE = f"{DOMAIN}_update"

SERVICE_START_SPREDER = "start_spreder"
SERVICE_STOP_SPREDER = "stopp_spreder"
SERVICE_BOOST = "boost"
SERVICE_SET_PROFILE = "sett_profil"

ATTR_MINUTES = "minutter"
ATTR_PROFILE = "profil"
