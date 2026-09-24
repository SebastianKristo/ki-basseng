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
