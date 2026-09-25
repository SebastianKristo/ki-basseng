# KI Basseng 1.9.0

## Velg mobilene som får varsel

*Varsle med* under Utstyr er nå en meny over varslingstjenestene som finnes, med mobilene
(`notify.mobile_app_*`) først og med navn. Velg én eller flere. Det som var skrevet inn som
tekst i 1.8, gjelder fortsatt og står valgt i menyen.

## Klorstatus

Ny sensor *Klorstatus*: `trenger_klor` eller `ok`, med hvor lenge til som attributter:

| Attributt | Hva |
|---|---|
| `trenger_klor` | Om det er på tide |
| `tekst` | «Om 3 dager», «Om 5 t», «I dag», «2 dager på overtid» |
| `neste`, `siste` | Neste og siste klortablett |
| `timer_til`, `dager_til` | Tid til neste (0 når det er på tide) |
| `overtid_dager` | Hvor lenge det har vært på tide |
| `dager_siden`, `intervall_dager` | Siden sist, og intervallet (kortere i varmt vann) |

Når det blir på tide, varsles mobilene én gang per tablett (bryteren *Varsle om klor*, på som
standard), og hendelsen `ki_basseng_klor` sendes.

---

# KI Basseng 1.8.0

## Vannivå med varsel og automatisk påfylling

En vannsensor festet i bassenget sier om det er nok vann: våt er fullt nok, tørr betyr at
det må fylles. Velg den under Utstyr (*Vannsensor i bassenget*). Uten sensor lages ingen av
de nye entitetene, og kortet viser ikke vannivået.

- **Varsel:** har sensoren vært tørr i *Tørr før varsel* (45 min), slår *Bassenget trenger
  vann* seg på og det varsles én gang: varsel i Home Assistant, tjenestene under *Varsle med*
  (f.eks. `notify.mobile_app_iphone`, flere med komma) og hendelsen `ki_basseng_vanniva`.
  Når sensoren er våt igjen, forsvinner varselet.
- **Automatisk påfylling** (bryter, av som standard): ventilen åpnes – *Ventil for påfylling*,
  eller hovedkranen sprederen bruker – og stenges så snart sensoren er våt.
- **Sikring:** etter *Maks påfylling* (60 min) uten at sensoren ble våt stenges ventilen, det
  varsles, og det fylles ikke automatisk igjen før sensoren har vært våt.
- **For hånd:** knappene *Fyll bassenget* og *Stopp påfylling*.
- Sprederen stenger ikke ventilen midt i en påfylling, og frostvakten gjelder også her.

Nye entiteter: sensor *Vannivå*, binærsensor *Bassenget trenger vann*, brytere *Automatisk
påfylling* og *Varsle om vannivå*, tall *Tørr før varsel* og *Maks påfylling*, knapper *Fyll
bassenget* og *Stopp påfylling*.

---

# KI Basseng 1.7.0

## Tid og kostnad til målet

Sensoren *Måltemperatur* forteller nå hvor lenge det tar å varme vannet opp til målet, og
hva det koster, med varmepumpa på fra nå:

| Attributt | Hva |
|---|---|
| `minutter_til_mal` | Minutter til vannet er på målet (0 når det er der) |
| `klar_kl` | Klokkeslettet det er klart |
| `oppvarming_kwh`, `oppvarming_kostnad` | Strømmen varmepumpa og sirkulasjonspumpa bruker på veien, og hva den koster |
| `rekker_malet` | `false` når varmepumpa ikke når målet innen to døgn |

Varmemodellen regner time for time med været, sola, pooltaket og strømprisen, i tidelsteg
så varmetapet følger vannet opp. I filtreringstimer koster ikke sirkulasjonspumpa ekstra.
Anslaget regnes hvert femte minutt, og med en gang ønsket temperatur eller taket endres.
Kostnaden står tom hvis en av timene mangler pris. I vintermodus er det ikke noe mål å nå.

## Klorloggen

