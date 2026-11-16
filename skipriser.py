#!/usr/bin/env python3
"""Daglig prissjekk av langrennssko (klassisk, kombi, skøyte) og langrennsstaver i norske nettbutikker.

Kjør:  python skipriser.py            (henter priser, oppdaterer data/priser.json,
                                       skriver RAPPORT.md og ev. varsel.md)
       python skipriser.py --prove    (henter og skriver rapport, men lagrer ikke historikk)

Bare standardbiblioteket brukes. Innstillinger ligger i config.json.
"""
import datetime
import json
import math
import os
import re
import sys
import time
import urllib.parse
import urllib.request

HER = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HER, "config.json")
DATA = os.path.join(HER, "data", "priser.json")
RAPPORT = os.path.join(HER, "RAPPORT.md")
VARSEL = os.path.join(HER, "varsel.md")

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126.0 Safari/537.36")
PAUSE = 1.5  # sekunder mellom hvert oppslag, for ikke å belaste butikkene
JSON = json.JSONDecoder()


# ---------------------------------------------------------------- henting

def hent(url, forsok=3):
    feil = None
    for i in range(forsok):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": UA,
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "nb-NO,nb;q=0.9",
            })
            with urllib.request.urlopen(req, timeout=45) as r:
                tekst = r.read().decode("utf-8", errors="replace")
            time.sleep(PAUSE)
            return tekst
        except Exception as e:  # nettverksfeil, 4xx/5xx
            feil = e
            time.sleep(3 * (i + 1))
    raise RuntimeError(f"Klarte ikke å hente {url}: {feil}")


def med_query(url, par):
    """Legg til query-parametre (liste av (navn, verdi))."""
    if not par:
        return url
    skille = "&" if "?" in url else "?"
    return url + skille + urllib.parse.urlencode(par)


# ---------------------------------------------------------------- størrelser

def lengde_omraade(etikett):
    """'160' -> (160,160), '1575' -> (157.5,157.5), '156-160cm' -> (156,160)."""
    s = etikett.lower().replace(",", ".").replace("cm", "").strip()
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)", s)
    if m:
        return float(m.group(1)), float(m.group(2))
    m = re.fullmatch(r"0*(\d+(?:\.\d+)?)", s)
    if m:
        v = float(m.group(1))
        if v >= 1000:
            v /= 10
        return v, v
    return None


def velg_storrelser(etiketter, kilde, profil):
    """Plukk de størrelsesvalgene i butikkens filter som passer brukeren."""
    ut = []
    for e in etiketter:
        if kilde["type"] == "sko":
            if any(e.strip() == s or e.strip().startswith(s + " ") for s in profil["skostorrelse"]):
                ut.append(e)
        else:
            omr = lengde_omraade(e)
            if omr and 100 <= omr[1] <= 200 and any(omr[0] <= l <= omr[1] for l in profil["stavlengder_cm"]):
                ut.append(e)
    return ut


# ---------------------------------------------------------------- butikkene

def flight(html):
    """Slå sammen dataene Next.js legger i siden (self.__next_f.push)."""
    biter = re.findall(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)', html)
    return "".join(json.loads(b) for b in biter)


def xxl(kilde, profil):
    def liste(url):
        html = hent(url)
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
        return json.loads(m.group(1))["props"]["pageProps"]["productListData"]

    forste = liste(kilde["url"])
    valg = []
    for f in forste.get("facets", []):
        if f.get("id") == "variant.custom.sizeLabel":
            valg = velg_storrelser([v["id"] for v in f.get("values", [])], kilde, profil)
    filter_par = [("f.variant.custom.sizeLabel", v) for v in valg]
    produkter, side = [], 1
    while True:
        d = forste if (side == 1 and not valg) else liste(med_query(kilde["url"], filter_par + [("pages", side)]))
        produkter += d["products"]
        if not d["products"] or len(produkter) >= d["totalHits"] or side >= 10:
            break
        side += 1

    ut = []
    for p in produkter:
        usp = {u["name"]: u["value"] for u in p.get("usps", [])}
        pris = p["price"]["selling"]["value"]
        alt = (p["price"].get("alternate") or {}).get("value")
        ut.append({
            "id": p["code"],
            "merke": p.get("brandName") or "",
            "navn": p["name"],
            "pris": pris,
            "forpris": alt if alt and alt > pris else None,
            "url": "https://www.xxl.no" + p["url"],
            "farge": p.get("localizedColorName") or "",
            "bruk": usp.get("Bruksområde", ""),
            "system": usp.get("Støvelsystem", ""),
            "bruker": usp.get("Bruker", ""),
            "str_sjekket": bool(valg),
            "paa_lager": p.get("isInStockOnline", True),
        })
    return ut


