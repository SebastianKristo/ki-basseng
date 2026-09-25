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
    # Utgangspunkt: ingen senking (den første oppdateringen kan ha planlagt en)
    k._setback_on = False
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


async def test_varmepumpetilstanden_overlever_omstart(hass, oppsett):
    """Slo integrasjonen av varmepumpa før en omstart, skal den huske det."""
    from custom_components.ki_basseng.coordinator import KiBassengCoordinator

    k, _ = oppsett
    k._hp_resume = True
    k._setback_on = True
    await k.async_persist()
    ny = KiBassengCoordinator(hass, k.entry)
    await ny.async_prepare()
    assert ny._hp_resume and ny._setback_on


async def test_forste_start_med_varmepumpa_av_gir_resume(hass, oppsett):
    from custom_components.ki_basseng.coordinator import KiBassengCoordinator

    k, _ = oppsett
    await k._store.async_save({"settings": k.settings})  # lagring uten hp-nøkkel
    hass.states.async_set(CLIMATE, "off", {"temperature": 27})
    ny = KiBassengCoordinator(hass, k.entry)
    await ny.async_prepare()
    assert ny._hp_resume


async def test_kaldt_vann_gir_oppvarming_ikke_vedlikehold(hass, oppsett):
    """Morgenen det gjaldt: 25 °C, varmepumpa av i påvente av sirkulasjon."""
    k, _ = oppsett
    naa = dt_util.now().replace(hour=7)
    k._setback_on = False
    k._hp_resume = True
    k._temp_est = 25.0
    hass.states.async_set(CLIMATE, "off", {"temperature": 27})
    modus, pa, _ = k._decide(naa)
    assert modus == "oppvarming" and pa is True


async def test_begrunnelse_nar_den_ikke_varmer(hass, oppsett):
    k, _ = oppsett
    naa = dt_util.now()
    k._temp_est = 25.0
    k._setback_on = False
    k.settings["heat_priority"] = False
    assert k.heat_block(naa) == "Varmeprioritet er av"
    k.settings["heat_priority"] = True
    hass.states.async_set(CLIMATE, "off", {"temperature": 27})
    k._hp_resume = False
    assert "utenfor integrasjonen" in k.heat_block(naa)
    k._temp_est = 27.0
    assert k.heat_block(naa) is None


async def test_vintermodus_frostsikring(hass, oppsett):
    k, kall = oppsett
    on = async_mock_service(hass, "homeassistant", "turn_on")
    off = async_mock_service(hass, "homeassistant", "turn_off")
    k.entry.update_listeners.clear()
    hass.config_entries.async_update_entry(k.entry, options={
        "heater_entities": ["switch.varmeovn"], "house_sensor": "sensor.bassenghus"})
    hass.states.async_set("switch.varmeovn", "off")
    hass.states.async_set("sensor.bassenghus", "3.0")
    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": _id(hass, "switch", "vintermodus")}, blocking=True)
    await k.async_refresh()
    await hass.async_block_till_done()
    assert any(c.data["entity_id"] == "switch.varmeovn" for c in on), "varmen skal på under 5 °C"
    assert any(c.data.get("hvac_mode") == "off" for c in kall["hvac"]), "varmepumpa av om vinteren"
    assert k.data["mode"] in ("vinter", "filtrering")

    hass.states.async_set("sensor.ute", "-3")
    modus, pa, _ = k._decide(dt_util.now())
    assert modus == "frostsikring" and pa

    hass.states.async_set("sensor.bassenghus", "7.5")
    await k.async_refresh()
    await hass.async_block_till_done()
    assert any(c.data["entity_id"] == "switch.varmeovn" for c in off), "av igjen over 7 °C"

    k.settings["winter_mode"] = False
    await k.async_refresh()
    assert k._hp_resume, "varmepumpa skal tilbake når vinteren er over"


