# Local Browser Automation

Bu proje Playwright ile:

1. Verilen URL'e gider.
2. Kullanici adi ve sifre ile login olur.
3. Sayfadaki input ve butonlari DOM uzerinden kesfeder ve skorlar.
4. Anasayfadaki username alanina belirlenen degeri yazar.
5. `Apply` butonuna basar.
6. Istenirse tarayici trafigini Oxylabs proxy uzerinden gonderir.

## Kurulum

```powershell
python -m pip install -r requirements.txt
python -m playwright install chromium
Copy-Item config.example.json config.json
```

## Config

`config.json` icinde su alanlari doldurun:

- `url`: Login sayfasi.
- `proxy.*`: Oxylabs proxy bilgileri. Proxy kullanmayacaksaniz bu bolumu silebilirsiniz.
- `login.username`: Giris kullanici adi.
- `login.password`: Giris sifresi.
- `target.value`: Username alanina yazilacak deger.
- `selectors.*`: Biliniyorsa gerçek CSS selector'ler. Bos birakilirsa auto-discovery calisir.
- `debug.dump_candidates_dir`: Discovery sonucunda adaylari JSON olarak diske yazar.

## Oxylabs Notu

Oxylabs Scraper API tipik olarak HTML cekme ve bypass icin uygundur. Login olup form doldurmak ve butona basmak gibi interaktif akislarda Playwright gerekir. Bu projede dogru entegrasyon modeli:

- Tarayici otomasyonu: Playwright
- IP/proxy katmani: Oxylabs

## Discovery Mantigi

Selector verilmemisse veya verilen selector eleman bulmazsa script:

- tum `input`, `textarea`, `button`, `[role=button]` elemanlarini toplar
- `id`, `name`, `class`, `aria-label`, `placeholder`, yakin label metni, parent context gibi alanlari okur
- hedefe gore puanlar:
  - login username
  - login password
  - login submit
  - home username field
  - apply button
- en yuksek skorlu adayi kullanir

Debug klasorunde su dosyalar olusur:

- `login_username.json`
- `login_password.json`
- `login_submit.json`
- `home_username.json`
- `apply_button.json`

Bu dump'lar yanlis eleman secildiginde hangi adaylarin goruldugunu incelemek icin kullanilir.

## Calistirma

```powershell
python app.py --headed
```

Tarayiciyi gizli modda calistirmak icin:

```powershell
python app.py
```