def sportholding(kilde, profil):
    """Sport 1 og Intersport (samme plattform)."""
    rot = re.match(r"https://[^/]+", kilde["url"]).group(0)

    def les(url):
        t = flight(hent(url))
        prod = []
        for m in re.finditer(r'"product":\{', t):
            p, _ = JSON.raw_decode(t, m.end() - 1)
            if "price" in p and "href" in p:
                prod.append(p)
        fasetter = []
        m = re.search(r'"facets":\[', t)
        if m:
            fasetter, _ = JSON.raw_decode(t, m.end() - 1)
        return prod, fasetter

    _, fasetter = les(kilde["url"])
    valg = []
    for f in fasetter:
        if f.get("name") == "Size":
            valg = velg_storrelser([i["item"] for i in f.get("items", [])], kilde, profil)
    # page=N gir de N*15 første produktene, så én stor side gir alt.
    produkter, _ = les(med_query(kilde["url"], [("page", 20)] + [("Size", v) for v in valg]))

    ut = []
    for p in produkter:
        pr = p["price"]
        pris, orig = pr["unitPrice"], pr.get("originalUnitPrice")
        ut.append({
            "id": p["id"],
            "merke": (p.get("brand") or "").title(),
            "navn": p["name"].title() if p["name"].isupper() else p["name"],
            "pris": pris,
            "forpris": orig if orig and orig > pris else None,
            "veil": pr.get("recommendedRetailPrice"),
            "medlem": bool(pr.get("isCustomerClubSpecificPrice")),
            "url": rot + p["href"],
            "farge": "",
            "kategori": " > ".join(c["name"] for c in p.get("categories", [])),
            "str_sjekket": bool(valg),
        })
    return ut


def milslukern(kilde, profil):
    """Milslukern: siden viser bare de 25 første produktene i kategorien."""
    rot = re.match(r"https://[^/]+", kilde["url"]).group(0)
    t = flight(hent(kilde["url"]))
    ut, sett = [], set()
    for m in re.finditer(r'"queryData":\[', t):
        liste, _ = JSON.raw_decode(t, m.end() - 1)
        for p in liste:
            if not isinstance(p, dict) or "price" not in p or p.get("id") in sett:
                continue
            sett.add(p["id"])
            pr = p["price"]
            pris, normal = pr["current"], pr.get("normal")
            farger = sorted({c["publicName"] for v in p.get("variants", []) for c in (v.get("colors") or [])})
            ut.append({
                "id": str(p["id"]),
                "merke": (p.get("brand") or {}).get("name", ""),
                "navn": p["name"].strip(),
                "pris": pris,
                "forpris": normal if normal and normal > pris else None,
                "url": p.get("url") or rot + p["path"],
                "farge": "/".join(farger),
                "tagger": " ".join(p.get("tags", [])),
                "kjonn": p.get("gender") or "",
                "str_sjekket": False,
            })
    return ut


def fjellsport(kilde, profil):
    def les(url):
        html = hent(url)
        m = re.search(r"INITIAL_DATA = JSON\.parse\('(.*?)(?<!\\)'\);", html, re.S)

        def av(m):
            c = m.group(1)
            if c[0] == "x":
                return chr(int(c[1:], 16))
            return c if c in "'\\" else m.group(0)
        return json.loads(re.sub(r"\\(x[0-9a-fA-F]{2}|.)", av, m.group(1), flags=re.S))["page"]

    produkter, side, sider = [], 1, 1
    while side <= min(sider, 10):
        d = les(med_query(kilde["url"], [("page", side)] if side > 1 else []))
        produkter += d.get("products", [])
        sider = (d.get("pagination") or {}).get("pageCount", 1)
        side += 1

    ut = []
    for p in produkter:
        pris = p["price"]["current"]["inclVat"]
        vanlig = (p["price"].get("regular") or {}).get("inclVat")
        ut.append({
            "id": p.get("productKey") or p.get("sku") or p["url"],
            "merke": p.get("brand") or "",
            "navn": p.get("partialProductName") or p["displayName"],
            "pris": pris,
            "forpris": vanlig if vanlig and vanlig > pris else None,
            "url": "https://www.fjellsport.no" + p["url"],
            "farge": "",
            "kjonn": p.get("gender") or "",
            "str_sjekket": False,
        })
    return ut


PARSERE = {"xxl": xxl, "sportholding": sportholding, "milslukern": milslukern, "fjellsport": fjellsport}


# ---------------------------------------------------------------- filtrering

def har_ord(tekst, ordliste):
    """Ord må stå alene. 'skøyt*' treffer også 'skøytestøvel'."""
    for o in ordliste:
        stamme = o.rstrip("*")
        slutt = "" if o.endswith("*") else r"(?![a-zæøå0-9])"
        if re.search(r"(?<![a-zæøå0-9])" + re.escape(stamme.lower()) + slutt, tekst):
            return o
    return None


