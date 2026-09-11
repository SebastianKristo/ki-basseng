/*!
 * ki-basseng-card 1.0.0
 * Kort for integrasjonen ki_basseng: sirkulasjon, varme og spreder.
 * Ingen byggesteg – legg fila i /config/www og legg den til som modul.
 */

const KIB_VERSION = "1.0.0";

const LitBase =
  customElements.get("ha-panel-lovelace") ||
  customElements.get("hui-view") ||
  customElements.get("hui-masonry-view");
const LitElement = LitBase
  ? Object.getPrototypeOf(LitBase)
  : Object.getPrototypeOf(customElements.get("home-assistant-main"));
const html = LitElement.prototype.html;
const css = LitElement.prototype.css;

/* ------------------------------------------------------------------ */
/* Entitetsoppslag                                                     */
/* ------------------------------------------------------------------ */

// Forventet halen på entity_id, med alternativer hvis navn er endret.
const KEYS = {
  modus: ["sensor", ["pumpemodus"]],
  omsetninger: ["sensor", ["omsetninger_i_dag"]],
  volum: ["sensor", ["pumpet_volum_i_dag"]],
  volumTotalt: ["sensor", ["pumpet_volum_totalt"]],
  pumpetid: ["sensor", ["pumpetid_i_dag"]],
  nesteStart: ["sensor", ["neste_pumpestart"]],
  pumpeEffekt: ["sensor", ["pumpe_effekt"]],
  vpEffekt: ["sensor", ["varmepumpe_effekt"]],
  pumpeEnergi: ["sensor", ["pumpe_energi_i_dag"]],
  vpEnergi: ["sensor", ["varmepumpe_energi_i_dag"]],
  kostnad: ["sensor", ["kostnad_i_dag"]],
  spart: ["sensor", ["spart_i_dag"]],
  vanntemp: ["sensor", ["vanntemperatur"]],
  spredertid: ["sensor", ["spreder_gjenstar"]],

  skalGa: ["binary_sensor", ["pumpe_skal_ga"]],
  spreder: ["binary_sensor", ["spreder_kjorer"]],
  overstyrt: ["binary_sensor", ["manuell_overstyring"]],
  vpVenter: ["binary_sensor", ["varmepumpe_venter"]],

  auto: ["switch", ["automatikk"]],
  pris: ["switch", ["prisstyring"]],
  varme: ["switch", ["varmeprioritet"]],
  styrVp: ["switch", ["styr_varmepumpe"]],
  pulsVarme: ["switch", ["puls_med_varme"]],
  spredprogram: ["switch", ["spreder_program"]],
  frostvakt: ["switch", ["frostvakt"]],

  mal: ["number", ["omsetninger_per_dogn", "omsetninger_mal"]],
  puls: ["number", ["vedlikeholdspuls"]],
  minTid: ["number", ["minste_kjoretid"]],
  overstyringTid: ["number", ["manuell_overstyring_varer", "overstyring_varighet"]],
  dagtimer: ["number", ["dagtimer_i_planen", "dagtimer"]],
  varmeStart: ["number", ["varmevindu_start"]],
  varmeSlutt: ["number", ["varmevindu_slutt"]],
  basislast: ["number", ["pumpe_basislast"]],
  spredVarighet: ["number", ["spreder_varighet"]],
  spredIntervall: ["number", ["spreder_intervall"]],
  spredMaks: ["number", ["spreder_maks_per_dogn", "spreder_maks"]],

  profil: ["select", ["driftsprofil"]],
  startSpreder: ["button", ["start_spreder"]],
  stoppSpreder: ["button", ["stopp_spreder"]],
  boost: ["button", ["boost_sirkulasjon"]],
  nullstill: ["button", ["nullstill_dagens_tellere", "nullstill_i_dag"]],
};

const MODUS_TEKST = {
  filtrering: "Filtrerer",
  oppvarming: "Varmer opp",
  vedlikehold: "Vedlikehold",
  hvile: "Hviler",
  manuell: "Manuell",
  boost: "Boost",
  spreder: "Spreder",
};

const MODUS_FARGE = {
  filtrering: "var(--kib-blue)",
  oppvarming: "var(--kib-orange)",
  vedlikehold: "var(--kib-accent)",
  boost: "var(--kib-accent)",
  spreder: "var(--kib-blue)",
  hvile: "var(--kib-muted)",
  manuell: "var(--kib-red)",
};