async def test_pooltak_med_dorsensor(hass, oppsett):
    """En dør-/vindussensor er «på» når den er åpen – da er taket av."""
    k, _ = oppsett
    hass.states.async_set("binary_sensor.pooltak", "on", {"device_class": "door"})
    assert not k.covered()
    hass.states.async_set("binary_sensor.pooltak", "off", {"device_class": "door"})
    assert k.covered()


async def test_klor_etterregistrering_sletting_og_kalender(hass, oppsett):
    k, _ = oppsett
    k.settings["chlorine_names"] = "Sebastian, Ida"
    igaar = dt_util.now() - timedelta(days=1)
    await hass.services.async_call(DOMAIN, "logg_klortablett", {"hvem": "Ida"}, blocking=True)
    await hass.services.async_call(
        DOMAIN, "logg_klortablett",
        {"hvem": "Sebastian", "tidspunkt": igaar.isoformat()}, blocking=True)
    assert [r["hvem"] for r in k.chlorine] == ["Sebastian", "Ida"], "sortert etter tid"

    kal = _id(hass, "calendar", "klorlogg")
    svar = await hass.services.async_call(
        "calendar", "get_events",
        {"entity_id": kal, "start_date_time": (igaar - timedelta(hours=1)).isoformat(),
         "end_date_time": (dt_util.now() + timedelta(days=30)).isoformat()},
        blocking=True, return_response=True)
    titler = [e["summary"] for e in svar[kal]["events"]]
    assert "Klortablett · Sebastian" in titler and "Klortablett · Ida" in titler

    # Legg til fra kalenderen: tittelen er bare et navn
    await hass.services.async_call(
        "calendar", "create_event",
        {"entity_id": kal, "summary": "Ida", "start_date": (igaar - timedelta(days=3)).date().isoformat(),
         "end_date": (igaar - timedelta(days=2)).date().isoformat()},
        blocking=True)
    assert len(k.chlorine) == 3 and k.chlorine[0]["hvem"] == "Ida"

    await hass.services.async_call(
        DOMAIN, "slett_klortablett", {"tid": k.chlorine[1]["tid"]}, blocking=True)
    assert [r["hvem"] for r in k.chlorine] == ["Ida", "Ida"]


async def test_spart_i_dag_deles_i_mengde_og_timing(hass, oppsett):
    """Mengde + timing skal gå nøyaktig opp i den målte besparelsen."""
    k, _ = oppsett
    c = k.counters
    c.update(split_day=k._day, cost_reference=10.0, ref_kwh_today=12.0,
             pump_kwh_priced=3.0, pump_cost_today=1.5, hp_cost_today=4.0,
             setback_kwh_today=1.2, setback_cost_today=0.8)
    s = k._savings()
    assert s["measured"] == 8.5
    assert s["kwh_saved"] == 9.0
    assert round(s["amount_cost"] + s["timing_cost"], 2) == s["measured"]
    assert s["timing_cost"] == 1.0, "pumpa betalte 0,50 mot snittet 0,83"
    assert s["with_setback"] == 9.3
    assert s["without_ki"] == 14.8 and s["with_ki"] == 5.5


async def test_spart_regnes_fra_tellerne(hass, oppsett):
    """Pumpa går ett minutt og står ett minutt, med pris 2 kr: da er halve
    referansen spart, og ingenting av det skyldes billigere timer."""
    k, _ = oppsett
    k.entry.update_listeners.clear()
    hass.config_entries.async_update_entry(k.entry, options={"price_sensor": "sensor.pris"})
    hass.states.async_set("sensor.pris", "2.0")
    for key in ("cost_reference", "ref_kwh_today", "pump_kwh_priced", "pump_cost_today",
                "hp_cost_today", "pump_kwh_today", "hp_kwh_today", "cost_today"):
        k.counters[key] = 0.0
    k.counters["split_day"] = k._day
    naa = dt_util.now()
    k._pump_state = True
    k._last_tick = naa - timedelta(seconds=60)
    k._accumulate(naa)
    k._pump_state = False
    k._last_tick = naa
    k._accumulate(naa + timedelta(seconds=60))
    s = k._savings()
    assert abs(s["measured"] - 0.8 * 2 / 60) < 0.006, "tallene er avrundet til øre"
    assert abs(s["timing_cost"]) < 0.006
    assert abs(k.counters["cost_reference"] - k.counters["pump_cost_today"] - 0.8 * 2 / 60) < 1e-9


