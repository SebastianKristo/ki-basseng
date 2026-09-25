"""Konstanter for KI Basseng."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "ki_basseng"
NAME = "KI Basseng"
VERSION = "1.8.0"
STORAGE_VERSION = 1

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CALENDAR,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.TEXT,
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
CONF_WEATHER = "weather_entity"
CONF_COVER = "cover_entity"
CONF_PRESENCE = "presence_entities"
CONF_COVER_INVERT = "cover_invert"
CONF_HOUSE_SENSOR = "house_sensor"
CONF_HEATERS = "heater_entities"
CONF_CALENDAR = "calendar_entity"
# Vannivå (1.8): en vannsensor festet i bassenget, våt = nok vann
CONF_LEVEL_SENSOR = "level_sensor"
CONF_FILL_VALVE = "fill_valve"
CONF_NOTIFY = "notify_services"

CONF_VOLUME = "volume_m3"
CONF_FLOW = "flow_m3h"
CONF_PUMP_BASELINE = "pump_baseline_w"
CONF_HP_NOMINAL = "hp_nominal_w"
CONF_CURRENCY = "currency"
CONF_AREA = "surface_m2"
CONF_COLLECTOR_AREA = "collector_m2"

DEFAULT_VOLUME = 40.95
DEFAULT_FLOW = 11.3
DEFAULT_PUMP_BASELINE = 800.0
DEFAULT_HP_NOMINAL = 1470.0
DEFAULT_CURRENCY = "SEK"
DEFAULT_AREA = 24.1  # 7,3 × 3,3
DEFAULT_COLLECTOR_AREA = 0.0

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
MODE_SOLAR = "solvarme"
MODE_WINTER = "vinter"
MODE_FROST = "frostsikring"

MODES = [
    MODE_MANUAL,
    MODE_REST,
    MODE_MAINTENANCE,
    MODE_FILTER,
    MODE_HEATING,
    MODE_BOOST,
    MODE_SPRINKLER,
    MODE_SOLAR,
    MODE_WINTER,
    MODE_FROST,
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
    # Vannivå: minutter sensoren må være tørr før varsel, lengste påfylling
    "level_dry_minutes": 45,
    "fill_max_minutes": 60,
    "auto_fill": False,
    "level_notify": True,
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
    # Varmepumpa står av i natt bare når simuleringen sier at det sparer
    "smart_setback": True,
    # Integrasjonen eier settpunktet: ønsket temperatur, minus borte-senking
    "manage_setpoint": True,
    # Brukes når det ikke finnes en entitet for taket
    "cover_on": False,
    # Kjør sirkulasjonen når solfangeren har varme å gi
    "solar_harvest": True,
    # Vinter: ingen oppvarming, lite sirkulasjon, frostsikring av bassenghuset
    "winter_mode": False,
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
    "target_temp": 27.0,
    "away_drop": 2.0,
    "max_drop": 3.0,
    "u_open": 15.0,  # W/(m²·K), inkludert fordampning
    "u_covered": 5.0,
    "cover_solar": 60.0,  # % av solen som slipper gjennom taket
    "chlorine_days": 7.0,
    "frost_house_min": 5.0,  # varmeelementene på under dette i bassenghuset
    "frost_pump_below": 0.0,  # sirkulasjon hele tiden under dette ute
    "winter_turnovers": 0.5,
    # Hvem som kan legge i klortabletter, kommaseparert: «Sebastian, Ida»
    "chlorine_names": "",
    # valg
    "profile": PROFILE_BALANCED,
    "setback_criterion": "begge",
}

# Lært av målinger, overlever omstart. Faktorene justerer modellen mot
# virkeligheten: 1,0 betyr at tabellverdiene stemmer.
DEFAULT_LEARNED: dict = {
    "cop_factor": 1.0,
    "loss_open": 1.0,
    "loss_covered": 1.0,
    "cop_samples": 0,
    "loss_samples": 0,
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
    "chlorine_total": 0,  # nullstilles ikke ved døgnskifte
    # Oppdelingen av «spart i dag». Bare timer med kjent pris telles, så de går opp.
    "ref_kwh_today": 0.0,  # kWh pumpa ville brukt i døgndrift
    "pump_kwh_priced": 0.0,  # kWh pumpa faktisk brukte, i de samme timene
    "pump_cost_today": 0.0,
    "hp_cost_today": 0.0,
    "setback_kwh_today": 0.0,  # anslått: nattsenkingen som startet i dag
    "setback_cost_today": 0.0,
    "cover_kwh_today": 0.0,  # anslått: varmetap taket hindret, i strøm
    "cover_cost_today": 0.0,
    "split_day": "",  # dagen tellerne over har vært med hele døgnet
    # Målt besparelse bakover i tid; dagen i dag legges til ved døgnskiftet
    "saved_yesterday": 0.0,
    "saved_month": 0.0,
    "saved_month_key": "",
    "saved_total": 0.0,
}

# Tellerne som starter på null hvert døgn
DAILY_COUNTERS = (
    "volume_today",
    "runtime_today",
    "pump_kwh_today",
    "hp_kwh_today",
    "cost_today",
    "cost_reference",
    "sprinkler_today",
    "ref_kwh_today",
    "pump_kwh_priced",
    "pump_cost_today",
    "hp_cost_today",
    "setback_kwh_today",
    "setback_cost_today",
    "cover_kwh_today",
    "cover_cost_today",
)

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
SERVICE_LOG_CHLORINE = "logg_klortablett"
SERVICE_UNDO_CHLORINE = "angre_klortablett"
SERVICE_DELETE_CHLORINE = "slett_klortablett"

ATTR_MINUTES = "minutter"
ATTR_PROFILE = "profil"
ATTR_COUNT = "antall"
ATTR_NOTE = "notat"
ATTR_WHO = "hvem"
ATTR_WHEN = "tidspunkt"
ATTR_ID = "tid"
# Varmeelementene slås av igjen så mange grader over grensen
FROST_HYSTERESIS = 2.0

# Hvor mange klortablett-innslag som tas vare på
CHLORINE_HISTORY = 50
# Vannet regnes som varmebehov når det er så mye under målet
HEAT_HYSTERESIS = 0.3
# Solfangeren kan lagre litt over målet før sirkulasjonen stopper
SOLAR_OVERSHOOT = 1.0
SOLAR_MIN_IRRADIANCE = 250.0