*Siste klortablett* har fått `speiles_til`: kalenderen tablettene også skrives til (for
eksempel Google Kalender, valgt under Utstyr), så kortet kan vise det.

Det nye kortet (ki-basseng-card 3.0 i ki-cards 5.75) viser det som «Vannet når 27° om ca
2 t 10 min, og det koster ca 4 kroner».

---

# KI Basseng 1.6.0

## Hva «spart i dag» består av

*Spart i dag* er fortsatt det målte tallet: hva pumpa ville kostet i døgndrift, minus hva
den faktisk kostet. Nå står det i attributtene hva tallet består av. De to første går
nøyaktig opp i det målte:

| Attributt | Hva |
|---|---|
| `sirkulasjon_kwh`, `sirkulasjon_kr` | Færre pumpetimer: kWh pumpa slapp å bruke, ganget med snittprisen så langt i døgnet |
| `billigere_timer_kr` | Prisstyringen: at timene pumpa gikk var billigere enn snittet |
| `snittpris_pumpe`, `snittpris_dogn_sa_langt` | Hva pumpa betalte per kWh, mot snittet |
| `pumpetimer`, `timer_med_pris` | Timer pumpa gikk, av timene med kjent pris |
| `nattsenking_kwh_anslatt`, `nattsenking_kr_anslatt` | Det modellen regnet ut da den valgte nattens av-vindu |
| `med_nattsenking_kr` | Det målte pluss anslaget for nattsenkingen |
| `pooltak_kwh_anslatt`, `pooltak_kr_anslatt` | Varmetapet taket hindret, minus solen det stengte ute, i strøm (kan være negativt en solrik dag) |
| `uten_ki_kr`, `med_ki_kr` | Pumpe i døgndrift + varmepumpe + det nattsenkingen sparte, mot det som faktisk ble brukt |
| `i_gar`, `denne_maneden`, `totalt` | Målt besparelse bakover i tid |

Anslagene fra varmemodellen (nattsenking og pooltak) holdes utenfor det målte tallet.
Pooltaket er ikke KI-ens fortjeneste, men det er verdt å se hva det gjør.

Dagen integrasjonen oppdateres, startet de nye tellerne midt i døgnet. Oppdelingen vises
derfor fra neste døgn. Det målte tallet er som før hele tiden.

---

# KI Basseng 1.5.0

## Den varmet ikke om morgenen – rettet

Bassenget kunne stå på 25 °C i vedlikehold om morgenen uten å varme. To feil samvirket:

* **Varmepumpetilstanden overlevde ikke en omstart.** Integrasjonen husket bare i minnet at
  den selv hadde slått av varmepumpa (for natta eller fordi sirkulasjonen manglet). Etter en
  omstart eller oppdatering trodde den at pumpa var slått av med vilje, og ba aldri om varme
  igjen. Nå lagres tilstanden. Første oppstart med denne versjonen regner en avslått
  varmepumpe som integrasjonens egen, så den kommer tilbake med sirkulasjonen.
* **Nattsenkingen var for snill med fristen.** Rakk ikke varmepumpa målet selv om den gikk
  hele natta, godtok senkingen å ende like langt unna målet. Nå må vannet være tilbake på
  målet når varmevinduet starter, ellers blir det ingen senking. Ligger vannet alt et halvt
  grad under målet, tas det igjen før det senkes.

**Hvorfor varmer den ikke?** Når vannet er under målet uten at den varmer, står grunnen i
begrunnelsen og i attributtet `varmer_ikke_fordi` på pumpemodus. Mulige grunner:
nattsenking til 06:00, varmeprioritet er av, utenfor varmevinduet, varmepumpa er slått av
utenfor integrasjonen, eller varmepumpa svarer ikke. Kortet viser den som et varsel.

## Vintermodus

Ny bryter: **Vintermodus**. Med den på:

* **Varmepumpa** slås av. Den settes ikke tilbake før vintermodus er av.
* **Varmeelementene i bassenghuset** går på under *Frostsikring: varme på under* (5 °C) og
  av igjen to grader over. Temperaturen tas fra føleren i bassenghuset, eller fra
  utetemperaturen hvis det ikke finnes noen føler.
