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