def passer(p, kilde, cfg):
    regler = cfg["filter"][kilde["type"]]
    sti = urllib.parse.urlparse(p["url"]).path  # ikke domenet: «fjell*» skal ikke treffe fjellsport.no
    tekst = " ".join([sti] + [str(p.get(k, "")) for k in ("merke", "navn", "kategori", "kjonn", "bruker")]).lower()
    if har_ord(tekst, regler["utelat"]):
        return False
    if p["pris"] < regler.get("min_pris", 0):
        return False
    if kilde["type"] == "sko":
        if p.get("system") and not har_ord(p["system"].lower(), ["nnn", "prolink", "turnamic"]):
            return False
        p["undertype"] = skotype(p, tekst, regler["typeord"])
        if p["undertype"] not in regler["vis_typer"]:
            return False
    return True


def skotype(p, tekst, typeord):
    """klassisk, skøyte eller kombi – ut fra navn, butikkens tagger og bruksområde."""
    bredt = f'{tekst} {p.get("tagger", "")} {p.get("bruk", "")}'.lower()
    skoyte = bool(har_ord(bredt, typeord["skøyte"]))
    klassisk = bool(har_ord(bredt, typeord["klassisk"]))
    if har_ord(bredt, typeord["kombi"]) or (skoyte and klassisk):
        return "kombi"
    return "skøyte" if skoyte else "klassisk"


def matcher_skiene(p, cfg):
    tekst = f'{p.get("merke", "")} {p.get("navn", "")} {p.get("farge", "")} {urllib.parse.urlparse(p["url"]).path}'.lower()
    return bool(har_ord(tekst, cfg["matcher_skiene"]["merker"]) or har_ord(tekst, cfg["matcher_skiene"]["farger"]))


# ---------------------------------------------------------------- rapport

def kr(v):
    return "" if v is None else f"{v:,.0f} kr".replace(",", " ")


def rabatt(p):
    return round((1 - p["pris"] / p["forpris"]) * 100) if p.get("forpris") else 0


def rad(p, ekstra=""):
    navn = f'{p["merke"]} {p["navn"]}'.strip().replace("|", "/")
    merknad = []
    if p.get("medlem"):
        merknad.append("medlemspris")
    if not p.get("str_sjekket"):
        merknad.append("sjekk størrelse selv")
    if p.get("paa_lager") is False:
        merknad.append("ikke på nettlager")
    if p.get("farge"):
        merknad.append(p["farge"])
    if ekstra:
        merknad.insert(0, ekstra)
    r = rabatt(p)
    return (f'| {"★" if p.get("match") else ""} | [{navn}]({p["url"]}) | {p.get("undertype") or "stav"} | {p["butikk"]} | **{kr(p["pris"])}** | '
            f'{kr(p.get("forpris"))} | {f"−{r} %" if r else ""} | {kr(p.get("laveste"))} | {", ".join(merknad)} |')


HODE = ("| ★ | Produkt | Type | Butikk | Pris nå | Førpris | Rabatt | Laveste sett | Merknad |\n"
        "|---|---|---|---|---|---|---|---|---|")


def tabell(rader):
    return HODE + "\n" + "\n".join(rader) if rader else "_Ingen._"


