# 🥗 SalimBabanınZayıflamaUygulaması

> Türk mutfağını bilen, haftalık düşünen bir kalori sayacı.
> Yemeği yaz, fotoğrafını çek ya da barkodu okut; gerisini o hesaplar.

iPhone'a ana ekran uygulaması olarak eklenen bir web uygulaması (PWA). Veri telefonda durur,
yedeği kendi sunucumda. Reklam, hesap, abonelik yok.

---

## Neden bir tane daha kalori uygulaması?

Mağazadaki uygulamalar "mercimek çorbası", "lahmacun" ya da "Gong" bilmiyor, her şeyi gram gram girdiriyor ve
bir günü aşınca bütün haftayı kaybetmiş hissettiriyor. Bu uygulama:
- Türk yemeklerini **porsiyonuyla** bilir (1 kase, 1 dilim, 1 adet),
- Günü değil **haftayı** hedef alır,
- Bilmediği yemeği yapay zekâya sorar ama **sana onaylatmadan eklemez**.

## Özellikler

### 🍲 Yemek ekleme (5 yol)
| Yol | Nasıl çalışıyor |
|---|---|
| ⌨️ Yazarak | Önce yerel liste (~260 Türk yemeği ve atıştırmalık), sonra **Open Food Facts**, en son sunucudaki **Gemini** |
| 📷 Tabak fotoğrafı | Gemini tabaktakileri ve porsiyonu tahmin eder, liste halinde onayına sunar |
| 🏷️ Barkod | Kamerayla okutulur, Open Food Facts'ten paket bilgisi gelir |
| 🎤 Sesle | "İki dilim ekmek, bir yumurta" demen yeterli |
| ⭐ Favoriler / tekrar | Sık yediklerin tek dokunuşla; "dünkünü tekrarla" |

Her yemekte kalori, protein, karbonhidrat ve yağ tutulur.

### 📊 Haftalık bütçe
- Hedef: Mifflin-St Jeor ile bazal metabolizma × hareket katsayısı − istenen açık (haftada 0,75-1 kg için ~900 kcal).
- Haftalık bütçe = günlük hedef × 7 (pazartesi-pazar).
- **Bugünün sınırı = haftanın kalanı ÷ kalan gün** (makul bir aralıkta tutulur). Dün fazla yediysen bugün biraz az, az yediysen biraz fazla.
- Eklemeden önce sınırı aşacaksan uyarır: "Bunu eklersen bugün 240 kcal aşacaksın, haftada hâlâ 600 kcal payın var."
- Kilo düştükçe hedef kendiliğinden güncellenir.

### 📈 Takip
- Kilo grafiği ve hedef kilo, BMI
- Su sayacı, seri (kaç gündür girdin), haftalık özet
- 🍽️ **"Kalanla ne yiyebilirim?"**: kalan kalori ve proteine göre Türk mutfağından öneriler

### 🔔 Hatırlatmalar
- Akşam **21:00**: bugün hiç ya da çok az girildiyse "Bugünü girdin mi?"
- Pazartesi **09:00**: tartılma günü ve haftalık özet

### 🖥️ Masaüstünden de
[Masaüstü Kartları](https://github.com/darkapasha/masaustu-kartlari) uygulamasında bir Kalori kartı var:
bilgisayardan bugünkü durumu görüp yemek eklenebilir.

## Mimari

```
iPhone (PWA)  ──HTTPS──>  Caddy  ──>  FastAPI (main.py)  ──>  veri/ (JSON durum + yedek)
web/index.html             tek sayfa uygulama, veri localStorage'da
web/yemekler.js            yerel yemek veritabanı: [ad, porsiyon, kcal, protein, karbonhidrat, yağ]
web/sw.js                  çevrimdışı açılış + bildirimler
main.py                    eşleme, senkron, yemek arama, AI tahmin, fotoğraf, push, zamanlayıcı
```

- **Senkron:** Telefon tüm durumu gönderir; her kayıtta zaman damgası vardır, yeni olan kazanır. Silinenler "mezar taşı" ile işaretlenir ki başka cihazda geri gelmesin.
- **Gemini:** önce hızlı `flash-lite` model (2-10 sn), yoğunluk hatasında bir kez tekrar, olmazsa büyük model.
- **Eşleme:** QR ya da Ayarlar'daki 6 haneli kod; her istek gizli bir anahtar taşır.

## Kurulum

```bash
bash kur.sh                       # venv, systemd servisi, Caddy bloğu (alan adını kendininkiyle değiştir)
echo "GEMINI_API_KEY=..." > veri/.env
```

Anahtarlar ve kişisel veriler `veri/` içinde; depoya girmez.

---

Kendim için yaptım, adı da ona göre 😄 Claude ile birlikte, vibe coding ile yapıldı 🎧
