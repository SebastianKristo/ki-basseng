"""Varmemodellen: sol, varmetap og om nattsenking lønner seg."""
from datetime import datetime, timedelta, timezone

import pytest

from custom_components.ki_basseng import termisk as t

STROMSTAD = (58.94, 11.17)
CEST = timezone(timedelta(hours=2))
KVELD = datetime(2026, 7, 10, 22, 0, tzinfo=CEST)


def _basseng(**kw):
    verdier = dict(
        volume=40.95, area=24.1, u_open=15, u_covered=5, cover_solar=0.6,
        hp_nominal_w=1470, pump_w=800,
    )
    verdier.update(kw)
    return t.Pool(**verdier)


def _timer(luft, priser=None, sky=0.2, filter_timer=()):
    priser = priser or [1.0] * len(luft)
    ut = []
    for i, (a, p) in enumerate(zip(luft, priser, strict=True)):
        start = KVELD + timedelta(hours=i)
        sol = t.irradiance(t.sun_elevation(start + timedelta(minutes=30), *STROMSTAD), sky)
        ut.append(t.Hour(start, a, sol, p, i in filter_timer))
    return ut


# -- sol --------------------------------------------------------------------
def test_solhoyde_midtsommer_i_stromstad():
    middag = datetime(2026, 6, 21, 13, 15, tzinfo=CEST)
    assert t.sun_elevation(middag, *STROMSTAD) == pytest.approx(54.5, abs=1)
    midnatt = datetime(2026, 6, 21, 1, 15, tzinfo=CEST)
    assert t.sun_elevation(midnatt, *STROMSTAD) < 0


def test_ingen_sol_om_natten_og_mindre_med_skyer():
    assert t.irradiance(-5, 0) == 0
    assert t.irradiance(50, 0) > 700
    assert t.irradiance(50, 1.0) < t.irradiance(50, 0) * 0.3


# -- varmetap ----------------------------------------------------------------
def test_tak_kutter_varmetapet():
    b = _basseng()
    assert b.loss_w(27, 15, covered=True) < b.loss_w(27, 15, covered=False) / 2


def test_kaldere_luft_gir_lavere_cop():
    b = _basseng()
    assert b.cop(5, 27) < b.cop(15, 27) < b.cop(25, 27)


def test_solfanger_gir_bare_varme_mens_pumpen_gar():
    b = _basseng(collector_area=10)
    assert b.solar_w(600, False, True) > b.solar_w(600, False, False)


def test_termostaten_holder_temperaturen():
    b = _basseng()
    res = t.simulate(b, _timer([14] * 8), 27, 27, covered=False)
    assert res.temp_end == pytest.approx(27, abs=0.05)
    assert res.kwh > 0


def test_av_hele_natten_kjoler_vannet():
    b = _basseng()
    res = t.simulate(b, _timer([14] * 8), 27, 27, False, off=set(range(8)))
    assert res.temp_end < 26.5
    # Sluttavregningen tar med strømmen det koster å hente inn igjen
    assert res.kwh > 0


# -- nattsenking -------------------------------------------------------------
def test_jevn_natt_og_jevn_pris_lonner_seg_ikke():
    """Å skru av og varme opp igjen sparer bare det lille ekstra tapet —
    og koster mer fordi gjenoppvarmingen skjer i morgenkulda."""
    b = _basseng()
    d = t.optimise_setback(b, _timer([16, 15, 14, 13, 12, 12, 13, 15]), 27, 27,
                           False, set(range(7)), 8, 3)
    assert not d.worth_it
    assert d.reason


def test_kald_natt_og_varm_formiddag_lonner_seg():
    """Varmepumpen gjør mer nytte når lufta er varm: la natten gå og ta igjen
    varmen i sola på formiddagen."""
    b = _basseng()
    luft = [14, 12, 11, 10, 9, 9, 10, 13, 16, 19, 21, 22]
    d = t.optimise_setback(b, _timer(luft), 27, 27, False, set(range(8)), 12, 3)
    assert d.worth_it
    assert d.saving_kwh > 1
    assert d.start == KVELD
    assert d.best.temp_end >= 26.85


