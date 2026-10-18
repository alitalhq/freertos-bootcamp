# Yapay Zekâ Kullanımı

**Araç:** Claude (Claude Code)

## Hangi işlerde destek alındı?

- Ödev metninin ve referans firmware'in incelenmesi, referansın macOS'ta CubeIDE ile derlenmesi
- `vendor/` klasörünün yalnız kullanılan dosyalara indirilmesi
- Ölçümlerin alınması, karşılaştırma tablosu (`summary.py`)
- `.SVDat` çözücüsü (Hafta 2'den uyarlama), SystemView pencereleri ve görsel işaretleme
- Yorum ve README taslakları

## Nasıl kontrol edildi?

- **Derleme:** Kütüphaneler budandıktan sonra temiz derleme 0 hata, 0 uyarı verdi; ELF boyutu budamadan önceki derlemeyle aynı kaldı.
- **Hazır binary:** Eğitmenin hazır ELF'inin SHA256'sı, doğrulama dokümanındaki değerle karşılaştırıldı (aynı). Ölçümlerde kendi CubeIDE derlememiz kullanıldı.
- **Sayaçlar:** Her koşuda girişim = kabul + başarısız ve kabul = tüketilen; `summary.py` bunu kontrol ediyor (`assert`).
- **İz:** Her `.SVDat` dosyası ölçüm aracının bayt sayısı ve FNV-1a kontrolünden geçti; kayıp 0, durma nedeni "süre".
- **Görseller:** Görsellerdeki sayılar (xQueueSend dönüş değeri, Blocked süresi) SystemView'in kendi Events listesinden okundu. Yorumdaki 20,02 / 20,18 ms gibi zamanlar izden çözücüyle çıkarıldı.

## Hangi öneriler değiştirildi, neden?

| Öneri / iddia | Neden yanlıştı | Sonuç |
|---|---|---|
| `.d` dosyalarındaki göreli yollar kendi klasörlerine göre çözülsün | Derleme `Debug/` içinden çalışıyor; yalnız 35 dosya kalıyordu, başlıklar eksik | Yollar `Debug/`'a göre çözüldü, 71 dosya |
| Pencere dosyasının başına izin yalnız ilk tanım blogu konsun | Tek seferlik kayıtta görev listesi daha sonra geliyor; SystemView görev adlarını gösteremedi | Pencereden önceki bütün tanım paketleri alınıyor |
