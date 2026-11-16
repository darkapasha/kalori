"""SalimBabanınZayıflamaUygulaması — sunucu.

Tek kullanıcılı. Telefon (ve masaüstü kartı) gizli anahtarla eşlenir; her API
isteği X-Anahtar başlığıyla gelir. PWA dosyaları da buradan sunulur.

- /api/esitle   kayıtları birleştirir (her öğe için en son değişen kazanır)
- /api/tahmin   yazılan yemeğin kalorisi (önbellek → Gemini)
- /api/foto     tabak fotoğrafından tahmin (Gemini)
- /api/barkod   Open Food Facts'ten paketli ürün
- /api/oneri    "kalanla ne yiyebilirim"
- /api/push/*   bildirim aboneliği; akşam ve tartılma hatırlatmaları
"""
import base64
import json
import os
import re
import secrets
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

SURUM = "1.0"
KOK = Path(__file__).resolve().parent
WEB = KOK / "web"
VERI = KOK / "veri"
VERI.mkdir(exist_ok=True)
TZ = ZoneInfo("Europe/Istanbul")
KILIT = threading.Lock()


def _gizli(ad: str, uret) -> str:
    yol = VERI / ad
    if not yol.exists():
        yol.write_text(uret())
        os.chmod(yol, 0o600)
    return yol.read_text().strip()


ANAHTAR = _gizli("anahtar.txt", lambda: secrets.token_urlsafe(32))


def _env(ad: str, varsayilan: str = "") -> str:
    yol = VERI / ".env"
    if yol.exists():
        for satir in yol.read_text().splitlines():
            if satir.startswith(ad + "="):
                return satir.split("=", 1)[1].strip().strip('"')
    return os.getenv(ad, varsayilan)


GEMINI_KEY = _env("GEMINI_API_KEY")
# Lite ~1 sn yanıt veriyor; büyük model yoğunlukta 503/zaman aşımı verebildiği için yedek
MODELLER = [("gemini-flash-lite-latest", None), ("gemini-flash-latest", {"thinkingLevel": "low"})]

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


def _dogru(k: str | None) -> bool:
    return bool(k) and secrets.compare_digest(k, ANAHTAR)


def kontrol(k: str | None) -> None:
    if not _dogru(k):
        time.sleep(1)
        raise HTTPException(status_code=401, detail="anahtar yanlış")