def test_dyr_kveld_billig_natt_flytter_varmen():
    b = _basseng()
    luft = [16, 15, 14, 13, 12, 12, 13, 15]
    priser = [1.5, 1.5, 1.5, 1.5, 0.4, 0.4, 0.4, 0.4]
    d = t.optimise_setback(b, _timer(luft, priser), 27, 27, False, set(range(7)), 8, 3,
                           t.CRITERION_COST)
    assert d.worth_it
    assert d.saving_cost > 1
    # Vinduet ligger i de dyre timene
    assert d.start.hour in (22, 23)


def test_begge_krever_at_strombruken_ikke_oker():
    """Standardkriteriet: spar penger, men aldri ved å bruke mer strøm."""
    b = _basseng()
    luft = [16, 15, 14, 13, 12, 12, 13, 15]
    priser = [1.5, 1.5, 1.5, 1.5, 0.4, 0.4, 0.4, 0.4]
    d = t.optimise_setback(b, _timer(luft, priser), 27, 27, False, set(range(7)), 8, 3,
                           t.CRITERION_BOTH)
    assert d.worth_it
    assert d.saving_kwh >= 0


def test_rekker_ikke_a_varme_opp_igjen():
    """En liten varmepumpe og badeklar om fire timer: tre timer av rekker ikke å
    tas igjen på den siste, så det vinduet forkastes."""
    b = _basseng(hp_nominal_w=800)
    luft = [18, 18, 18, 18]
    d = t.optimise_setback(b, _timer(luft), 27, 27, False, {0, 1, 2}, 4, 3,
                           t.CRITERION_ENERGY)
    lang = [a for a in d.evaluated if a["fra"] == "22:00" and a["til"] == "01:00"]
    assert lang and not lang[0]["klar"]
    assert not (d.worth_it and d.end.hour == 1)


def test_maks_senking_respekteres():
    b = _basseng()
    luft = [5, 4, 3, 2, 2, 2, 3, 12, 18, 22, 24, 25]
    d = t.optimise_setback(b, _timer(luft), 27, 27, False, set(range(8)), 12, 0.3,
                           t.CRITERION_ENERGY)
    fri = t.optimise_setback(b, _timer(luft), 27, 27, False, set(range(8)), 12, 3,
                             t.CRITERION_ENERGY)
    assert fri.worth_it and fri.best.temp_min < 27 - 0.3
    assert not d.worth_it or d.best.temp_min >= 27 - 0.3


def test_med_tak_er_det_mindre_a_spare():
    luft = [14, 12, 11, 10, 9, 9, 10, 13, 16, 19, 21, 22]
    apen = t.optimise_setback(_basseng(), _timer(luft), 27, 27, False, set(range(8)), 12, 3)
    tak = t.optimise_setback(_basseng(), _timer(luft), 27, 27, True, set(range(8)), 12, 3)
    assert tak.baseline.kwh < apen.baseline.kwh
    assert tak.saving_kwh <= apen.saving_kwh


def test_aktiv_bare_innenfor_vinduet():
    d = t.SetbackDecision(True, KVELD, KVELD + timedelta(hours=3))
    assert d.active(KVELD + timedelta(hours=1))
    assert not d.active(KVELD + timedelta(hours=3))
    assert not t.SetbackDecision(False).active(KVELD)


def test_ingen_natt_ingen_senking():
    d = t.optimise_setback(_basseng(), _timer([14] * 4), 27, 27, False, set(), 4, 3)
    assert not d.worth_it


# -- læring og klor -----------------------------------------------------------
def test_ema_klemmes():
    assert t.ema(1.0, 10, 0.5, 0.5, 1.6) == 1.6
    assert t.ema(1.0, 0.9, 0.5, 0.5, 1.6) == pytest.approx(0.95)


def test_klorintervall_kortere_i_varmt_vann():
    assert t.chlorine_interval_days(7, 20) == 7
    assert t.chlorine_interval_days(7, None) == 7
    assert t.chlorine_interval_days(7, 32) == pytest.approx(3.5)