* **Frostsikring:** under *Frostsikring: sirkulasjon under* (0 °C ute) går pumpa hele tiden
  (modus `frostsikring`).
* **Sirkulasjon** ellers etter *Omsetninger per døgn om vinteren* (0,5).

Nytt i oppsettet under Utstyr: *Temperatur i bassenghuset* og *Varmeelementer* (bryter,
`input_boolean`, `climate` eller lys).

## Pooltak med dør- eller vindussensor

En dør- eller vindussensor er «på» når den er åpen, altså når taket er av. Sensorer med
device class door, window, opening eller garage_door tolkes riktig av seg selv. For andre
finnes en ny avhaking i oppsettet: *Pooltak-sensoren er «på» når taket er ÅPENT*.

## Klorloggen kan redigeres, og er en kalender

* **Ny kalender, `calendar.ki_basseng_klorlogg`:** hver tablett er en hendelse, og neste
  forfallsdag er en heldagshendelse. Du kan legge inn og slette tabletter rett i
  kalenderpanelet i Home Assistant. Tittelen på en ny hendelse kan være et navn («Ida»).
* **Etterregistrering:** `logg_klortablett` tar `tidspunkt:`, og innslaget havner på riktig
  plass i tid.
* **Ny tjeneste `slett_klortablett`** (`tid:`) fjerner ett innslag.
* **Google Kalender (eller en annen):** velg den under *Kalender klorloggen også skal skrives
  til*. Da skrives hver tablett også dit med `calendar.create_event`. Slettes et innslag,
  prøver integrasjonen å slette hendelsen der også, men det virker bare hvis kalenderen lar
  seg slette i. Loggen i integrasjonen er fasiten.

---

# KI Basseng 1.4.0

## Hvem la i klortabletten?

* **Navn i klorloggen:** et nytt tekstfelt, `text.ki_basseng_navn_i_klorloggen`, der du skriver
  hvem som kan legge i klortabletter, med komma mellom: «Sebastian, Ida». Mellomrom og
  dubletter ryddes bort. Kortet viser navnene som knapper du huker av før du logger, og
  navnene kan legges til og fjernes under tannhjulet i kortet.
* **`logg_klortablett` har fått feltet `hvem`.** Navnet lagres i loggen og står i loggboka:
  «1 klortablett lagt i av Sebastian».
* **Mer i *Siste klortablett*:**
  * `logg`: alle de siste 50 innslagene, med dato, antall og hvem. Det er dette kalenderen
    i kortet tegner fra.
  * `navn`: navnene fra tekstfeltet.
  * `per_person`: hvor mange tabletter hver person har lagt i.

---

# KI Basseng 1.3.1

* **Tilstedeværelse kan være en bryter.** Feltet godtar nå `switch` i tillegg til personer,
  sporere, soner, grupper, binærsensorer og `input_boolean`. «På» betyr hjemme.
* **Pooltak uten egen entitet.** Feltet for pooltak-entitet er valgfritt og sier det nå.
  Uten det styres taket med bryteren *Pooltak på*, som kortet viser som en egen flis.
  Binærsensoren *Pooltak* er fjernet; den speilet bare bryteren.
* Begrunnelsen for nattsenkingen skriver desimalkomma: «sparer 1,4 kWh».

---

# KI Basseng 1.3.0

## Smart nattsenking: av bare når det lønner seg

Den nye varmemodellen (`termisk.py`) simulerer bassenget time for time. Den tar
inn sted og sol, timesvarsel fra en `weather`-entitet, strømpris, tid, om noen
er hjemme, ønsket temperatur, om pooltaket ligger på, og en eventuell solfanger.

Hvert tiende minutt sammenligner den to ting: å holde temperaturen hele natten,
og hvert mulige av-vindu frem til varmevinduet starter. Varmepumpen slås av bare
når et vindu gir badeklart vann i tide og holder seg innenfor maks senking. I
tillegg må det spare etter valgt kriterium. Standard er at det skal spare penger,
men aldri bruke mer strøm totalt. Det som mangler på målet til slutt, regnes med,
så det å utsette oppvarmingen teller aldri som en besparelse.