const PROFIL_TEKST = {
  eco: "Eco",
  balansert: "Balansert",
  badeklar: "Badeklar",
  ferie: "Ferie",
  egendefinert: "Egen",
};

const nf = (v, d = 1) =>
  v === null || v === undefined || isNaN(v)
    ? "–"
    : Number(v).toFixed(d).replace(".", ",");

/* ------------------------------------------------------------------ */
/* Kortet                                                              */
/* ------------------------------------------------------------------ */

class KiBassengCard extends LitElement {
  static get properties() {
    return { hass: {}, _config: {}, _fane: { state: true } };
  }

  constructor() {
    super();
    this._fane = null;
  }

  static getStubConfig() {
    return { type: "custom:ki-basseng-card", prefix: "ki_basseng" };
  }

  static getConfigElement() {
    return document.createElement("ki-basseng-card-editor");
  }

  setConfig(config) {
    this._config = {
      tittel: "Badebasseng",
      faner: ["oversikt", "sirkulasjon", "spreder", "innstillinger"],
      ...config,
    };
    this._fane = this._config.fane || this._config.faner[0];
  }

  getCardSize() {
    return 8;
  }

  /* --- oppslag ---------------------------------------------------- */

  get prefix() {
    if (this._config.prefix) return this._config.prefix;
    if (this._funnetPrefix) return this._funnetPrefix;
    if (!this.hass) return "ki_basseng";
    const treff = Object.keys(this.hass.states).find(
      (id) =>
        id.startsWith("sensor.") &&
        id.endsWith("_pumpemodus") &&
        this.hass.states[id].attributes.omsetningstid !== undefined
    );
    this._funnetPrefix = treff
      ? treff.slice("sensor.".length, -"_pumpemodus".length)
      : "ki_basseng";
    return this._funnetPrefix;
  }

  id(key) {
    const spec = KEYS[key];
    if (!spec || !this.hass) return null;
    const [domain, haler] = spec;
    for (const hale of haler) {
      const id = `${domain}.${this.prefix}_${hale}`;
      if (this.hass.states[id]) return id;
    }
    return `${domain}.${this.prefix}_${haler[0]}`;
  }

  st(key) {
    const id = this.id(key);
    return id ? this.hass.states[id] : undefined;
  }

  val(key, fallback = null) {
    const s = this.st(key);
    if (!s || ["unknown", "unavailable", ""].includes(s.state)) return fallback;
    const n = Number(s.state);
    return isNaN(n) ? s.state : n;
  }

  attr(key, navn) {
    const s = this.st(key);
    return s ? s.attributes[navn] : undefined;
  }

  on(key) {
    const s = this.st(key);
    return !!s && s.state === "on";
  }

  enhet(key) {
    const s = this.st(key);
    return (s && s.attributes.unit_of_measurement) || "";
  }

  /* --- handlinger -------------------------------------------------- */

  _trykk(key) {
    const id = this.id(key);
    if (!id) return;
    this.hass.callService("button", "press", { entity_id: id });
    this._puls();
  }

  _veksle(key) {
    const id = this.id(key);
    if (!id) return;
    this.hass.callService("switch", "toggle", { entity_id: id });
  }

  _sett(key, verdi) {
    const id = this.id(key);
    if (!id) return;
    this.hass.callService("number", "set_value", { entity_id: id, value: verdi });
  }

  _velg(verdi) {
    const id = this.id("profil");
    if (!id) return;
    this.hass.callService("select", "select_option", {
      entity_id: id,
      option: verdi,
    });
  }

  _mer(key) {
    const id = this.id(key);
    if (!id) return;
    const ev = new Event("hass-more-info", { bubbles: true, composed: true });
    ev.detail = { entityId: id };
    this.dispatchEvent(ev);
  }

  _puls() {
    if (navigator.vibrate) navigator.vibrate(8);
  }

  /* --- delvisninger ------------------------------------------------ */

