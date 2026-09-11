# KI Basseng

Sirkulasjon, varme og spreder for bassenget i Strömstad, samlet i én
integrasjon og ett kort.

Kjernen er avveiningen mellom tre ting som drar hver sin vei:

- **Spare strøm.** Pumpen skal ikke gå døgnet rundt på 800 W.
- **Nok omsetning.** Vannet må likevel gjennom filteret ofte nok til at det
  holder seg klart.
- **Nok tid til varmepumpen.** Varmepumpen kan ikke jobbe uten sirkulasjon,
  så når den vil varme, må pumpen gå uansett hva prisen sier.

Integrasjonen løser dette med et omsetningsmål per døgn i stedet for et
fast antall timer, legger de timene på døgnets billigste perioder, og lar
varmen overstyre planen når det trengs.

## Slik virker styringen

Én omsetning er `volum / kapasitet`, altså 40,95 / 11,3 ≈ 3,62 timer. Målet
settes i omsetninger, ikke timer, slik at det følger bassenget og ikke
kalenderen.

| Modus | Når | Pumpen |
|---|---|---|
| Oppvarming | Varmepumpen varmer, innenfor varmevinduet | Går |
| Filtrering | Omsetningsmålet er ikke nådd, og timen står i planen | Går |
| Hvile | Målet er nådd, eller den venter på en billig time | Står |
| Vedlikehold | Målet er nådd, men den gir noen minutter sirkulasjon i timen | Pulser |
| Boost | Du trykket på knappen | Går |
| Manuell | Du tok på bryteren selv | Rører den ikke |

Planen bygges fra prissensoren: de billigste timene velges, nattetimer får
et lite påslag (bassenget skummes ikke fritt for løv mens alle sover), og
minst et par dagtimer holdes av. Mangler prisdata, faller den tilbake på en
fast liste. Timer som allerede er gjennomført, blir stående, slik at planen
ikke hopper rundt utover dagen.

Tar du på pumpebryteren manuelt, merker integrasjonen at kommandoen ikke kom
fra den selv og legger seg flat i et valgt antall minutter.

### Varmepumpesperren

Går pumpen av mens varmepumpen står på, slår integrasjonen av varmepumpen
etter ett minutt og husker settpunktet. Når sirkulasjonen er tilbake og har
vært stabil i to minutter, settes settpunkt og varmemodus tilbake. Under
vedlikeholdspulser holdes varmen av med mindre *Puls med varme* står på.

### Effektsplitt

Smartpluggen måler pumpe og varmepumpe samlet. Integrasjonen deler målingen
i to: pumpen står for basislasten når bryteren er på, resten tilhører
varmepumpen. Bryterens tilstand brukes som fasit i stedet for terskelen
alene, så du slipper feilklassifisering i grenselandet rundt 900 W.

### Spreder

Hageslangen på hovedkranen med spreder ned i bassenget styres med varighet,
valgfritt program (start hver N. time mellom 10 og 20), tak per døgn og en
frostvakt som nekter å åpne ventilen når det er under 2 °C ute.

## Installasjon

1. Legg `custom_components/ki_basseng/` i `/config/`, eller legg repoet til
   som egendefinert HACS-repo.
2. Start Home Assistant på nytt.
3. **Innstillinger → Enheter og tjenester → Legg til → KI Basseng.**

Oppsettet går i tre steg:

| Steg | Felt |
|---|---|
| Måling | pumpebryter (påkrevd), kombinert effektmåler, eventuelle separate målere, prissensor |
| Utstyr | varmepumpe, innløp, utløp, utetemperatur, vannventil for spreder |
| Bassenget | volum, kapasitet, basislast, varmepumpens merkeeffekt, valuta |

For ditt oppsett:

```
Pumpebryter        switch.bassengpumpe
Kombinert måler    sensor.bassengpumpe_power
Prissensor         sensor.stromstad_totalpris_kwh_sek
Varmepumpe         climate.basseng_bassengvarmepumpe
Innløp             sensor.basseng_bassengvarmepumpe_water_inflow_temperature
Utløp              sensor.basseng_bassengvarmepumpe_water_outflow_temperature
Vannventil         switch.ute_master_vannventil
Volum              40.95        (estimatpakken sier 7,3 × 3,3 × 1,7)
Kapasitet          11.3
Basislast          800
```

