# Yapay Zekâ Kullanımı

**Araç:** Claude (Claude Code)

## Hangi işlerde destek alındı?

- Ders ve ödev metinlerinin incelenmesi, Hafta 1 projesiyle karşılaştırılması
- A/B/C sürümleri, S6 yükü ve TEL bekleme istatistiği için firmware kodu (`firmware/odev02/App/`)
- Ölçüm aracı (`interface/capture.py`) ve testleri
- Analiz betiği, grafikler, rapor ve README taslakları

## Üretilen kod ve sonuçlar nasıl kontrol edildi?

Hiçbir kod ya da iddia doğrudan kabul edilmedi. Her adım kartta ya da ham veriyle sınandı:

- **Sürümler:** Her koşunun TSK satırında ButtonTask önceliği okundu: A'da 2, B ve C'de 4. C koşularında `btn_first=1` görüldü.
- **C'nin seçim kuralı:** C-S6'da t₃−t₂ en çok 5,48 ms çıktı. Bu, hattaki tek bir mesajın süresinden (5,56 ms) kısa; BTN'nin bekleyen TEL'lerin önüne geçtiğini gösteriyor.
- **TEL bekleme ölçümü:** C-S6'daki en uzun bekleme 22,46 ms. Hesapla beklenen değer 3 TEL + 1 BTN = 4 × 5,56 ≈ 22,2 ms; ölçümle uyuyor.
- **Ham oturum:** `_raw.txt` dosyasındaki TEL satırı sayısı, kartın `tel_sent` sayacıyla karşılaştırıldı; beş koşuda da eşit. A-S5'te bu eşitlik, ilk satırın birleşik olmasına rağmen sağlanıyor (bkz. README, Ölçüm notları).
- **Araç ile firmware uyumu:** Bir test, araçtaki senaryo tablosunun `scenario.c` ile aynı olduğunu kontrol ediyor.
- **Rapor:** Rapordaki sayılar `summary.csv` ve meta dosyalarıyla karşılaştırıldı. Ölçülmeyen mekanizmalar (CPU bekleme sırası, kaybın yer değiştirmesi) hipotez olarak yazıldı.

## Hangi öneriler değiştirildi, neden?

| Öneri / iddia | Neden yanlıştı | Sonuç |
|---|---|---|
| Ham oturum, kartın LAB satırından itibaren kaydedilsin | Kart ilk 4 TEL'i LAB'dan önce gönderiyordu; dosyada eksik kaldılar | Bu koşuya ait satırlar LAB'dan önce de toplanıyor; satır sayısı `tel_sent` ile eşit |
| LAB'dan önce koşu adını taşıyan her satır alınsın | A-S5'te önceki çalışma da "A-S5" adını taşıyordu; yarım satırı ham dosyanın ilk satırına karıştı | Sıra numarası geri giderse ya da satır 64 bayt değilse atılıyor; durum README'de not edildi |
| LAB satırı TEL türünde gönderilsin | TEL bekleme istatistiğine karışırdı | Ayrı `MSG_INFO` türü eklendi |
| S5'te TEL bekleme ortalamaları karşılaştırılsın | Ortalama koşu süresine bağlı: C-S5 653 s, B-S5 42 s sürdü | S5'te yalnızca en uzun bekleme karşılaştırıldı |
| "B, S5'te R'yi kötüleştirdi" (medyan 130 → 158 ms) | A'da kuyruk doluyken gelen yanıtlar kayboldu ve ortalamaya girmedi | Raporda bu fark seçilim etkisi olarak açıklandı |

Tasarım kararları da öneriler arasından seçildi:
- **Yeni proje:** Hafta 1 değiştirilmedi; Hafta 2 için ayrı bir kopya açıldı.
- **Tek değişken:** Hafta 1'in çözümleri (TC zinciri, UART önceliği) bu projeye taşınmadı. Böylece sürümler arasında tek değişken kaldı.
- **Basış yöntemi:** Resmî ölçümler fiziksel B1 basışlarıyla alındı. Otomatik basışlı koşular yalnızca destekleyici veri olarak ayrı tutuluyor.