  _ring() {
    const gjort = this.val("omsetninger", 0) || 0;
    const mal = Number(this.attr("omsetninger", "mal") || this.val("mal", 1.5)) || 1.5;
    const andel = Math.max(0, Math.min(1, gjort / mal));
    const r = 46;
    const omkrets = 2 * Math.PI * r;
    const modus = this.val("modus", "hvile");
    const farge = MODUS_FARGE[modus] || "var(--kib-accent)";

    return html`
      <svg class="ring" viewBox="0 0 120 120" @click=${() => this._mer("omsetninger")}>
        <circle class="spor" cx="60" cy="60" r="${r}" />
        <circle
          class="fylt"
          cx="60"
          cy="60"
          r="${r}"
          style="stroke:${farge};stroke-dasharray:${omkrets};stroke-dashoffset:${omkrets *
          (1 - andel)}"
        />
        <text x="60" y="56" class="ring-tall">${nf(gjort, 2)}×</text>
        <text x="60" y="76" class="ring-under">av ${nf(mal, 2)}</text>
      </svg>
    `;
  }

  _tidslinje() {
    const plan = this.attr("modus", "plan_i_dag") || [];
    const na = new Date();
    const naPst = ((na.getHours() * 60 + na.getMinutes()) / 1440) * 100;
    const gar = this.attr("modus", "pumpe_gar");
    const timer = [];
    for (let t = 0; t < 24; t++) {
      const planlagt = plan.includes(t);
      const naTime = t === na.getHours();
      timer.push(html`
        <div
          class="time ${planlagt ? "planlagt" : ""} ${naTime ? "na" : ""}"
          title="${String(t).padStart(2, "0")}:00"
        ></div>
      `);
    }
    return html`
      <div class="tidslinje">
        <div class="spor-24">
          ${timer}
          <div class="naalinje ${gar ? "gar" : ""}" style="left:${naPst}%"></div>
        </div>
        <div class="klokkeslett">
          <span>00</span><span>06</span><span>12</span><span>18</span><span>24</span>
        </div>
      </div>
    `;
  }

  _rute(ikon, tall, tekst, key) {
    return html`
      <div class="rute" @click=${() => key && this._mer(key)}>
        <ha-icon icon="${ikon}"></ha-icon>
        <div class="rute-tall">${tall}</div>
        <div class="rute-tekst">${tekst}</div>
      </div>
    `;
  }

  _bryter(key, tekst, ikon) {
    const på = this.on(key);
    if (!this.st(key)) return html``;
    return html`
      <button class="pille ${på ? "aktiv" : ""}" @click=${() => this._veksle(key)}>
        <ha-icon icon="${ikon}"></ha-icon><span>${tekst}</span>
      </button>
    `;
  }

  _stepper(key, tekst, steg, desimaler = 2, suffiks = "") {
    const s = this.st(key);
    if (!s) return html``;
    const v = Number(s.state);
    const min = Number(s.attributes.min ?? 0);
    const maks = Number(s.attributes.max ?? 100);
    return html`
      <div class="stepper">
        <div class="stepper-tekst">${tekst}</div>
        <div class="stepper-styring">
          <button
            @click=${() => this._sett(key, Math.max(min, +(v - steg).toFixed(4)))}
            aria-label="Mindre"
          >
            <ha-icon icon="mdi:minus"></ha-icon>
          </button>
          <div class="stepper-verdi">${nf(v, desimaler)}${suffiks}</div>
          <button
            @click=${() => this._sett(key, Math.min(maks, +(v + steg).toFixed(4)))}
            aria-label="Mer"
          >
            <ha-icon icon="mdi:plus"></ha-icon>
          </button>
        </div>
      </div>
    `;
  }

  /* --- faner -------------------------------------------------------- */

