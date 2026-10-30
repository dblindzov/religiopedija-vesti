"""
Религиопедија — вести са блога „5 ПАСУСА“.

Чита RSS фид блога, за сваку вест узима наслов, линк, датум и прву слику,
слику смањује на 480×300 и чува у фасцикли slike/, а списак вести уписује
у vesti.js. Главна страна Религиопедије учитава vesti.js преко jsDelivr-а.

Покреће се аутоматски (GitHub Actions), сваког сата.
"""

import hashlib
import html
import io
import json
import os
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

from PIL import Image, ImageOps

FID = "https://5pasusa.blogspot.com/feeds/posts/default?alt=rss&max-results=15"
BROJ_VESTI = 8           # колико вести иде на главну страну
SIRINA, VISINA = 480, 300
FASCIKLA = "slike"
IZLAZ = "vesti.js"
ZONA = ZoneInfo("Europe/Belgrade")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")

IMG_RE = re.compile(r"<img\b[^>]*?\bsrc\s*=\s*[\"']([^\"']+)[\"']", re.I)


def preuzmi(url, referer=None, timeout=30):
    zaglavlja = {"User-Agent": UA, "Accept": "*/*"}
    if referer:
        zaglavlja["Referer"] = referer
    zahtev = urllib.request.Request(url, headers=zaglavlja)
    with urllib.request.urlopen(zahtev, timeout=timeout) as odgovor:
        return odgovor.read()


def procitaj_fid(xml_bajtovi):
    koren = ET.fromstring(xml_bajtovi)
    vesti = []
    for item in koren.iter("item"):
        naslov = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        opis = item.findtext("description") or ""
        datum = ""
        pub = item.findtext("pubDate")
        if pub:
            try:
                datum = parsedate_to_datetime(pub).astimezone(ZONA).date().isoformat()
            except (TypeError, ValueError):
                pass
        slika = None
        nadjena = IMG_RE.search(opis)
        if nadjena:
            slika = html.unescape(nadjena.group(1)).strip()
            if slika.startswith("//"):
                slika = "https:" + slika
        if naslov and link.startswith("https://5pasusa.blogspot.com/"):
            vesti.append({"naslov": naslov, "link": link,
                          "datum": datum, "izvor_slike": slika})
    return vesti


def sacuvaj_sliku(url, referer):
    """Враћа релативну путању до сачуване сличице или None."""
    ime = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16] + ".jpg"
    putanja = os.path.join(FASCIKLA, ime)
    if os.path.exists(putanja):
        return f"{FASCIKLA}/{ime}"
    try:
        podaci = preuzmi(url, referer=referer)
        with Image.open(io.BytesIO(podaci)) as slika:
            slika = ImageOps.exif_transpose(slika)
            if slika.mode not in ("RGB", "L"):
                pozadina = Image.new("RGB", slika.size, (255, 255, 255))
                rgba = slika.convert("RGBA")
                pozadina.paste(rgba, mask=rgba.split()[3])
                slika = pozadina
            slika = ImageOps.fit(slika.convert("RGB"), (SIRINA, VISINA),
                                 method=Image.LANCZOS, centering=(0.5, 0.4))
            os.makedirs(FASCIKLA, exist_ok=True)
            slika.save(putanja, "JPEG", quality=78, optimize=True,
                       progressive=True)
        return f"{FASCIKLA}/{ime}"
    except Exception as greska:  # слика није кључна — вест иде и без ње
        print(f"  слика није преузета ({url}): {greska}", file=sys.stderr)
        return None


def main():
    try:
        vesti = procitaj_fid(preuzmi(FID))
    except Exception as greska:
        print(f"Фид није прочитан, ништа се не мења: {greska}", file=sys.stderr)
        return 0
    if not vesti:
        print("Фид је празан, ништа се не мења.", file=sys.stderr)
        return 0

    izabrane = []
    for v in vesti[:BROJ_VESTI]:
        print(f"• {v['naslov']}")
        slika = sacuvaj_sliku(v["izvor_slike"], v["link"]) if v["izvor_slike"] else None
        izabrane.append({"naslov": v["naslov"], "link": v["link"],
                         "datum": v["datum"], "slika": slika})

    # бришу се сличице које више нису у употреби
    u_upotrebi = {os.path.basename(v["slika"]) for v in izabrane if v["slika"]}
    if os.path.isdir(FASCIKLA):
        for ime in os.listdir(FASCIKLA):
            if ime.endswith(".jpg") and ime not in u_upotrebi:
                os.remove(os.path.join(FASCIKLA, ime))

    sadrzaj = ("/* Аутоматски направљено — не мењати ручно. */\n"
               "window.rpVesti && window.rpVesti("
               + json.dumps({"vesti": izabrane}, ensure_ascii=False, indent=1)
               + ");\n")
    stari = ""
    if os.path.exists(IZLAZ):
        with open(IZLAZ, encoding="utf-8") as f:
            stari = f.read()
    if sadrzaj != stari:
        with open(IZLAZ, "w", encoding="utf-8") as f:
            f.write(sadrzaj)
        print("vesti.js је ажуриран.")
    else:
        print("Нема нових вести.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
