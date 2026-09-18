"""Varmepumpa hopper selv i «auto». Da skal den tilbake til «heat»."""
import asyncio
from types import SimpleNamespace

from custom_components.ki_basseng.const import CONF_CLIMATE, DEFAULT_SETTINGS
from custom_components.ki_basseng.coordinator import KiBassengCoordinator as K


def _koord(tilstand, innstillinger=None, hp_resume=False):
    k = object.__new__(K)
    kall = []

    async def _call(dom, tj, data, blocking=False):
        kall.append((dom, tj, data.get("hvac_mode") or data.get("message"), data.get("entity_id")))

    k.hass = SimpleNamespace(
        states=SimpleNamespace(get=lambda e: (
            SimpleNamespace(state=tilstand, attributes={"temperature": 27})
            if e == "climate.basseng" and tilstand is not None else None)),
        services=SimpleNamespace(async_call=_call))
    k.cfg = lambda n: "climate.basseng" if n == CONF_CLIMATE else None
    k.settings = {**DEFAULT_SETTINGS, **(innstillinger or {})}
    k._hp_resume = hp_resume
    k.kall = kall
    return k


def _kjor(k):
    asyncio.get_event_loop().run_until_complete(K._guard_auto_mode(k, None))
    return [x for x in k.kall if x[1] == "set_hvac_mode"]


def test_auto_settes_til_heat():
    k = _koord("auto")
    assert _kjor(k) == [("climate", "set_hvac_mode", "heat", "climate.basseng")]


def test_heat_rores_ikke():
    """Står den der vi vil, skal vi ikke sende noe. Et kall i minuttet til en
    varmepumpe som alt er i heat er bare støy på bussen."""
    assert _kjor(_koord("heat")) == []


def test_off_rores_ikke():
    """«off» er noe integrasjonen selv setter når sirkulasjonen er av."""
    assert _kjor(_koord("off")) == []


def test_cool_og_dry_rores_ikke():
    """Har du satt den til kjøling med vilje, skal ikke vakthunden overstyre deg.
    Bare «auto» er tilstanden pumpa havner i av seg selv."""
    for m in ("cool", "dry", "fan_only", "heat_cool"):
        assert _kjor(_koord(m)) == [], m


def test_ikke_mens_sperren_har_slatt_av():
    """Sperren slår av pumpa når sirkulasjonen mangler og setter `_hp_resume`.
    Tvinger vakthunden den på igjen samtidig, slåss de to reglene."""
    assert _kjor(_koord("auto", hp_resume=True)) == []


def test_kan_slas_av():
    assert _kjor(_koord("auto", {"force_heat": False})) == []


def test_uten_climate_entitet():
    k = _koord("auto")
    k.cfg = lambda n: None
    assert _kjor(k) == []


def test_utilgjengelig_pumpe():
    assert _kjor(_koord(None)) == []


def test_skriver_i_loggboka():
    k = _koord("auto")
    asyncio.get_event_loop().run_until_complete(K._guard_auto_mode(k, None))
    logg = [x for x in k.kall if x[1] == "log"]
    assert logg and "auto" in logg[0][2]


def test_teller_hvor_ofte_det_skjer():
    """Skjer det ofte, er det verdt å vite — teller med i loggmeldingen."""
    k = _koord("auto")
    for _ in range(3):
        asyncio.get_event_loop().run_until_complete(K._guard_auto_mode(k, None))
    assert k._auto_rettet == 3