  _oversikt() {
    const modus = this.val("modus", "hvile");
    const temp = this.val("vanntemp");
    const effekt = (this.val("pumpeEffekt", 0) || 0) + (this.val("vpEffekt", 0) || 0);
    const neste = this.val("nesteStart");
    const valuta = this.enhet("kostnad") || "";
    let nesteTekst = "–";
    if (neste && typeof neste === "string") {
      const d = new Date(neste);
      if (!isNaN(d)) {
        nesteTekst = d.toLocaleTimeString("nb-NO", {
          hour: "2-digit",
          minute: "2-digit",
        });
      }
    } else if (["filtrering", "oppvarming", "boost"].includes(modus)) {
      nesteTekst = "pågår";
    }

    return html`
      <div class="hero">
        ${this._ring()}
        <div class="hero-tekst">
          <div class="temp" @click=${() => this._mer("vanntemp")}>
            ${nf(temp, 1)}<span>°C</span>
          </div>
          <div
            class="merke"
            style="background:${MODUS_FARGE[modus] || "var(--kib-muted)"}"
          >
            <ha-icon icon="${this.on("skalGa") ? "mdi:pump" : "mdi:pump-off"}"></ha-icon>
            ${MODUS_TEKST[modus] || modus}
          </div>
          <div class="begrunnelse">${this.attr("modus", "begrunnelse") || ""}</div>
        </div>
      </div>

      ${this._tidslinje()}

      <div class="ruter">
        ${this._rute(
          "mdi:timer-outline",
          `${nf(this.val("pumpetid", 0), 1)} t`,
          "Pumpetid i dag",
          "pumpetid"
        )}
        ${this._rute(
          "mdi:water-pump",
          `${nf(this.val("volum", 0), 0)} m³`,
          "Pumpet i dag",
          "volum"
        )}
        ${this._rute("mdi:flash", `${nf(effekt, 0)} W`, "Effekt nå", "pumpeEffekt")}
        ${this._rute(
          "mdi:piggy-bank-outline",
          `${nf(this.val("spart", 0), 0)} ${valuta}`,
          "Spart i dag",
          "spart"
        )}
      </div>

      <div class="fotnote">
        <span>Neste start ${nesteTekst}</span>
        <span
          >${nf(this.val("kostnad", 0), 1)} ${valuta} brukt ·
          ${nf(this.val("pumpeEnergi", 0) + (this.val("vpEnergi", 0) || 0), 1)} kWh</span
        >
      </div>
    `;
  }

  _sirkulasjon() {
    const blokker = this.attr("modus", "blokker") || [];
    const snittPlan = this.attr("modus", "snittpris_plan");
    const snittDogn = this.attr("modus", "snittpris_dogn");
    const profil = this.st("profil");
    const anbefalt = this.attr("omsetninger", "anbefalt");

    return html`
      <div class="blokk">
        <div class="blokk-tittel">Døgnplan</div>
        ${this._tidslinje()}
        ${blokker.length
          ? blokker.map(
              (b, i) => html`
                <div class="rad">
                  <span>Blokk ${i + 1}</span><span class="tall">${b}</span>
                </div>
              `
            )
          : html`<div class="tom">Ingen blokker planlagt akkurat nå.</div>`}
        ${snittPlan !== undefined && snittPlan !== null
          ? html`
              <div class="rad">
                <span>Snittpris i planen</span>
                <span class="tall">${nf(snittPlan, 2)}</span>
              </div>
              <div class="rad">
                <span>Snittpris hele døgnet</span>
                <span class="tall">${nf(snittDogn, 2)}</span>
              </div>
            `
          : ""}
      </div>

      ${profil
        ? html`
            <div class="blokk">
              <div class="blokk-tittel">Profil</div>
              <div class="chips">
                ${(profil.attributes.options || []).map(
                  (o) => html`
                    <button
                      class="chip ${profil.state === o ? "aktiv" : ""}"
                      @click=${() => this._velg(o)}
                    >
                      ${PROFIL_TEKST[o] || o}
                    </button>
                  `
                )}
              </div>
              ${anbefalt
                ? html`<div class="hint">
                    Vanntemperaturen tilsier ${nf(anbefalt, 2)} omsetninger i døgnet.
                  </div>`
                : ""}
            </div>
          `
        : ""}

      <div class="blokk">
        ${this._stepper("mal", "Omsetninger per døgn", 0.25, 2, "×")}
        ${this._stepper("puls", "Vedlikeholdspuls", 1, 0, " min")}
      </div>

      <div class="piller">
        ${this._bryter("auto", "Automatikk", "mdi:robot-outline")}
        ${this._bryter("pris", "Prisstyring", "mdi:cash-clock")}
        ${this._bryter("varme", "Varmeprioritet", "mdi:heat-wave")}
      </div>

      <button class="stor" @click=${() => this._trykk("boost")}>
        <ha-icon icon="mdi:fan-plus"></ha-icon> Boost sirkulasjon i 30 min
      </button>

      ${this.on("overstyrt")
        ? html`<div class="varsel">
            Manuell overstyring aktiv – automatikken er satt på pause.
          </div>`
        : ""}
      ${this.on("vpVenter")
        ? html`<div class="varsel">
            Varmepumpen står av og venter på at sirkulasjonen kommer tilbake.
          </div>`
        : ""}
    `;
  }