Volumet spriker mellom de to pakkene dine: pumpestyringen regner 35,6 m³,
estimatpakken 40,95 m³. Det er 15 % forskjell på hvor lenge pumpen må gå per
omsetning, så det er verdt å måle opp en gang for alle.

## Entiteter

Alt havner på enheten **KI Basseng** med prefiks `ki_basseng`.

**Sensorer:** pumpemodus (med plan, blokker og snittpriser som attributter),
omsetninger i dag, pumpet volum i dag/totalt, pumpetid i dag, neste
pumpestart, pumpe- og varmepumpeeffekt, energi i dag for begge, kostnad i
dag, spart i dag, vanntemperatur, spreder gjenstår.

**Binærsensorer:** pumpe skal gå, spreder kjører, manuell overstyring,
varmepumpe venter.

**Brytere:** automatikk, prisstyring, varmeprioritet, styr varmepumpe, puls
med varme, spreder-program, frostvakt.

**Tall:** omsetninger per døgn, vedlikeholdspuls, minste kjøretid, manuell
overstyring varer, dagtimer i planen, varmevindu start/slutt, pumpe
basislast, spreder varighet/intervall/maks per døgn.

**Valg:** driftsprofil (eco, balansert, badeklar, ferie). Profilen setter
omsetningsmål og puls i ett grep, og hopper til «egendefinert» hvis du
justerer noe manuelt etterpå.

**Knapper:** start og stopp spreder, boost sirkulasjon, nullstill dagens
tellere.

## Tjenester

```yaml
action: ki_basseng.start_spreder
data:
  minutter: 15

action: ki_basseng.boost
data:
  minutter: 45

action: ki_basseng.sett_profil
data:
  profil: badeklar
```

## Kortet

Legg `ki-basseng-card.js` i `/config/www/` og registrer den under
**Innstillinger → Dashbord → Ressurser** som `/local/ki-basseng-card.js`.

```yaml
type: custom:ki-basseng-card
tittel: Badebasseng
faner: [oversikt, sirkulasjon, spreder, innstillinger]
```

`prefix:` kan utelates — kortet finner entitetene selv. Har du flere
bassenger, oppgi prefiks for hvert kort.

Fanen *Oversikt* viser omsetningsringen, vanntemperatur, modus med
begrunnelse, døgnplanen som en 24-timers stripe med nå-markør, og fire
nøkkeltall. *Sirkulasjon* har blokkene, profilvalg, steppere for mål og
puls, og boost. *Spreder* har nedtelling og hurtigvalg. *Innstillinger* har
resten.

Se `examples/badebasseng-popup.yaml` for en bubble-card-popup i samme stil
som resten av dashbordet ditt.

## Hva dette erstatter

Fjern disse fra `packages/` når integrasjonen er satt opp, ellers krangler
de om den samme pumpen:

- `basseng_pumpestyring.yaml` i sin helhet
- `bassengpumpe_split.yaml` i sin helhet
- `pumpe_volum.yaml` i sin helhet
- sprederdelen av `ki_basseng_varmestyring.yaml`
  (`input_boolean.ki_bassengsprinkler_*`, `input_number.ki_bassengsprinkler_varighet_min`,
  `input_text.ki_bassengsprinkler_nedtelling_tekst`)
- `sensor.ki_basseng_pumpemodus` og pumpedelen av samme pakke

`basseng_estimat.yaml` kan bli stående. Den regner på varmetap,
oppvarmingstid og nattsenking, og rører ikke sirkulasjonen. Den eneste
overlappen er at begge kan sette settpunktet på varmepumpen — la
estimatpakken eie settpunktet, og la denne integrasjonen eie av/på og
sirkulasjonen.

## Tuning

- **Pumpen går for lite.** Øk omsetningsmålet, eller bytt profil til
  badeklar. Er vannet over 27 °C, foreslår sensoren 2,5 omsetninger.
- **Planen ligger midt på natten.** Øk *Dagtimer i planen*.
- **Effektsplitten ser feil ut.** Les av `sensor.bassengpumpe_power` mens
  bare sirkulasjonspumpen går, og sett *Pumpe basislast* til den verdien.
- **Varmepumpen starter ikke igjen.** Sjekk at *Styr varmepumpe* er på og at
  pumpen har gått sammenhengende i over to minutter.

## Lisens

MIT.
