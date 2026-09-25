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

### Varmemodellen og smart nattsenking

Integrasjonen har en enkel fysisk modell av bassenget (`termisk.py`) som den
bruker til å vurdere varmen. Den tar inn:

| Inndata | Hvor den kommer fra |
|---|---|
| Sted | Breddegrad og lengdegrad fra Home Assistant. Gir solhøyden time for time |
| Sol | Solhøyde og skydekke gir innstråling (W/m²) på vannflaten og solfangeren |
| Vær | Timesvarsel fra en `weather`-entitet: temperatur og skydekke fremover |
| Strømpris | Timesprisene fra prissensoren, i dag og i morgen |
| Tid | Varmevinduet bestemmer natten og når bassenget skal være varmt igjen |
| Tilstedeværelse | Personer, soner eller brytere («på» er hjemme). Er ingen hjemme, senkes målet |
| Ønsket temperatur | Et tall i integrasjonen. Den holder varmepumpens settpunkt der |
| Pooltak | Bryteren *Pooltak på*, eller en entitet: cover, bryter eller dør-/vindussensor (på = åpent) |
| Solfanger | Areal i oppsettet. Med solfanger går pumpen når sola gir varme |

Bassenget er et stort varmelager: 41 m³ vann holder 48 kWh per grad. Tapet går
gjennom vannflaten og øker med forskjellen mellom vann og luft. Tak kutter det
meste av tapet, men slipper også inn mindre sol.

**Lønner det seg å la varmepumpen stå av i natt?** Kaldere vann taper mindre
varme, så en senking sparer alltid litt varme. Men varmen må hentes inn igjen, og
det kan koste mer strøm enn det sparer:

- om morgenen er lufta kaldest, og varmepumpen har lavest COP
- gjenoppvarmingen kan havne i dyre timer
- sirkulasjonspumpen (800 W) må gå så lenge varmepumpen jobber

Hvert tiende minutt simulerer integrasjonen natten time for time, fra nå til
varmevinduet starter. Den regner først ut hva det koster å holde temperaturen,
og så hvert mulige av-vindu i natt. Et vindu velges bare når:

1. bassenget er tilbake på måltemperaturen før varmevinduet starter,
2. vannet aldri faller mer enn *Maks nattsenking* under målet, og
3. vinduet sparer etter kriteriet i *Nattsenking skal spare*:
   - **begge** (standard): sparer penger og bruker aldri mer strøm totalt
   - **kostnad**: sparer penger, selv om det går med litt mer strøm
   - **energi**: sparer kWh, uansett pris

Det som mangler på målet når horisonten slutter, regnes med som strøm som må
brukes senere. Ellers ville et vindu som bare utsetter oppvarmingen, se ut som
en besparelse.

I praksis lønner senking seg når natten er kald og formiddagen varm og solrik,
når taket er av (stort tap) eller når kvelden er dyr og natten billig. En jevn,
mild natt med flat pris gir som regel *lønner seg ikke*.

Mens senkingen står, er varmepumpen av og krever ikke sirkulasjon.
Filtreringsplanen går som vanlig. Når vinduet er over, setter sperren
varmepumpen på igjen så snart sirkulasjonen går. Avbrytes en senking, startes
ingen ny før det har gått en halvtime.

Sensoren *Nattsenking* viser `aktiv`, `planlagt`, `lonner_seg_ikke` eller `av`.
Attributtene viser vinduet, begrunnelsen, kWh og kostnad med og uten senking,
laveste temperatur og de beste alternativene den vurderte.

**Læring.** Modellen justerer seg selv:

- *COP-faktoren* læres fra målt COP (Δt × flow mot varmepumpens effekt).
- *Tapsfaktorene* læres fra rolige netter. Da går pumpen, varmepumpen står og
  sola er nede, så temperaturfallet over tre timer viser det faktiske tapet.
  Med og uten tak læres hver for seg.

Faktorene vises på sensoren *Varmetap*.