  _spreder() {
    const går = this.on("spreder");
    const igjen = this.val("spredertid", 0) || 0;
    const varighet = this.val("spredVarighet", 10) || 10;
    const brukt = this.attr("spredertid", "brukt_i_dag_min") || 0;
    const maks = this.val("spredMaks", 0) || 0;
    const andel = går ? Math.max(0, Math.min(1, igjen / varighet)) : 0;

    return html`
      <div class="spreder-hero ${går ? "gar" : ""}">
        <ha-icon icon="${går ? "mdi:sprinkler-variant" : "mdi:sprinkler"}"></ha-icon>
        <div class="spreder-tall">
          ${går ? `${Math.ceil(igjen)} min igjen` : this.attr("spredertid", "status") || "Klar"}
        </div>
        <div class="spreder-linje">
          <div style="width:${andel * 100}%"></div>
        </div>
      </div>

      <div class="chips">
        ${[5, 10, 20, 30].map(
          (m) => html`
            <button
              class="chip ${Math.round(varighet) === m ? "aktiv" : ""}"
              @click=${() => this._sett("spredVarighet", m)}
            >
              ${m} min
            </button>
          `
        )}
      </div>

      <button
        class="stor ${går ? "stopp" : "start"}"
        @click=${() => this._trykk(går ? "stoppSpreder" : "startSpreder")}
      >
        <ha-icon icon="${går ? "mdi:stop" : "mdi:play"}"></ha-icon>
        ${går ? "Stopp sprederen" : `Start sprederen i ${Math.round(varighet)} min`}
      </button>

      <div class="blokk">
        <div class="rad">
          <span>Brukt i dag</span>
          <span class="tall"
            >${nf(brukt, 0)} min${maks ? ` av ${nf(maks, 0)}` : ""}</span
          >
        </div>
        ${this._stepper("spredIntervall", "Program: start hver", 1, 0, " t")}
        <div class="piller">
          ${this._bryter("spredprogram", "Program", "mdi:repeat")}
          ${this._bryter("frostvakt", "Frostvakt", "mdi:snowflake-alert")}
        </div>
        <div class="hint">
          Programmet kjører bare mellom 10 og 20, og stopper når døgnets grense er
          nådd.
        </div>
      </div>
    `;
  }

  _innstillinger() {
    const rader = [
      ["dagtimer", "Dagtimer i planen", 1, 0, " t"],
      ["minTid", "Minste kjøretid", 5, 0, " min"],
      ["overstyringTid", "Manuell overstyring varer", 15, 0, " min"],
      ["varmeStart", "Varmevindu start", 1, 0, ":00"],
      ["varmeSlutt", "Varmevindu slutt", 1, 0, ":00"],
      ["basislast", "Pumpe basislast", 10, 0, " W"],
      ["spredMaks", "Spreder maks per døgn", 10, 0, " min"],
    ];
    return html`
      <div class="blokk">
        ${rader.map(([k, t, s, d, suf]) => this._stepper(k, t, s, d, suf))}
      </div>
      <div class="piller">
        ${this._bryter("styrVp", "Styr varmepumpe", "mdi:heat-pump-outline")}
        ${this._bryter("pulsVarme", "Puls med varme", "mdi:fire-circle")}
      </div>
      <div class="blokk">
        <div class="rad">
          <span>Pumpet totalt</span>
          <span class="tall">${nf(this.val("volumTotalt", 0), 1)} m³</span>
        </div>
        <div class="rad">
          <span>Én omsetning tar</span>
          <span class="tall"
            >${nf(this.attr("omsetninger", "en_omsetning_timer"), 2)} t</span
          >
        </div>
      </div>
      <button class="stor stille" @click=${() => this._trykk("nullstill")}>
        <ha-icon icon="mdi:backup-restore"></ha-icon> Nullstill dagens tellere
      </button>
      <div class="hint">ki-basseng-card ${KIB_VERSION} · ${this.prefix}</div>
    `;
  }

  /* --- render ------------------------------------------------------- */