def main():
    prove = "--prove" in sys.argv
    cfg = json.load(open(CONFIG, encoding="utf-8"))
    profil, v = cfg["profil"], cfg["varsel"]
    i_dag = datetime.date.today().isoformat()
    tilstand = json.load(open(DATA, encoding="utf-8")) if os.path.exists(DATA) else {}
    forste_gang = not tilstand

    funnet, feil = {}, []
    for kilde in cfg["kilder"]:
        merkelapp = f'{kilde["butikk"]} ({kilde["type"]})'
        try:
            alle = PARSERE[kilde["parser"]](kilde, profil)
            if not alle:
                raise RuntimeError("fant ingen produkter – siden kan ha endret seg")
            ok = [p for p in alle if passer(p, kilde, cfg)]
            print(f"{merkelapp}: {len(alle)} hentet, {len(ok)} aktuelle")
            for p in ok:
                p.update(butikk=kilde["butikk"], type=kilde["type"], match=matcher_skiene(p, cfg))
                funnet[f'{kilde["butikk"]}:{p["id"]}'] = p
        except Exception as e:
            feil.append(f"{merkelapp}: {e}")
            print(f"FEIL {merkelapp}: {e}")

    endringer = []  # (tekst, produkt)
    for nokkel, p in funnet.items():
        gammel = tilstand.get(nokkel)
        if gammel:
            fall = gammel["pris"] - p["pris"]
            if fall >= v["min_prisfall_kr"] or (fall > 0 and fall / gammel["pris"] * 100 >= v["min_prisfall_prosent"]):
                endringer.append((f'ned fra {kr(gammel["pris"])}', p))
            historikk = gammel.get("historikk", [])
            laveste, laveste_dato = gammel.get("laveste", gammel["pris"]), gammel.get("laveste_dato", gammel.get("forste_sett"))
            forste_sett = gammel.get("forste_sett", i_dag)
        else:
            if not forste_gang and rabatt(p) >= v["min_rabatt_prosent_nytt_produkt"]:
                endringer.append(("nytt tilbud", p))
            historikk, laveste, laveste_dato, forste_sett = [], p["pris"], i_dag, i_dag
        if not historikk or historikk[-1][1] != p["pris"]:
            historikk.append([i_dag, p["pris"]])
        if p["pris"] < laveste:
            laveste, laveste_dato = p["pris"], i_dag
        p.update(laveste=laveste, laveste_dato=laveste_dato)
        tilstand[nokkel] = {
            "butikk": p["butikk"], "type": p["type"], "undertype": p.get("undertype"), "merke": p["merke"], "navn": p["navn"], "url": p["url"],
            "pris": p["pris"], "forpris": p.get("forpris"), "laveste": laveste, "laveste_dato": laveste_dato,
            "forste_sett": forste_sett, "sist_sett": i_dag, "historikk": historikk[-400:],
        }

    def sortert(type_, bare_tilbud):
        ps = [p for p in funnet.values() if p["type"] == type_ and (rabatt(p) > 0) == bare_tilbud]
        # Tilbud: størst rabatt først. Ordinær pris: gruppert på type, billigst først.
        return sorted(ps, key=(lambda p: (-rabatt(p), p["pris"])) if bare_tilbud
                      else (lambda p: (p.get("undertype", ""), p["pris"])))

    navn = {"sko": f'Skisko, str. {"/".join(profil["skostorrelse"])}',
            "staver": f'Staver, {" / ".join(str(l).replace(".", ",") for l in profil["stavlengder_cm"])} cm'}
    linjer = [f"# Skipriser {i_dag}", "",
              f'{len(funnet)} aktuelle produkter funnet. ★ = passer til skiene ({cfg["matcher_skiene"]["beskrivelse"]}).', ""]
    if feil:
        linjer += ["**Butikker som feilet i dag:**", ""] + [f"- {f}" for f in feil] + [""]
    linjer += ["## Endringer siden sist", "",
               "_Første kjøring – ingen historikk å sammenligne med ennå._" if forste_gang
               else tabell([rad(p, t) for t, p in sorted(endringer, key=lambda e: -rabatt(e[1]))]), ""]
    for type_ in ("sko", "staver"):
        linjer += [f"## {navn[type_]} – på tilbud nå", "", tabell([rad(p) for p in sortert(type_, True)]), "",
                   f"## {navn[type_]} – ordinær pris", "", tabell([rad(p) for p in sortert(type_, False)]), ""]
    linjer += ["---", "«Førpris» er butikkens egen førpris og er ikke kontrollert. «Laveste sett» er laveste pris "
               "dette skriptet har registrert. Størrelse er sjekket mot butikkens filter der det går an; "
               "lagerstatus må sjekkes i butikken."]
    open(RAPPORT, "w", encoding="utf-8").write("\n".join(linjer) + "\n")

    # Varsel: bare når noe faktisk har skjedd (eller første kjøring, som en startoversikt).
    if os.path.exists(VARSEL):
        os.remove(VARSEL)
    if endringer or forste_gang:
        if forste_gang:
            tittel = f"Skipriser: startoversikt {i_dag}"
            kropp = ["Prissjekken er i gang. Dette er de beste tilbudene akkurat nå:", ""]
            for type_ in ("sko", "staver"):
                kropp += [f"### {navn[type_]}", "", tabell([rad(p) for p in sortert(type_, True)[:8]]), ""]
        else:
            tittel = f"Skipriser: {len(endringer)} prisfall/tilbud {i_dag}"
            kropp = [tabell([rad(p, t) for t, p in sorted(endringer, key=lambda e: -rabatt(e[1]))]), ""]
        kropp += ["Hele oversikten ligger i RAPPORT.md i repoet."]
        open(VARSEL, "w", encoding="utf-8").write(tittel + "\n\n" + "\n".join(kropp) + "\n")

    if not prove:
        os.makedirs(os.path.dirname(DATA), exist_ok=True)
        json.dump(tilstand, open(DATA, "w", encoding="utf-8"), ensure_ascii=False, indent=1, sort_keys=True)
    print(f"Ferdig: {len(funnet)} produkter, {len(endringer)} endringer, {len(feil)} feil.")
    # Feiler alle kildene, skal kjøringen bli rød så det synes.
    return 1 if feil and not funnet else 0


if __name__ == "__main__":
    sys.exit(main())