def json_oku(ad: str, varsayilan):
    try:
        return json.loads((VERI / ad).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return varsayilan


def json_yaz(ad: str, veri) -> None:
    gecici = VERI / (ad + ".yeni")
    gecici.write_text(json.dumps(veri, ensure_ascii=False), encoding="utf-8")
    os.replace(gecici, VERI / ad)


# --- Eşitleme ---------------------------------------------------------------
# Veri: {kayit:{id:öğe}, kilo:{..}, su:{..}, fav:{..}, ayar:{..}}
# Her öğede "d" (değişme zamanı, ms) var; büyük olan kazanır. Silinen öğe
# "silindi": true ile iz bırakır ki öbür cihaz da silsin.
KOLEKSIYONLAR = ("kayit", "kilo", "su", "fav")
EN_FAZLA_GOVDE = 2_000_000


def veri_oku() -> dict:
    v = json_oku("veri.json", {})
    for k in KOLEKSIYONLAR:
        v.setdefault(k, {})
    v.setdefault("ayar", {})
    return v


def _temiz(o) -> dict | None:
    if not isinstance(o, dict) or not isinstance(o.get("id"), str) or not 0 < len(o["id"]) <= 60:
        return None
    try:
        o["d"] = int(o.get("d", 0))
    except (TypeError, ValueError):
        return None
    # metin alanlarını kırp
    for a, deger in list(o.items()):
        if isinstance(deger, str):
            o[a] = deger[:300]
        elif not isinstance(deger, (int, float, bool)) and deger is not None:
            o.pop(a)
    return o


def birlestir(gelen: dict) -> dict:
    with KILIT:
        v = veri_oku()
        for k in KOLEKSIYONLAR:
            for ham in (gelen.get(k) or {}).values() if isinstance(gelen.get(k), dict) else []:
                o = _temiz(ham)
                if o and (o["id"] not in v[k] or o["d"] > v[k][o["id"]].get("d", 0)):
                    v[k][o["id"]] = o
        ayar = gelen.get("ayar")
        if isinstance(ayar, dict) and int(ayar.get("d", 0) or 0) > int(v["ayar"].get("d", 0) or 0):
            v["ayar"] = {a: d for a, d in ayar.items() if isinstance(d, (int, float, str, bool)) or d is None}
        # 60 günden eski silme izlerini at
        sinir = (time.time() - 60 * 86400) * 1000
        for k in KOLEKSIYONLAR:
            v[k] = {i: o for i, o in v[k].items() if not (o.get("silindi") and o["d"] < sinir)}
        json_yaz("veri.json", v)
        return v


@app.get("/api/durum")
def durum(x_anahtar: str | None = Header(default=None)):
    kontrol(x_anahtar)
    return {"ok": True, "surum": SURUM, "ai": bool(GEMINI_KEY)}


@app.get("/api/veri")
def veri_al(x_anahtar: str | None = Header(default=None)):
    kontrol(x_anahtar)
    return veri_oku()


@app.post("/api/esitle")
async def esitle(istek: Request, x_anahtar: str | None = Header(default=None)):
    kontrol(x_anahtar)
    govde = await istek.body()
    if len(govde) > EN_FAZLA_GOVDE:
        raise HTTPException(413)
    try:
        gelen = json.loads(govde)
        assert isinstance(gelen, dict)
    except (ValueError, AssertionError):
        raise HTTPException(400, "biçim")
    return birlestir(gelen)


# --- Eşleme kodu --------------------------------------------------------------
# iPhone'da ana ekran uygulaması Safari'den ayrı depolama kullanır. Eşlenmiş
# cihaz 6 haneli, 10 dakikalık bir kod alır; yeni cihaz kodu girip anahtarı alır.
_kod = {"kod": None, "son": 0.0, "deneme": 0}


@app.post("/api/kod")
def kod_al(x_anahtar: str | None = Header(default=None)):
    kontrol(x_anahtar)
    _kod.update(kod=f"{secrets.randbelow(10**6):06d}", son=time.time() + 600, deneme=0)
    return {"kod": _kod["kod"]}


class KodIstek(BaseModel):
    kod: str


@app.post("/api/kod/kullan")
def kod_kullan(istek: KodIstek):
    time.sleep(0.5)
    if not _kod["kod"] or time.time() > _kod["son"] or _kod["deneme"] >= 8:
        raise HTTPException(400, "kod yok ya da süresi geçti")
    _kod["deneme"] += 1
    if secrets.compare_digest(istek.kod.strip(), _kod["kod"]):
        _kod["kod"] = None
        return {"anahtar": ANAHTAR}
    raise HTTPException(400, "kod yanlış")


# --- Gemini ---------------------------------------------------------------------
TALIMAT = (
    "Sen Türkiye'de yaşayan biri için kalori hesaplayan bir beslenme uzmanısın. "
    "Kullanıcının yediği şeyi tek tek kalemlere ayır. Miktar yazılmamışsa Türkiye'deki "
    "olağan tek porsiyonu varsay (ev yemeği tabağı, restoran porsiyonu, 1 dilim, 1 adet). "
    "Türkçe karakterleri (ç, ğ, ı, ö, ş, ü) doğru kullan. Gerçekçi ol, düşük tahmin etme; yağ ve sos genelde unutulur, hesaba kat. "
    "Yanıtı yalnızca JSON ver: {\"kalemler\":[{\"ad\":\"kısa Türkçe ad\",\"miktar\":\"ör. 1 porsiyon (300 g)\","
    "\"gram\":sayı,\"kcal\":sayı,\"protein\":gram,\"karb\":gram,\"yag\":gram}],\"not\":\"varsa kısa uyarı, yoksa boş\"}"
)

SEMA = {
    "type": "OBJECT",
    "properties": {
        "kalemler": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "ad": {"type": "STRING"}, "miktar": {"type": "STRING"}, "gram": {"type": "NUMBER"},
                    "kcal": {"type": "NUMBER"}, "protein": {"type": "NUMBER"},
                    "karb": {"type": "NUMBER"}, "yag": {"type": "NUMBER"},
                },
                "required": ["ad", "miktar", "kcal", "protein", "karb", "yag"],
            },
        },
        "not": {"type": "STRING"},
    },
    "required": ["kalemler"],
}


