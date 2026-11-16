# 🥗 SalimBabanınZayıflamaUygulaması — kalori takibi

iPhone'a ana ekran uygulaması olarak eklenen, Türk mutfağını bilen bir kalori sayacı.
Yemeği yazarsın, fotoğrafını çekersin ya da barkodu okutursun; günlük ve haftalık bütçeni takip eder.

## Özellikler

- 🍲 **~260 Türk yemeği ve atıştırmalık** hazır listede (mercimek çorbasından Gong'a kadar).
- 🔎 Listede yoksa **Open Food Facts**, o da yoksa sunucudaki **Gemini** tahmin eder; sonuç eklemeden önce onayına sunulur.
- 📷 **Tabak fotoğrafı**, 🏷️ **barkod**, 🎤 **sesle ekleme**, ⭐ favoriler ve "dünkünü tekrarla".
- 📊 **Haftalık bütçe**: bugünün sınırı haftanın kalanına göre ayarlanır, aşmadan önce uyarır.
- ⚖️ Kilo grafiği, hedef kilo düştükçe kendini günceller; su, seri (streak), haftalık özet.
- 🍽️ "**Kalanla ne yiyebilirim?**" önerisi.
- 🔔 Akşam 21:00 "bugünü girdin mi?" ve pazartesi tartılma hatırlatması (Web Push).
- 💾 Veri telefonda, yedeği sunucuda; masaüstü kartından da bakılıp eklenebilir.

## Yapı

```
main.py           FastAPI: eşleme, senkron (POST /api/esitle), yemek arama, AI tahmin, fotoğraf, push, zamanlayıcı
web/index.html    tek sayfalık uygulama
web/yemekler.js   yerel yemek veritabanı (ad, porsiyon, kcal, protein, karbonhidrat, yağ)
web/sw.js         çevrimdışı kabuk + bildirimler
kur.sh            sunucuya kurulum (venv, systemd, Caddy)
```

Gemini anahtarı sunucuda `veri/.env` içinde durur, depoya girmez. Telefon tek seferlik QR/kodla eşlenir.

---
Claude Code ile birlikte geliştirildi.
