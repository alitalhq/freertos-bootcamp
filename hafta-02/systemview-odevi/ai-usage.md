# Yapay Zekâ Kullanımı

**Araç:** Claude (Claude Code)

## Hangi işlerde destek alındı?

- J-Link olmadan SystemView kaydı alma yönteminin seçilmesi (Hafta 3 paketi incelenerek)
- SystemView/RTT kaynaklarının ve FreeRTOS 10 yamasının projeye eklenmesi, uygulama olayları
- `capture.py` iz desteği, `.SVDat` çözücüsü ve görsellerin çizimi
- Rapor ve README taslakları

## Nasıl kontrol edildi?

- **Kayıt bütünlüğü:** Her `.SVDat` dosyası kartın gönderdiği bayt sayısı ve FNV-1a checksum ile doğrulandı.
- **İz ile ölçüm uyumu:** İzden (DWT) okunan t₀→t₁…t₄ aralıkları CSV'deki TIM2 ölçümleriyle karşılaştırıldı; fark ~10 µs.
- **Zincirler:** Her izde hangi olayların tam t₀→t₄ zinciri olduğu dosyadan çıkarılıp `experiment.csv`'ye yazıldı.
- **Görseller:** Çözücü her dosyayı sonuna kadar hatasız okudu; görevler ve kesmeler SystemView'deki görünümle karşılaştırıldı.

## Hangi öneriler değiştirildi, neden?

| Öneri / iddia | Neden yanlıştı | Sonuç |
|---|---|---|
| 128 word'lük inject görevi yeter | İz açıkken stack taştı (`vApplicationStackOverflowHook`) | 256 word |
| SystemView Init post-mortem modunda kanalı kendisi ayarlar | `UpChannel` ayarlanmıyordu; olaylar 16 baytlık kanal 0'a gitti, izde yalnız senkronlar kaldı | `app_trace_init` içinde ayarlandı |
| `O=FreeRTOS 10.3.1` sistem tanımı | SystemView açıklama dosyasını bulamadı, API adları çıkmadı | `O=FreeRTOS`, sürüm `N=` alanında |
| RUN satırı için 112 baytlık tampon yeter | `txprio` eklenince satır 125 karakter oldu, kart sessizce attı | 192 bayt |
| Koşu, LAB satırından itibaren kaydedilsin | UART önceliği 4'te LAB ilk satır oldu ve reset baytıyla bozuldu; koşu hiç başlamadı | Baştaki çöp bayt kesiliyor (test eklendi) |
| SystemView olay adlarını modül tanımından okur | V4.10b post-mortem dosyada okumadı | Açıklama dosyası + izden kendi çizimimiz |