**Vanntemperatur.** Når pumpen står, måler følerne vannet som står i røret. Da
fører modellen temperaturen videre fra siste pålitelige måling. Det estimatet
brukes i beregningene og vises som `modellestimat`.

### Klortabletter

Klorloggen er også en kalender, `calendar.ki_basseng_klorlogg`, der du kan legge til og
slette tabletter. Vil du ha tablettene i Google Kalender, velger du den under Utstyr, så
skrives hver tablett dit også.

Trykk *Logg klortablett*, eller kall `ki_basseng.logg_klortablett`, når du legger
i tabletter. Skriv navnene i husstanden i *Navn i klorloggen* («Sebastian, Ida»), så kan
du huke av hvem som la i. Navnet kommer med i loggen, og tjenesten tar det som `hvem:`. Integrasjonen husker de 50 siste innslagene med tid, antall, notat
og vanntemperatur, og skriver i loggboka.

*Neste klortablett* regnes ut fra intervallet (7 dager som standard). Intervallet
blir kortere i varmt vann, fordi klor forbrukes raskere over 24 °C. Ved 32 °C er
det halvert. *Klortablett bør legges i* slår seg på når det er på tide.

### Spart i dag

*Spart i dag* er hva pumpa ville kostet i døgndrift, minus hva den faktisk kostet. I
attributtene står hva tallet består av:

- **Færre pumpetimer** og **billigere timer**. Disse to går opp i det målte tallet.
- **Nattsenkingen** og **pooltaket**, som er anslag fra varmemodellen.
- **I går**, **denne måneden** og **totalt**.

I kortet folder «Spart i dag» ut hele oppdelingen.

### Vintermodus

Slå på *Vintermodus* når sesongen er over.

- **Varmepumpa** står av.
- **Varmeelementene i bassenghuset** holder temperaturen over *Frostsikring: varme på under*
  (5 °C), med to graders slingringsmonn.
- **Pumpa** sirkulerer hele tiden når det er kaldere ute enn *Frostsikring: sirkulasjon
  under* (0 °C). Ellers filtrerer den *Omsetninger per døgn om vinteren*.

Velg føleren og elementene under Utstyr i oppsettet.

### Når den ikke varmer

Er vannet under målet uten at varmepumpa jobber, står grunnen i attributtet
`varmer_ikke_fordi` på *Pumpemodus* og i begrunnelsen. Grunnen kan være nattsenking,
varmeprioritet av, utenfor varmevinduet, eller at varmepumpa er slått av utenfor
integrasjonen. Tilstanden til varmepumpa lagres, så en omstart midt på natta ikke gjør at
den blir stående av.

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
| Utstyr | varmepumpe, innløp, utløp, utetemperatur, vannventil for spreder, værmelding, pooltak, tilstedeværelse |
| Bassenget | volum, kapasitet, vannflate, solfangerareal, basislast, varmepumpens merkeeffekt, valuta |

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
Vannflate          24.1         (7,3 × 3,3)
Kapasitet          11.3
Basislast          800
Værmelding         weather.forecast_hjem
Tilstedeværelse    person.sebastian (+ resten av husstanden)
```

Volumet spriker mellom de to pakkene dine: pumpestyringen regner 35,6 m³,
estimatpakken 40,95 m³. Det er 15 % forskjell på hvor lenge pumpen må gå per
omsetning, så det er verdt å måle opp en gang for alle.

## Entiteter

Alt havner på enheten **KI Basseng** med prefiks `ki_basseng`.

**Sensorer:** pumpemodus (med plan, blokker og snittpriser som attributter),
omsetninger i dag, pumpet volum i dag/totalt, pumpetid i dag, neste
pumpestart, pumpe- og varmepumpeeffekt, energi i dag for begge, kostnad i
dag, spart i dag, vanntemperatur, spreder gjenstår, måltemperatur,
nattsenking, nattsenking besparelse, varmetap, solinnstråling, siste og neste
klortablett.

**Binærsensorer:** pumpe skal gå, spreder kjører, manuell overstyring,
varmepumpe venter, nattsenking aktiv, klortablett bør legges i, noen hjemme.

**Brytere:** automatikk, prisstyring, varmeprioritet, styr varmepumpe, puls
med varme, spreder-program, frostvakt, smart nattsenking, styr settpunkt,
pooltak på, solvarme.

**Tall:** omsetninger per døgn, vedlikeholdspuls, minste kjøretid, manuell
overstyring varer, dagtimer i planen, varmevindu start/slutt, pumpe
basislast, spreder varighet/intervall/maks per døgn, ønsket temperatur,
senking når ingen er hjemme, maks nattsenking, varmetap med/uten tak, sol
gjennom taket, klortablett intervall.

**Valg:** driftsprofil (eco, balansert, badeklar, ferie) og hva nattsenkingen
skal spare. Profilen setter omsetningsmål og puls i ett grep, og hopper til
«egendefinert» hvis du justerer noe manuelt etterpå. Ferie regnes som at
ingen er hjemme.

**Knapper:** start og stopp spreder, boost sirkulasjon, logg klortablett,
angre siste klortablett, nullstill dagens tellere.

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

action: ki_basseng.logg_klortablett
data:
  antall: 1
  hvem: Sebastian
  notat: Flottøren

action: ki_basseng.angre_klortablett
```

