"""Integrasjonen i en ekte Home Assistant: oppsett, klorlogg, tak, tilstedeværelse
og nattsenkingen som slår varmepumpa av og på."""
from datetime import timedelta

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.ki_basseng import termisk
from custom_components.ki_basseng.const import (
    CONF_CLIMATE,
    CONF_COVER,
    CONF_INFLOW,
    CONF_OUTDOOR,
    CONF_PRESENCE,
    CONF_PUMP_SWITCH,
    CONF_WEATHER,
    DOMAIN,
)

CLIMATE = "climate.basseng"


@pytest.fixture
async def oppsett(hass: HomeAssistant):
    hass.config.latitude = 58.94
    hass.config.longitude = 11.17
    hass.states.async_set("switch.bassengpumpe", "off")
    hass.states.async_set(
        CLIMATE, "heat",
        {"temperature": 26, "current_temperature": 26.5, "hvac_action": "idle"},
    )
    hass.states.async_set("sensor.innlop", "26.5")
    hass.states.async_set("sensor.ute", "14")
    hass.states.async_set("person.sebastian", "home")
    hass.states.async_set("binary_sensor.pooltak", "off")
    hass.states.async_set("weather.hjem", "cloudy", {"temperature": 14, "cloud_coverage": 80})

    kall = {
        "hvac": async_mock_service(hass, "climate", "set_hvac_mode"),
        "temp": async_mock_service(hass, "climate", "set_temperature"),
        "on": async_mock_service(hass, "switch", "turn_on"),
        "off": async_mock_service(hass, "switch", "turn_off"),
        "logg": async_mock_service(hass, "logbook", "log"),
    }
    naa = dt_util.as_utc(dt_util.now()).replace(minute=0, second=0, microsecond=0)
    kall["vaer"] = async_mock_service(
        hass, "weather", "get_forecasts",
        response={"weather.hjem": {"forecast": [
            {"datetime": (naa + timedelta(hours=i)).isoformat(),
             "temperature": 12 + i % 5, "cloud_coverage": 30}
            for i in range(24)
        ]}},
        supports_response=True,
    )

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="KI Basseng",
        data={
            CONF_PUMP_SWITCH: "switch.bassengpumpe",
            CONF_CLIMATE: CLIMATE,
            CONF_INFLOW: "sensor.innlop",
            CONF_OUTDOOR: "sensor.ute",
            CONF_WEATHER: "weather.hjem",
            CONF_COVER: "binary_sensor.pooltak",
            CONF_PRESENCE: ["person.sebastian"],
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return hass.data[DOMAIN][entry.entry_id], kall


def _id(hass, domain, key):
    for state in hass.states.async_all(domain):
        if state.entity_id.endswith(key):
            return state.entity_id
    raise AssertionError(f"fant ikke {domain}.*{key}")


async def test_nye_entiteter_finnes(hass, oppsett):
    for domain, key in [
        ("sensor", "nattsenking"),
        ("sensor", "maltemperatur"),
        ("sensor", "varmetap"),
        ("sensor", "solinnstraling"),
        ("sensor", "siste_klortablett"),
        ("sensor", "neste_klortablett"),
        ("binary_sensor", "nattsenking_aktiv"),
        ("binary_sensor", "klortablett_bor_legges_i"),
        ("binary_sensor", "noen_hjemme"),
        ("switch", "smart_nattsenking"),
        ("switch", "pooltak_pa"),
        ("number", "onsket_temperatur"),
        ("select", "nattsenking_skal_spare"),
        ("button", "logg_klortablett"),
    ]:
        _id(hass, domain, key)


async def test_vaermeldingen_hentes(hass, oppsett):
    k, kall = oppsett
    assert kall["vaer"]
    assert len(k._forecast) == 24


async def test_klortablett_logges_og_kan_angres(hass, oppsett):
    k, kall = oppsett
    forfall = _id(hass, "binary_sensor", "klortablett_bor_legges_i")
    assert hass.states.get(forfall).state == "on"

    await hass.services.async_call(
        DOMAIN, "logg_klortablett", {"antall": 2, "notat": "flottør"}, blocking=True
    )
    await hass.async_block_till_done()
    siste = hass.states.get(_id(hass, "sensor", "siste_klortablett"))
    assert siste.state not in ("unknown", "unavailable")
    assert siste.attributes["totalt"] == 2
    assert siste.attributes["historikk"][0]["notat"] == "flottør"
    assert hass.states.get(forfall).state == "off"
    assert any("klortablett" in c.data["message"] for c in kall["logg"])

    await hass.services.async_call(DOMAIN, "angre_klortablett", {}, blocking=True)
    await k.async_refresh()
    assert hass.states.get(_id(hass, "sensor", "siste_klortablett")).attributes["totalt"] == 0


async def test_settpunktet_folger_onsket_temperatur(hass, oppsett):
    k, kall = oppsett
    await hass.services.async_call(
        "number", "set_value",
        {"entity_id": _id(hass, "number", "onsket_temperatur"), "value": 28},
        blocking=True,
    )
    await k.async_refresh()
    assert kall["temp"][-1].data["temperature"] == 28


async def test_borte_senker_malet(hass, oppsett):
    k, kall = oppsett
    assert k.target_temp() == 27
    hass.states.async_set("person.sebastian", "not_home")
    await k.async_refresh()
    assert k.target_temp() == 25
    assert hass.states.get(_id(hass, "binary_sensor", "noen_hjemme")).state == "off"


async def test_pooltak_fra_entitet(hass, oppsett):
    k, _ = oppsett
    k.entry.update_listeners.clear()  # ikke last inn på nytt midt i testen
    assert not k.covered()
    hass.states.async_set("binary_sensor.pooltak", "on")
    assert k.covered()
    hass.config_entries.async_update_entry(
        k.entry, options={CONF_COVER: "cover.pooltak"}
    )
    hass.states.async_set("cover.pooltak", "closed")
    assert k.covered(), "lukket cover betyr at bassenget er dekket"
    hass.states.async_set("cover.pooltak", "open")
    assert not k.covered()


async def test_nattsenking_slar_av_og_pa(hass, oppsett):
    k, kall = oppsett
    naa = dt_util.now()
    k._setback = termisk.SetbackDecision(
        True, naa - timedelta(minutes=5), naa + timedelta(hours=2),
        saving_kwh=1.2, saving_cost=0.8,
    )
    await k._guard_setback(naa)
    assert k._setback_on
    assert kall["hvac"][-1].data == {"entity_id": CLIMATE, "hvac_mode": "off"}
    # Mens senkingen står, skal ikke varmen kreve sirkulasjon
    assert not k._heat_allowed(naa)

    hass.states.async_set(CLIMATE, "off", {"temperature": 27})
    k._setback = termisk.SetbackDecision(False, reason="Over")
    await k._guard_setback(naa)
    assert not k._setback_on
    assert k._hp_resume, "sperren skal sette varmepumpa på når pumpa går"
    assert k._heat_allowed(naa)


async def test_ingen_ny_senking_rett_etter_avbrudd(hass, oppsett):
    k, kall = oppsett
    naa = dt_util.now()
    k._setback_ended = naa - timedelta(minutes=5)
    k._setback = termisk.SetbackDecision(True, naa, naa + timedelta(hours=1))
    await k._guard_setback(naa)
    assert not k._setback_on


async def test_nattsenking_beregnes(hass, oppsett):
    k, _ = oppsett
    state = hass.states.get(_id(hass, "sensor", "nattsenking"))
    assert state.state in ("aktiv", "planlagt", "lonner_seg_ikke")
    assert state.attributes["begrunnelse"]


async def test_bryter_som_tilstedevaerelse(hass, oppsett):
    """En vanlig bryter kan brukes som tilstedeværelse: «på» betyr hjemme."""
    k, _ = oppsett
    k.entry.update_listeners.clear()
    hass.config_entries.async_update_entry(
        k.entry, options={CONF_PRESENCE: ["switch.gjester"]}
    )
    hass.states.async_set("switch.gjester", "on")
    assert k.present()
    hass.states.async_set("switch.gjester", "off")
    assert not k.present()


async def test_pooltak_uten_entitet_styres_av_bryteren(hass, oppsett):
    k, _ = oppsett
    k.entry.update_listeners.clear()
    data = {key: v for key, v in k.entry.data.items() if key != CONF_COVER}
    hass.config_entries.async_update_entry(k.entry, data=data)
    bryter = _id(hass, "switch", "pooltak_pa")
    await hass.services.async_call("switch", "turn_on", {"entity_id": bryter}, blocking=True)
    assert k.settings["cover_on"] is True
    assert k.covered()
    await hass.services.async_call("switch", "turn_off", {"entity_id": bryter}, blocking=True)
    assert not k.covered()


async def test_navn_i_klorloggen_og_hvem(hass, oppsett):
    """Navnene settes i tekstfeltet; loggen husker hvem som la i."""
    k, kall = oppsett
    felt = _id(hass, "text", "navn_i_klorloggen")
    await hass.services.async_call(
        "text", "set_value", {"entity_id": felt, "value": " Sebastian, ida ,Ida;Ola"},
        blocking=True,
    )
    assert k.chlorine_names == ["Sebastian", "ida", "Ola"]
    await hass.services.async_call(
        DOMAIN, "logg_klortablett", {"hvem": "Sebastian"}, blocking=True
    )
    await k.async_refresh()
    siste = hass.states.get(_id(hass, "sensor", "siste_klortablett")).attributes
    assert siste["historikk"][0]["hvem"] == "Sebastian"
    assert siste["logg"][-1]["hvem"] == "Sebastian"
    assert siste["navn"] == ["Sebastian", "ida", "Ola"]
    assert siste["per_person"] == {"Sebastian": 1}
    assert any("av Sebastian" in c.data["message"] for c in kall["logg"])


def test_split_names():
    from custom_components.ki_basseng.coordinator import split_names

    assert split_names("") == []
    assert split_names("A, b ,a;;C") == ["A", "b", "C"]