def gemini(parcalar: list, sema: dict | None = SEMA, sicaklik: float = 0.2) -> dict:
    if not GEMINI_KEY:
        raise HTTPException(503, "yapay zeka anahtarı yok")
    son_hata = "bilinmiyor"
    for model, dusunme in MODELLER:
        gen = {"temperature": sicaklik, "responseMimeType": "application/json"}
        if sema:
            gen["responseSchema"] = sema
        if dusunme:
            gen["thinkingConfig"] = dusunme
        govde = json.dumps({"contents": [{"role": "user", "parts": parcalar}], "generationConfig": gen}).encode()
        for deneme in range(2):
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            ist = urllib.request.Request(url, data=govde, headers={
                "Content-Type": "application/json", "x-goog-api-key": GEMINI_KEY})
            bas = time.time()
            try:
                with urllib.request.urlopen(ist, timeout=12 if deneme == 0 else 20) as y:
                    cevap = json.loads(y.read())
                metin = cevap["candidates"][0]["content"]["parts"][0]["text"]
                print(f"gemini {model} {time.time() - bas:.1f}s", flush=True)
                return json.loads(metin)
            except urllib.error.HTTPError as e:
                son_hata = f"{model} HTTP {e.code}"
                print(f"gemini {son_hata} {time.time() - bas:.1f}s {e.read()[:200]!r}", flush=True)
                if e.code in (400, 403, 404, 429):
                    break
            except (urllib.error.URLError, TimeoutError, KeyError, IndexError, ValueError) as e:
                son_hata = f"{model} {type(e).__name__}"
                print(f"gemini {son_hata} {time.time() - bas:.1f}s", flush=True)
    raise HTTPException(502, f"yapay zeka yanıt vermedi ({son_hata})")


def _sayi(x) -> float:
    try:
        return max(0.0, round(float(x), 1))
    except (TypeError, ValueError):
        return 0.0


def kalem_temizle(sonuc: dict) -> dict:
    kalemler = []
    for k in (sonuc.get("kalemler") or [])[:15]:
        if not isinstance(k, dict) or not k.get("ad"):
            continue
        kalemler.append({
            "ad": str(k["ad"])[:80], "miktar": str(k.get("miktar", ""))[:60],
            "kcal": round(_sayi(k.get("kcal"))), "protein": _sayi(k.get("protein")),
            "karb": _sayi(k.get("karb")), "yag": _sayi(k.get("yag")),
        })
    return {"kalemler": kalemler, "not": str(sonuc.get("not") or "")[:200]}


def normal(metin: str) -> str:
    m = unicodedata.normalize("NFKC", metin).replace("I", "ı").replace("İ", "i").lower()
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s,.]", " ", m)).strip()


class MetinIstek(BaseModel):
    metin: str


@app.post("/api/tahmin")
def tahmin(istek: MetinIstek, x_anahtar: str | None = Header(default=None)):
    kontrol(x_anahtar)
    metin = istek.metin.strip()[:400]
    if not metin:
        raise HTTPException(400, "boş")
    anahtar = normal(metin)
    with KILIT:
        onbellek = json_oku("onbellek.json", {})
    if anahtar in onbellek:
        return {**onbellek[anahtar], "kaynak": "önbellek"}
    sonuc = kalem_temizle(gemini([{"text": TALIMAT + "\n\nYenen: " + metin}]))
    if sonuc["kalemler"]:
        with KILIT:
            onbellek = json_oku("onbellek.json", {})
            onbellek[anahtar] = sonuc
            if len(onbellek) > 3000:
                onbellek = dict(list(onbellek.items())[-2500:])
            json_yaz("onbellek.json", onbellek)
    return {**sonuc, "kaynak": "yapay zeka"}