## Kortet

Legg `ki-basseng-card.js` i `/config/www/` og registrer den under
**Innstillinger → Dashbord → Ressurser** som `/local/ki-basseng-card.js`.

```yaml
type: custom:ki-basseng-card
tittel: Badebasseng
faner: [oversikt, sirkulasjon, varme, spreder, innstillinger]
```

`prefix:` kan utelates — kortet finner entitetene selv. Har du flere
bassenger, oppgi prefiks for hvert kort.

Fanen *Oversikt* viser omsetningsringen, vanntemperatur, modus med
begrunnelse, døgnplanen som en 24-timers stripe med nå-markør, og fire
nøkkeltall. *Sirkulasjon* har blokkene, profilvalg, steppere for mål og
puls, og boost. *Varme* har måltemperatur, nattsenkingen med vindu og
besparelse, steppere for ønsket temperatur og senking, bryter for pooltaket og
klorloggen med én knapp. *Spreder* har nedtelling og hurtigvalg. *Innstillinger* har
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

Fra 1.3.0 eier integrasjonen også settpunktet og nattsenkingen. Fjern
nattsenkingen og alt som setter settpunktet i `basseng_estimat.yaml`, ellers
krangler de om varmepumpen. Resten av estimatpakken kan bli stående. Vil du
heller la pakken eie settpunktet, slår du av *Styr settpunkt*. Da bruker
modellen varmepumpens eget settpunkt som mål.

## Tuning

- **Pumpen går for lite.** Øk omsetningsmålet, eller bytt profil til
  badeklar. Er vannet over 27 °C, foreslår sensoren 2,5 omsetninger.
- **Planen ligger midt på natten.** Øk *Dagtimer i planen*.
- **Effektsplitten ser feil ut.** Les av `sensor.bassengpumpe_power` mens
  bare sirkulasjonspumpen går, og sett *Pumpe basislast* til den verdien.
- **Varmepumpen starter ikke igjen.** Sjekk at *Styr varmepumpe* er på og at
  pumpen har gått sammenhengende i over to minutter.
- **Nattsenkingen slår aldri til.** Se på attributtene til *Nattsenking*.
  Står det «rekker ikke å varme opp igjen», flytter du *Varmevindu start*
  senere. Står det «koster like mye som den sparer», gjør den jobben sin.
- **Modellen bommer på temperaturen.** Juster *Varmetap uten tak* og *Med tak*.
  Tapsfaktorene læres over tid, men startverdien avgjør hvor fort de treffer.
  Med bassengduk er 3–6 W/m²K typisk. Uten tak er 10–25 W/m²K typisk,
  avhengig av vind.

## Lisens

MIT.