Modellen lærer COP fra målt Δt, og varmetapet med og uten tak fra rolige netter.

## Ønsket temperatur, borte-senking og pooltak

* **Ønsket temperatur** eier nå varmepumpens settpunkt (bryteren *Styr
  settpunkt*).
* **Borte-senking:** er ingen hjemme, eller står profilen på ferie, senkes målet
  med 2 °C (justerbart).
* **Pooltak:** tilstanden hentes fra en cover-, binær- eller bryterentitet, eller
  fra bryteren *Pooltak på*. Taket endrer både varmetap og solinnslipp.
* **Solfanger:** har du oppgitt et areal, går sirkulasjonen når sola gir varme.
  Den stopper 1 °C over målet. Ny pumpemodus: `solvarme`.
* Varmeprioriteten starter nå pumpen når vannet er 0,3 °C under målet og
  varmepumpen venter på sirkulasjon. Før ventet den på at pumpen startet av
  andre grunner.

## Klortabletter

Ny knapp og tjeneste `logg_klortablett` (antall og notat), og `angre_klortablett`.
Sensorene *Siste klortablett* og *Neste klortablett*, og en binærsensor som sier
fra når det er på tide. I varmt vann blir intervallet kortere.

## Kortet

Ny fane **Varme** med måltemperatur, nattsenking, steppere, pooltak og klorlogg.

## Opprydding

* Én versjon overalt (1.3.0). `const.VERSION` hang igjen på 1.0.1.
* Prisene leses én gang per tikk. Før ble de lest opp til tre ganger.
* Loggboka brukes bare hvis den finnes, så styringen stopper aldri på den.
* 27 nye tester for modellen og integrasjonen i en ekte Home Assistant.

---

# KI Basseng 1.1.0

## Varmepumpa settes tilbake til «heat» når den går i «auto»

Pumpa bytter modus på egen hånd — etter strømbrudd, etter en app-oppdatering, eller bare
fordi den vil. I «auto» styrer den etter sin egen logikk og kan kjøle bassenget like
gjerne som å varme det.

Ny vakthund som kjører hvert minutt: står pumpa i `auto`, settes den til `heat`, og det
skrives i loggboka med antall ganger det har skjedd. Skjer det ofte, er det verdt å vite.

To ting gjør den trygg å kjøre så tett:

* **Bare `auto` røres.** `heat` er der vi vil være, og `off` er noe integrasjonen selv
  setter når sirkulasjonen mangler. Har du satt pumpa til `cool` eller `dry` med vilje,
  overstyres du ikke — det er bare `auto` pumpa havner i av seg selv.
* **Ikke mens sperren har slått av.** Varmepumpesperren slår av pumpa når sirkulasjonen
  mangler og setter `_hp_resume`. Tvang vakthunden den på igjen samtidig, ville de to
  reglene slåss om pumpa hvert minutt. Vakthunden går derfor etter sperren i samme tikk
  og holder seg unna så lenge flagget står.

Ny bryter: **«Tving varmepumpa til heat»**, på som standard.

Ti tester dekker det: auto rettes, heat og off røres ikke, cool/dry/fan_only/heat_cool
røres ikke, den holder seg unna mens sperren har slått av, den kan slås av, den tåler at
climate-entiteten mangler eller er utilgjengelig, den skriver i loggboka, og telleren
øker.

## Popupen

`examples/basseng-popup.yaml` er bygget om i samme form som server-popupen: statuskort
øverst — «Bassenget har det bra», eller hva som feiler — og fem fliser der hver åpner sin
egen del over rutenettet i stedet for å ligge under den.

En av sjekkene er ny: **står varmepumpa i auto, sier statuskortet det.** Da ser du det uten
å åpne noe, i tillegg til at vakthunden retter det.

Fra 168 til 198 linjer, men uten rulling — og med formspråket fra resten av dashbordet.