  render() {
    if (!this.hass || !this._config) return html``;
    if (!this.st("modus")) {
      return html`
        <ha-card>
          <div class="tom stor-tom">
            Fant ingen entiteter med prefikset
            <code>${this.prefix}</code>. Sett opp integrasjonen KI Basseng, eller
            oppgi <code>prefix:</code> i kortet.
          </div>
        </ha-card>
      `;
    }

    const faner = this._config.faner;
    const innhold = {
      oversikt: () => this._oversikt(),
      sirkulasjon: () => this._sirkulasjon(),
      spreder: () => this._spreder(),
      innstillinger: () => this._innstillinger(),
    };
    const aktiv = faner.includes(this._fane) ? this._fane : faner[0];

    return html`
      <ha-card>
        ${this._config.tittel
          ? html`<div class="topp">${this._config.tittel}</div>`
          : ""}
        ${faner.length > 1
          ? html`
              <div class="faner">
                ${faner.map(
                  (f) => html`
                    <button
                      class="fane ${aktiv === f ? "aktiv" : ""}"
                      @click=${() => (this._fane = f)}
                    >
                      ${f[0].toUpperCase() + f.slice(1)}
                    </button>
                  `
                )}
              </div>
            `
          : ""}
        <div class="innhold">${innhold[aktiv]()}</div>
      </ha-card>
    `;
  }

