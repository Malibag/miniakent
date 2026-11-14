"""Uygulamanın Haberler listesi (kullanıcı, 2026-11-14): Miniakent'in Instagram'daki son 20 videosu.

GitHub görevinde 30 dakikada bir çalışır, listeyi Firebase'e yazar (haberler/; uygulama herkese açık okur):
    IG_TOKEN (Instagram anahtarı) ve FIREBASE_SA (Firebase hizmet hesabı JSON'u) GitHub gizli değişkenlerinden gelir.
Bilgisayarda deneme (Firebase'e dokunmaz, dosyaya yazar):
    python haberler_topla.py --dosya <yol> [--anahtar-dosya D:\\Tum_Uygulamalar\\Hikaye_Sehri\\instagram_token.txt]

Kapak adresleri Instagram'ın süreli bağlantıları: her çalışmada yenilendiği için listede hep geçerli kalır.
Tarih ve başlık burada hazırlanır; uygulama olduğu gibi gösterir (biçim değişikliği mağaza güncellemesi istemez).
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import urllib.parse
import urllib.request

IG = "https://graph.instagram.com/me/media"
DB = "https://miniakent-default-rtdb.europe-west1.firebasedatabase.app"
TR = dt.timezone(dt.timedelta(hours=3))
AYLAR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
ADET = 20
# uygulamanın yazı tipinde olmayan işaretler (emoji, birleştiriciler) başlıktan çıkarılır
EMOJI = re.compile("[\U00010000-\U0010FFFF\u2600-\u27BF\u2B00-\u2BFF\uFE00-\uFE0F\u200D\u20E3]")


def medya(tok):
    q = urllib.parse.urlencode({"fields": "id,caption,media_type,permalink,thumbnail_url,timestamp",
                                "limit": 40, "access_token": tok})
    with urllib.request.urlopen(f"{IG}?{q}", timeout=60) as r:
        return json.load(r).get("data", [])


def baslik(caption):
    for satir in (caption or "").splitlines():
        s = re.sub(r"\s+", " ", EMOJI.sub("", satir)).strip()
        if s and not s.startswith("#"):
            return s if len(s) <= 140 else s[:139].rstrip() + "…"
    return "Miniakent"


def tarih(ts):
    t = dt.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S%z").astimezone(TR)
    return f"{t.day} {AYLAR[t.month - 1]}"


def liste(tok):
    l = []
    for m in medya(tok):
        if m.get("media_type") != "VIDEO" or not m.get("permalink") or not m.get("thumbnail_url"):
            continue
        l.append({"id": m["id"], "tarih": tarih(m["timestamp"]), "baslik": baslik(m.get("caption")),
                  "baglanti": m["permalink"], "kapak": m["thumbnail_url"]})
        if len(l) == ADET:
            break
    return l


def _anahtar(kapsam):
    from google.oauth2 import service_account  # yalnız GitHub görevinde gerekli (pip install google-auth)
    from google.auth.transport.requests import Request
    kimlik = service_account.Credentials.from_service_account_info(json.loads(os.environ["FIREBASE_SA"]), scopes=kapsam)
    kimlik.refresh(Request())
    return kimlik.token


def firebase_oku():
    """Bir önceki liste (yoksa None): yeni video bundan anlaşılır."""
    tok = _anahtar(["https://www.googleapis.com/auth/firebase.database", "https://www.googleapis.com/auth/userinfo.email"])
    istek = urllib.request.Request(f"{DB}/haberler.json", headers={"Authorization": f"Bearer {tok}"})
    with urllib.request.urlopen(istek, timeout=60) as r:
        return json.load(r)


def firebase_yaz(veri):
    tok = _anahtar(["https://www.googleapis.com/auth/firebase.database", "https://www.googleapis.com/auth/userinfo.email"])
    istek = urllib.request.Request(f"{DB}/haberler.json", data=json.dumps(veri, ensure_ascii=False).encode("utf-8"),
                                   method="PUT", headers={"Authorization": f"Bearer {tok}",
                                                          "Content-Type": "application/json"})
    with urllib.request.urlopen(istek, timeout=60) as r:
        r.read()


# Bildirim (kullanıcı, 2026-11-14): yeni video çıkınca "duyurular" konusuna abone telefonlara gider; uygulamadaki
# izin sorusunda ya da Ayarlar > Bildirimler'de "Evet" diyenler abonedir. Telefon kimliği saklanmaz.
KONU = "duyurular"


def bildirim_gonder(konu, metin):
    tok = _anahtar(["https://www.googleapis.com/auth/firebase.messaging"])
    govde = {"message": {"topic": konu, "notification": {"title": "Miniakent", "body": metin},
                         "android": {"notification": {"channel_id": "bildirimler"}}}}
    istek = urllib.request.Request("https://fcm.googleapis.com/v1/projects/miniakent/messages:send",
                                   data=json.dumps(govde, ensure_ascii=False).encode("utf-8"), method="POST",
                                   headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
    with urllib.request.urlopen(istek, timeout=60) as r:
        r.read()


def yeni_video(onceki, veri):
    """Listenin en yenisi bir önceki listede yoksa o video (bir çalışmada en çok bir bildirim). Önceki liste yoksa ya da
    boşsa (ilk çalışma) bildirim gitmez; Instagram'dan bir video silinince eskisi en üste çıksa da bildirim gitmez."""
    if not veri["liste"]:
        return None
    en_yeni = veri["liste"][0]
    veri["bildirilen"] = en_yeni["id"]
    if not isinstance(onceki, dict):
        return None
    eski = {h.get("id") for h in onceki.get("liste", []) if isinstance(h, dict)}
    if not eski or en_yeni["id"] in eski or en_yeni["id"] == onceki.get("bildirilen"):
        return None
    return en_yeni


def main():
    a = argparse.ArgumentParser()
    a.add_argument("--dosya", help="Firebase yerine bu dosyaya yaz (deneme)")
    a.add_argument("--anahtar-dosya", help="Instagram anahtarı dosyadan (deneme)")
    o = a.parse_args()
    if o.anahtar_dosya:
        with open(o.anahtar_dosya, encoding="utf-8-sig") as f:
            tok = f.read().strip()
    else:
        tok = os.environ["IG_TOKEN"].strip()
    veri = {"liste": liste(tok), "guncel": int(dt.datetime.now(dt.timezone.utc).timestamp())}
    if o.dosya:
        with open(o.dosya, "w", encoding="utf-8") as f:
            json.dump(veri, f, ensure_ascii=False, indent=1)
        print(f"haberler: {len(veri['liste'])} video yazildi")
        return
    yeni = yeni_video(firebase_oku(), veri)
    firebase_yaz(veri)   # önce işaret yazılır: bildirim gitmese de aynı video için bir daha denenmez
    print(f"haberler: {len(veri['liste'])} video yazildi")
    if yeni:
        bildirim_gonder(KONU, "Yeni video: " + yeni["baslik"])
        print("bildirim gonderildi:", yeni["id"])


if __name__ == "__main__":
    sys.exit(main())
