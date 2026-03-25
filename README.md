# Local Browser Automation

Bu proje Playwright ile:

1. Verilen URL'e gider.
2. Kullanici adi ve sifre ile login olur.
3. Anasayfadaki username alanina belirlenen degeri yazar.
4. `Apply` butonuna basar.

## Kurulum

```powershell
python -m pip install -r requirements.txt
python -m playwright install chromium
Copy-Item config.example.json config.json
```

## Config

`config.json` icinde su alanlari doldurun:

- `url`: Login sayfasi.
- `login.username`: Giris kullanici adi.
- `login.password`: Giris sifresi.
- `target.value`: Username alanina yazilacak deger.
- `selectors.*`: Sayfadaki gerçek CSS selector'ler.

## Calistirma

```powershell
python app.py --headed
```

Tarayiciyi gizli modda calistirmak icin:

```powershell
python app.py
```