  static get styles() {
    return css`
      :host {
        --kib-surface: var(--gray200, var(--card-background-color, #1c1c1e));
        --kib-inner: var(--gray100, rgba(127, 127, 127, 0.12));
        --kib-text: var(--gray1000, var(--primary-text-color, #fafbfc));
        --kib-muted: var(--gray600, var(--secondary-text-color, #8e8e93));
        --kib-accent: var(--active-big, var(--primary-color, #4dd07a));
        --kib-blue: var(--blue, #4a9df8);
        --kib-orange: var(--orange, #f0a03c);
        --kib-red: var(--red, #e8604c);
      }
      ha-card {
        background: none;
        border: none;
        box-shadow: none;
        color: var(--kib-text);
        overflow: visible;
      }
      .topp {
        font-size: 15px;
        font-weight: 600;
        padding: 0 4px 10px;
      }
      .faner {
        display: flex;
        gap: 6px;
        overflow-x: auto;
        scrollbar-width: none;
        padding-bottom: 12px;
      }
      .faner::-webkit-scrollbar {
        display: none;
      }
      .fane {
        flex: 1 0 auto;
        border: none;
        cursor: pointer;
        padding: 9px 16px;
        border-radius: 14px;
        background: var(--kib-surface);
        color: var(--kib-muted);
        font: inherit;
        font-size: 14px;
        font-weight: 500;
      }
      .fane.aktiv {
        background: var(--kib-accent);
        color: #000;
      }
      .innhold {
        display: flex;
        flex-direction: column;
        gap: 12px;
      }

      /* hero */
      .hero {
        display: flex;
        align-items: center;
        gap: 18px;
        background: var(--kib-surface);
        border-radius: 22px;
        padding: 18px 20px;
      }
      .ring {
        width: 108px;
        height: 108px;
        flex: none;
        cursor: pointer;
      }
      .ring .spor {
        fill: none;
        stroke: var(--kib-inner);
        stroke-width: 9;
      }
      .ring .fylt {
        fill: none;
        stroke-width: 9;
        stroke-linecap: round;
        transform: rotate(-90deg);
        transform-origin: 60px 60px;
        transition: stroke-dashoffset 0.6s ease;
      }
      .ring-tall {
        fill: var(--kib-text);
        font-size: 24px;
        font-weight: 600;
        text-anchor: middle;
      }
      .ring-under {
        fill: var(--kib-muted);
        font-size: 12px;
        text-anchor: middle;
      }
      .hero-tekst {
        min-width: 0;
      }
      .temp {
        font-size: 42px;
        font-weight: 300;
        line-height: 1;
        cursor: pointer;
      }
      .temp span {
        font-size: 18px;
        opacity: 0.6;
        margin-left: 2px;
      }
      .merke {
        display: inline-flex;
        align-items: center;
        gap: 5px;
        margin-top: 10px;
        padding: 4px 11px 4px 8px;
        border-radius: 999px;
        color: #000;
        font-size: 13px;
        font-weight: 600;
      }
      .merke ha-icon {
        --mdc-icon-size: 16px;
      }
      .begrunnelse {
        margin-top: 8px;
        font-size: 12px;
        color: var(--kib-muted);
        line-height: 1.4;
      }

      /* tidslinje */
      .tidslinje {
        background: var(--kib-surface);
        border-radius: 18px;
        padding: 14px 16px 10px;
      }
      .spor-24 {
        position: relative;
        display: flex;
        gap: 2px;
        height: 16px;
      }
      .time {
        flex: 1;
        border-radius: 3px;
        background: var(--kib-inner);
      }
      .time.planlagt {
        background: var(--kib-blue);
      }
      .time.na {
        outline: 1px solid var(--kib-text);
        outline-offset: 1px;
      }
      .naalinje {
        position: absolute;
        top: -3px;
        bottom: -3px;
        width: 2px;
        background: var(--kib-text);
        opacity: 0.75;
      }
      .naalinje.gar {
        background: var(--kib-accent);
        opacity: 1;
      }
      .klokkeslett {
        display: flex;
        justify-content: space-between;
        font-size: 11px;
        color: var(--kib-muted);
        padding-top: 5px;
      }

      /* ruter */
      .ruter {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 8px;
      }
      @media (max-width: 430px) {
        .ruter {
          grid-template-columns: repeat(2, 1fr);
        }
      }
      .rute {
        background: var(--kib-surface);
        border-radius: 18px;
        padding: 14px 12px;
        cursor: pointer;
      }
      .rute ha-icon {
        --mdc-icon-size: 18px;
        color: var(--kib-muted);
      }
      .rute-tall {
        font-size: 19px;
        font-weight: 600;
        padding-top: 8px;
      }
      .rute-tekst {
        font-size: 12px;
        color: var(--kib-muted);
        padding-top: 2px;
      }
      .fotnote {
        display: flex;
        justify-content: space-between;
        gap: 10px;
        font-size: 12px;
        color: var(--kib-muted);
        padding: 0 6px;
        flex-wrap: wrap;
      }

      /* blokker */
      .blokk {
        background: var(--kib-surface);
        border-radius: 18px;
        padding: 14px 16px;
        display: flex;
        flex-direction: column;
        gap: 10px;
      }
      .blokk-tittel {
        font-size: 12px;
        color: var(--kib-muted);
        letter-spacing: 0.4px;
      }
      .rad {
        display: flex;
        justify-content: space-between;
        font-size: 14px;
      }
      .rad span:first-child {
        color: var(--kib-muted);
      }
      .tall {
        font-variant-numeric: tabular-nums;
      }
      .tom {
        font-size: 13px;
        color: var(--kib-muted);
      }
      .stor-tom {
        background: var(--kib-surface);
        border-radius: 18px;
        padding: 20px;
        line-height: 1.5;
      }
      .hint {
        font-size: 12px;
        color: var(--kib-muted);
        line-height: 1.45;
      }
      .varsel {
        background: var(--kib-inner);
        border-left: 3px solid var(--kib-orange);
        border-radius: 12px;
        padding: 12px 14px;
        font-size: 13px;
        line-height: 1.45;
      }

      /* knapper */
      .chips {
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
      }
      .chip {
        flex: 1;
        min-width: 72px;
        border: none;
        cursor: pointer;
        padding: 10px 6px;
        border-radius: 14px;
        background: var(--kib-inner);
        color: var(--kib-text);
        font: inherit;
        font-size: 14px;
      }
      .chip.aktiv {
        background: var(--kib-accent);
        color: #000;
        font-weight: 600;
      }
      .piller {
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
      }
      .pille {
        flex: 1;
        min-width: 104px;
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 6px;
        border: none;
        cursor: pointer;
        padding: 12px 8px;
        border-radius: 16px;
        background: var(--kib-surface);
        color: var(--kib-text);
        font: inherit;
        font-size: 13px;
      }
      .pille ha-icon {
        --mdc-icon-size: 18px;
      }
      .pille.aktiv {
        background: var(--kib-accent);
        color: #000;
        font-weight: 600;
      }
      .stor {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 8px;
        border: none;
        cursor: pointer;
        width: 100%;
        padding: 16px;
        border-radius: 18px;
        background: var(--kib-accent);
        color: #000;
        font: inherit;
        font-size: 15px;
        font-weight: 600;
      }
      .stor.stopp {
        background: var(--kib-red);
      }
      .stor.stille {
        background: var(--kib-surface);
        color: var(--kib-text);
        font-weight: 500;
      }

      /* stepper */
      .stepper {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
      }
      .stepper-tekst {
        font-size: 14px;
        color: var(--kib-muted);
      }
      .stepper-styring {
        display: flex;
        align-items: center;
        gap: 4px;
      }
      .stepper-styring button {
        border: none;
        cursor: pointer;
        width: 34px;
        height: 34px;
        border-radius: 50%;
        background: var(--kib-inner);
        color: var(--kib-text);
        display: grid;
        place-items: center;
      }
      .stepper-styring ha-icon {
        --mdc-icon-size: 18px;
      }
      .stepper-verdi {
        min-width: 76px;
        text-align: center;
        font-size: 15px;
        font-weight: 600;
        font-variant-numeric: tabular-nums;
      }

      /* spreder */
      .spreder-hero {
        background: var(--kib-surface);
        border-radius: 22px;
        padding: 22px;
        text-align: center;
      }
      .spreder-hero ha-icon {
        --mdc-icon-size: 40px;
        color: var(--kib-muted);
      }
      .spreder-hero.gar ha-icon {
        color: var(--kib-blue);
        animation: vipp 2.4s ease-in-out infinite;
      }
      @keyframes vipp {
        0%,
        100% {
          transform: rotate(-12deg);
        }
        50% {
          transform: rotate(12deg);
        }
      }
      @media (prefers-reduced-motion: reduce) {
        .spreder-hero.gar ha-icon {
          animation: none;
        }
      }
      .spreder-tall {
        font-size: 20px;
        font-weight: 600;
        padding-top: 8px;
      }
      .spreder-linje {
        margin-top: 14px;
        height: 6px;
        border-radius: 4px;
        background: var(--kib-inner);
        overflow: hidden;
      }
      .spreder-linje div {
        height: 100%;
        background: var(--kib-blue);
        transition: width 1s linear;
      }
      button:focus-visible {
        outline: 2px solid var(--kib-accent);
        outline-offset: 2px;
      }
    `;
  }
}

