# Skipriser

Sjekker hver dag prisen på **langrennssko (str. 45)** og **langrennsstaver (157,5/160 cm)**
i norske nettbutikker, til skiene Atomic Redster C2 Skin 202 cm (rød/svart).

- **Se prisene:** åpne [RAPPORT.md](RAPPORT.md). Den oppdateres hver morgen.
- **Varsel:** når noe går ned i pris, eller det dukker opp et nytt tilbud, opprettes en sak
  under «Issues». GitHub sender den på e-post til eieren av repoet.
- **★** betyr at produktet passer til skiene (Atomic, eller rødt).

## Butikker

| Butikk | Størrelse sjekket | Merknad |
|---|---|---|
| XXL | ja | |
| Sport 1 | ja | medlemspriser er merket |
| Intersport | ja | medlemspriser er merket |
| Fjellsport | nei | sjekk størrelse i butikken |
| Milslukern | nei | bare de 25 første produktene i hver kategori |

Anton Sport og Oslo Sportslager slipper ikke skript inn, og er derfor ikke med.

## Endre innstillinger

Alt står i `config.json`:

- `profil`: skostørrelse og stavlengder.
- `filter.sko.vis_typer`: hvilke skotyper som vises (klassisk, kombi, skøyte). Kolonnen «Type» i rapporten
  settes ut fra ordene i `typeord`.
- `varsel`: hvor stort prisfall som skal gi varsel (kr og prosent), og hvor stor rabatt et
  nytt produkt må ha.
- `filter`: ord som utelukker produkter (skøytesko, junior, stropper osv.). `skøyt*` treffer
  alle ord som begynner på «skøyt».
- `matcher_skiene`: merker og farger som gir ★.
- `kilder`: kategorisidene som leses.

## Kjøre selv

```
python skipriser.py           # henter priser og lagrer historikk i data/priser.json
python skipriser.py --prove   # skriver bare RAPPORT.md, lagrer ikke historikk
```

Trenger bare Python 3, ingen ekstra pakker. Skriptet leser de vanlige, åpne kategorisidene,
med halvannet sekunds pause mellom hvert oppslag (ca. 25 oppslag per dag).

## Verdt å vite

- «Førpris» er butikkens egen og er ikke kontrollert. «Laveste sett» er laveste pris skriptet
  selv har registrert, og blir nyttig etter noen uker.
- Bygger en butikk om nettsiden sin, slutter den butikken å virke. Da står den under
  «Butikker som feilet i dag» øverst i rapporten.
- Bindingen må være NNN, Prolink eller Turnamic (de passer om hverandre). SNS-sko er filtrert bort.