class FotoIstek(BaseModel):
    resim: str          # base64 JPEG
    aciklama: str = ""


@app.post("/api/foto")
def foto(istek: FotoIstek, x_anahtar: str | None = Header(default=None)):
    kontrol(x_anahtar)
    veri = istek.resim.split(",", 1)[-1]
    if len(veri) > 6_000_000:
        raise HTTPException(413, "resim çok büyük")
    try:
        base64.b64decode(veri[:100] + "==", validate=False)
    except ValueError:
        raise HTTPException(400, "resim bozuk")
    ek = f"\nKullanıcının notu: {istek.aciklama[:200]}" if istek.aciklama.strip() else ""
    istem = TALIMAT + "\n\nFotoğraftaki tabakta/masada kullanıcının yiyeceği şeyleri tanı, " \
        "porsiyonu tabağın boyutundan tahmin et." + ek
    sonuc = gemini([{"inline_data": {"mime_type": "image/jpeg", "data": veri}}, {"text": istem}])
    return {**kalem_temizle(sonuc), "kaynak": "fotoğraf"}


@app.get("/api/barkod/{kod}")
def barkod(kod: str, x_anahtar: str | None = Header(default=None)):
    kontrol(x_anahtar)
    if not re.fullmatch(r"\d{6,14}", kod):
        raise HTTPException(400, "barkod")
    with KILIT:
        onbellek = json_oku("barkod.json", {})
    if kod in onbellek:
        return onbellek[kod]
    alanlar = "product_name,product_name_tr,brands,quantity,serving_size,serving_quantity,nutriments"
    url = f"https://world.openfoodfacts.org/api/v2/product/{kod}.json?fields={alanlar}"
    ist = urllib.request.Request(url, headers={"User-Agent": "KaloriPWA/1.0 (kisisel kullanim)"})
    try:
        with urllib.request.urlopen(ist, timeout=15) as y:
            cevap = json.loads(y.read())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            raise HTTPException(404, "ürün bulunamadı")
        raise HTTPException(502, "Open Food Facts yanıt vermedi")
    except (urllib.error.URLError, TimeoutError, ValueError):
        raise HTTPException(502, "Open Food Facts yanıt vermedi")
    u = cevap.get("product")
    if cevap.get("status") != 1 or not u:
        raise HTTPException(404, "ürün bulunamadı")
    n = u.get("nutriments") or {}
    kcal100 = n.get("energy-kcal_100g")
    if kcal100 is None and n.get("energy_100g") is not None:
        kcal100 = float(n["energy_100g"]) / 4.184
    if kcal100 is None:
        raise HTTPException(404, "üründe kalori bilgisi yok")
    ad = u.get("product_name_tr") or u.get("product_name") or "Ürün"
    if u.get("brands"):
        ad = f"{u['brands'].split(',')[0].strip()} {ad}"
    sonuc = {
        "ad": ad[:80], "paket": u.get("quantity") or "", "porsiyon": u.get("serving_size") or "",
        "porsiyon_g": _sayi(u.get("serving_quantity")),
        "yuz": {"kcal": round(_sayi(kcal100)), "protein": _sayi(n.get("proteins_100g")),
                "karb": _sayi(n.get("carbohydrates_100g")), "yag": _sayi(n.get("fat_100g"))},
    }
    with KILIT:
        onbellek = json_oku("barkod.json", {})
        onbellek[kod] = sonuc
        json_yaz("barkod.json", onbellek)
    return sonuc


class OneriIstek(BaseModel):
    kalan: int
    protein: int = 0
    saat: str = ""
    yenenler: str = ""