/* ------------------------------------------------------------------ */
/* Enkel editor                                                        */
/* ------------------------------------------------------------------ */

class KiBassengCardEditor extends LitElement {
  static get properties() {
    return { hass: {}, _config: {} };
  }

  setConfig(config) {
    this._config = config;
  }

  _endret(ev) {
    const config = { ...this._config, ...ev.detail.value };
    this.dispatchEvent(
      new CustomEvent("config-changed", { detail: { config }, bubbles: true, composed: true })
    );
  }

  render() {
    if (!this.hass || !this._config) return html``;
    const schema = [
      { name: "tittel", selector: { text: {} } },
      { name: "prefix", selector: { text: {} } },
      {
        name: "faner",
        selector: {
          select: {
            multiple: true,
            mode: "list",
            options: [
              { value: "oversikt", label: "Oversikt" },
              { value: "sirkulasjon", label: "Sirkulasjon" },
              { value: "spreder", label: "Spreder" },
              { value: "innstillinger", label: "Innstillinger" },
            ],
          },
        },
      },
    ];
    return html`
      <ha-form
        .hass=${this.hass}
        .data=${{ faner: ["oversikt", "sirkulasjon", "spreder", "innstillinger"], ...this._config }}
        .schema=${schema}
        .computeLabel=${(s) =>
          ({ tittel: "Tittel", prefix: "Entitetsprefiks", faner: "Faner" }[s.name] || s.name)}
        @value-changed=${this._endret}
      ></ha-form>
    `;
  }
}

customElements.define("ki-basseng-card", KiBassengCard);
customElements.define("ki-basseng-card-editor", KiBassengCardEditor);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "ki-basseng-card",
  name: "KI Basseng",
  preview: true,
  description: "Sirkulasjon, varme og spreder for bassenget",
});

console.info(
  `%c KI-BASSENG-CARD %c ${KIB_VERSION} `,
  "background:#4a9df8;color:#000;font-weight:600;border-radius:3px 0 0 3px",
  "background:#333;color:#fff;border-radius:0 3px 3px 0"
);
