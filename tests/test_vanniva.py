"""Vannivå (1.8): vannsensor i bassenget, varsel og automatisk påfylling."""
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.ki_basseng.const import (
    CONF_LEVEL_SENSOR,
    CONF_NOTIFY,
    CONF_PUMP_SWITCH,
    CONF_VALVE,
    DOMAIN,
)

SENSOR = "binary_sensor.bassengvann"
KRAN = "switch.hovedkran"


async def _oppsett(hass: HomeAssistant, med_sensor: bool = True):
    hass.states.async_set("switch.bassengpumpe", "off")
    hass.states.async_set(KRAN, "off")
    hass.states.async_set(SENSOR, "on")
    kall = {
        "pa": async_mock_service(hass, "homeassistant", "turn_on"),
        "av": async_mock_service(hass, "homeassistant", "turn_off"),
        "sw_av": async_mock_service(hass, "switch", "turn_off"),
        "sw_pa": async_mock_service(hass, "switch", "turn_on"),
        "mobil": async_mock_service(hass, "notify", "mobil"),
        "varsel": async_mock_service(hass, "persistent_notification", "create"),
        "bort": async_mock_service(hass, "persistent_notification", "dismiss"),
    }
    data = {CONF_PUMP_SWITCH: "switch.bassengpumpe", CONF_VALVE: KRAN}
    if med_sensor:
        data.update({CONF_LEVEL_SENSOR: SENSOR, CONF_NOTIFY: "notify.mobil"})
    entry = MockConfigEntry(domain=DOMAIN, title="KI Basseng", data=data)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return hass.data[DOMAIN][entry.entry_id], kall


def _finnes(hass, domain, hale):
    return any(s.entity_id.endswith(hale) for s in hass.states.async_all(domain))


async def test_ingen_entiteter_uten_sensor(hass):
    await _oppsett(hass, med_sensor=False)
    assert not _finnes(hass, "sensor", "vanniva")
    assert not _finnes(hass, "button", "fyll_bassenget")


async def test_entitetene_finnes_med_sensor(hass):
    k, _ = await _oppsett(hass)
    for domain, hale in [("sensor", "vanniva"), ("binary_sensor", "bassenget_trenger_vann"),
                         ("switch", "automatisk_pafylling"), ("number", "torr_for_varsel"),
                         ("number", "maks_pafylling"), ("button", "fyll_bassenget"),
                         ("button", "stopp_pafylling")]:
        assert _finnes(hass, domain, hale), (domain, hale)
    assert k.level_state() == "ok"


async def test_torr_en_stund_varsler_en_gang(hass):
    k, kall = await _oppsett(hass)
    hass.states.async_set(SENSOR, "off")
    await k.async_refresh()
    assert k.level_state() == "torr", "nettopp tørr: venter før varsel"
    assert not kall["mobil"]

    k.settings["level_dry_minutes"] = 0
    await k.async_refresh()
    await k.async_refresh()
    assert k.level_state() == "lav"
    assert len(kall["mobil"]) == 1, "varsler bare én gang"
    assert kall["varsel"]
    assert not kall["pa"], "ingen påfylling uten automatikk"


async def test_automatisk_pafylling_stopper_nar_sensoren_blir_vat(hass):
    k, kall = await _oppsett(hass)
    k.settings.update(level_dry_minutes=0, auto_fill=True)
    hass.states.async_set(SENSOR, "off")
    await k.async_refresh()
    assert k.level_state() == "fyller"
    assert kall["pa"][-1].data["entity_id"] == KRAN

    hass.states.async_set(SENSOR, "on")
    await k.async_refresh()
    assert k.level_state() == "ok"
    assert kall["av"][-1].data["entity_id"] == KRAN
    assert k.counters["fill_last_minutes"] >= 0


async def test_maks_pafylling_stopper_og_sperrer(hass):
    k, kall = await _oppsett(hass)
    k.settings.update(level_dry_minutes=0, auto_fill=True, fill_max_minutes=30)
    hass.states.async_set(SENSOR, "off")
    await k.async_refresh()
    k._fill_started = dt_util.now() - timedelta(minutes=31)
    await k.async_refresh()
    assert k.level_state() == "stoppet"
    assert kall["av"], "ventilen stenges"
    antall = len(kall["pa"])
    await k.async_refresh()
    assert len(kall["pa"]) == antall, "starter ikke igjen før sensoren har vært våt"
    assert any("stoppet" in c.data["title"].lower() for c in kall["mobil"])


async def test_sprederen_stenger_ikke_ventilen_midt_i_pafylling(hass):
    k, kall = await _oppsett(hass)
    await k.async_start_sprinkler(5)
    hass.states.async_set(SENSOR, "off")
    await k.async_start_fill()
    await k.async_stop_sprinkler("Ferdig")
    assert not [c for c in kall["sw_av"] if c.data.get("entity_id") == KRAN]
    assert k.level_state() == "fyller"


async def test_manuell_fylling_nekter_nar_fullt(hass):
    k, kall = await _oppsett(hass)
    await k.async_start_fill()
    assert not kall["pa"]
    assert "fullt" in k._level_reason