ONERI_SEMA = {
    "type": "OBJECT",
    "properties": {"oneriler": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
        "ad": {"type": "STRING"}, "neden": {"type": "STRING"}, "kcal": {"type": "NUMBER"},
        "protein": {"type": "NUMBER"}, "karb": {"type": "NUMBER"}, "yag": {"type": "NUMBER"},
        "miktar": {"type": "STRING"}}, "required": ["ad", "neden", "kcal", "protein", "karb", "yag", "miktar"]}}},
    "required": ["oneriler"],
}


@app.post("/api/oneri")
def oneri(istek: OneriIstek, x_anahtar: str | None = Header(default=None)):
    kontrol(x_anahtar)
    istem = (
        f"kilo vermeye çalışan birinin bugün {max(0, istek.kalan)} kalorisi kaldı"
        + (f", hâlâ {istek.protein} g proteine ihtiyacı var" if istek.protein > 0 else "")
        + (f". Saat {istek.saat}" if istek.saat else "")
        + (f". Bugün yedikleri: {istek.yenenler[:300]}" if istek.yenenler else "")
        + ". Türkiye'de kolay bulunan, doyurucu, proteinli 4 farklı öneri ver (ev yemeği, market, "
        "dışarıda yenebilecek bir şey karışık olsun). Her biri kalan kaloriyi aşmasın. "
        "'neden' alanı tek kısa cümle olsun. Türkçe karakterleri (ç, ğ, ı, ö, ş, ü) doğru kullan. Kalan kalori çok azsa düşük kalorili atıştırmalık öner."
    )
    sonuc = gemini([{"text": istem}], ONERI_SEMA, 0.8)
    liste = []
    for o in (sonuc.get("oneriler") or [])[:6]:
        if isinstance(o, dict) and o.get("ad"):
            liste.append({"ad": str(o["ad"])[:80], "neden": str(o.get("neden", ""))[:160],
                          "miktar": str(o.get("miktar", ""))[:60], "kcal": round(_sayi(o.get("kcal"))),
                          "protein": _sayi(o.get("protein")), "karb": _sayi(o.get("karb")), "yag": _sayi(o.get("yag"))})
    return {"oneriler": liste}


# --- Bildirimler ------------------------------------------------------------------
def vapid():
    yol = VERI / "vapid.pem"
    if not yol.exists():
        from py_vapid import Vapid01
        v = Vapid01()
        v.generate_keys()
        v.save_key(str(yol))
        os.chmod(yol, 0o600)
    from py_vapid import Vapid01
    from py_vapid.utils import b64urlencode
    from cryptography.hazmat.primitives import serialization
    v = Vapid01.from_file(str(yol))
    ham = v.public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return str(yol), b64urlencode(ham)


@app.get("/api/push/anahtar")
def push_anahtar(x_anahtar: str | None = Header(default=None)):
    kontrol(x_anahtar)
    return {"anahtar": vapid()[1]}


@app.post("/api/push/abone")
async def push_abone(istek: Request, x_anahtar: str | None = Header(default=None)):
    kontrol(x_anahtar)
    abone = await istek.json()
    if not isinstance(abone, dict) or not str(abone.get("endpoint", "")).startswith("https://"):
        raise HTTPException(400)
    with KILIT:
        liste = [a for a in json_oku("aboneler.json", []) if a.get("endpoint") != abone["endpoint"]]
        liste.append({"endpoint": abone["endpoint"], "keys": abone.get("keys", {})})
        json_yaz("aboneler.json", liste[-5:])
    return {"ok": True}


@app.post("/api/push/dene")
def push_dene(x_anahtar: str | None = Header(default=None)):
    kontrol(x_anahtar)
    return {"gonderilen": bildir("Bildirimler açık 👍", "Akşam 21:00'de ve tartılma gününde haber vereceğim.")}