async def test_dognskiftet_legger_besparelsen_til_maaned_og_total(hass, oppsett):
    k, _ = oppsett
    igaar = (dt_util.now() - timedelta(days=1)).date().isoformat()
    k._day = igaar
    k.counters.update(split_day=igaar, cost_reference=5.0, pump_cost_today=0.0,
                      saved_total=10.0, saved_month=3.0, saved_month_key=igaar[:7])
    k._roll_day(dt_util.now())
    assert k.counters["saved_yesterday"] == 5.0
    assert k.counters["saved_total"] == 15.0
    samme_maaned = igaar[:7] == dt_util.now().date().isoformat()[:7]
    assert k.counters["saved_month"] == (8.0 if samme_maaned else 0.0)
    assert k.counters["cost_reference"] == 0.0 and k.counters["split_day"] == k._day


async def test_nattsenking_og_pooltak_anslas(hass, oppsett):
    k, _ = oppsett
    naa = dt_util.now()
    k._setback_on = False
    k._setback_ended = None
    k.counters["setback_kwh_today"] = 0.0
    k.counters["setback_cost_today"] = 0.0
    k._setback = termisk.SetbackDecision(True, naa - timedelta(minutes=1), naa + timedelta(hours=3),
                                         saving_kwh=1.2, saving_cost=0.8)
    await k._guard_setback(naa)
    assert k.counters["setback_kwh_today"] == 1.2 and k.counters["setback_cost_today"] == 0.8

    k.counters["cover_kwh_today"] = 0.0
    k._count_cover(True, 27.0, 14.0, 0.0, {"dt_s": 3600, "price": 1.0, "pump_w": 0, "hp_w": 0})
    assert k.counters["cover_kwh_today"] > 0.5, "taket hindrer varmetap om natta"
    k._count_cover(False, 27.0, 14.0, 0.0, {"dt_s": 3600, "price": 1.0, "pump_w": 0, "hp_w": 0})
    assert k.counters["cover_cost_today"] == k.counters["cover_kwh_today"], "ingenting når taket er av"


async def test_tid_og_kostnad_til_malet(hass, oppsett):
    """Måltemperaturen forteller hvor lenge og hva det koster å nå målet."""
    k, _ = oppsett
    await hass.services.async_call(
        "number", "set_value",
        {"entity_id": _id(hass, "number", "onsket_temperatur"), "value": 28},
        blocking=True,
    )
    await k.async_refresh()
    a = hass.states.get(_id(hass, "sensor", "maltemperatur")).attributes
    assert a["rekker_malet"] is True
    assert a["minutter_til_mal"] > 0
    assert a["oppvarming_kwh"] > 0
    assert a["klar_kl"] is not None and ":" in a["klar_kl"]

    # I vintermodus er det ikke noe mål å nå
    k.settings["winter_mode"] = True
    await k.async_refresh()
    a = hass.states.get(_id(hass, "sensor", "maltemperatur")).attributes
    assert "minutter_til_mal" not in a


async def test_klorloggen_viser_hvor_den_speiles(hass, oppsett):
    k, _ = oppsett
    assert k._chlorine_info(dt_util.now())["mirror"] is None
    k.entry.update_listeners.clear()
    hass.config_entries.async_update_entry(k.entry, options={"calendar_entity": "calendar.google"})
    assert k._chlorine_info(dt_util.now())["mirror"] == "calendar.google"
    # Sin egen kalender speiles den ikke til
    egen = _id(hass, "calendar", "klorlogg")
    hass.config_entries.async_update_entry(k.entry, options={"calendar_entity": egen})
    assert k._chlorine_info(dt_util.now())["mirror"] is None