def bildir(baslik: str, govde: str) -> int:
    from pywebpush import webpush, WebPushException
    yol, _ = vapid()
    with KILIT:
        liste = json_oku("aboneler.json", [])
    kalan, sayi = [], 0
    for a in liste:
        try:
            webpush(a, json.dumps({"baslik": baslik, "govde": govde}, ensure_ascii=False),
                    vapid_private_key=yol, vapid_claims={"sub": "mailto:kalori@example.com"}, ttl=3600)
            kalan.append(a)
            sayi += 1
        except WebPushException as e:
            kod = getattr(e.response, "status_code", 0)
            if kod not in (404, 410):
                kalan.append(a)
        except Exception:
            kalan.append(a)
    with KILIT:
        json_yaz("aboneler.json", kalan)
    return sayi


def gun_anahtari(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, TZ).strftime("%Y-%m-%d")


def zamanlayici():
    while True:
        try:
            simdi = datetime.now(TZ)
            gun = simdi.strftime("%Y-%m-%d")
            durum = json_oku("zamanlayici.json", {})
            v = veri_oku()
            ayar = v.get("ayar") or {}
            # Akşam 21:00 hatırlatması: bugün az ya da hiç girilmediyse
            if ayar.get("aksamBildirim", True) and simdi.hour == 21 and durum.get("aksam") != gun:
                bugun = [o for o in v["kayit"].values() if not o.get("silindi") and gun_anahtari(o.get("t", 0)) == gun]
                toplam = sum(o.get("kcal", 0) for o in bugun)
                if not bugun:
                    bildir("Bugünü girdin mi?", "Bugün hiçbir şey girilmemiş. Yediklerini eklemeyi unutma 🍽️")
                elif toplam < 900:
                    bildir("Bugünü girdin mi?", f"Bugün yalnızca {round(toplam)} kcal girilmiş. Eksik kalan var mı?")
                durum["aksam"] = gun
            # Tartılma hatırlatması: pazartesi 09:00 ve son 5 günde tartı yoksa
            if ayar.get("tartiBildirim", True) and simdi.weekday() == 0 and simdi.hour == 9 and durum.get("tarti") != gun:
                son = max((o.get("t", 0) for o in v["kilo"].values() if not o.get("silindi")), default=0)
                if time.time() * 1000 - son > 5 * 86400 * 1000:
                    bildir("Tartılma günü ⚖️", "Sabah aç karnına tartıl, kilonu gir. Haftalık özetin de hazır.")
                else:
                    bildir("Haftalık özetin hazır 📊", "Geçen haftayı görmek için uygulamayı aç.")
                durum["tarti"] = gun
            json_yaz("zamanlayici.json", durum)
        except Exception as e:  # zamanlayıcı asla ölmesin
            print("zamanlayici hata:", e, flush=True)
        time.sleep(60)


@app.on_event("startup")
def baslat():
    threading.Thread(target=zamanlayici, daemon=True).start()


# --- Sayfa ----------------------------------------------------------------------
@app.get("/", include_in_schema=False)
@app.get("/index.html", include_in_schema=False)
def ana_sayfa(k: str = ""):
    html = (WEB / "index.html").read_text(encoding="utf-8")
    if _dogru(k):
        html = html.replace('href="/manifest.webmanifest"', f'href="/manifest.webmanifest?k={k}"', 1)
    return HTMLResponse(html, headers={"Cache-Control": "no-cache"})


@app.get("/manifest.webmanifest")
def manifest(k: str = ""):
    veri = {
        "name": "SalimBabanınZayıflamaUygulaması",
        "short_name": "Zayıflama",
        "lang": "tr",
        "start_url": f"/?k={k}" if _dogru(k) else "/",
        "scope": "/",
        "display": "standalone",
        "background_color": "#0f1412",
        "theme_color": "#0f1412",
        "icons": [
            {"src": "/ikon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/ikon-512.png", "sizes": "512x512", "type": "image/png"},
        ],
    }
    return JSONResponse(veri, media_type="application/manifest+json", headers={"Cache-Control": "no-store"})


@app.get("/sw.js")
def sw():
    return FileResponse(WEB / "sw.js", media_type="text/javascript", headers={"Cache-Control": "no-cache"})


app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
