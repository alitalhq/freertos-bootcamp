# ADR-004: Lab modu ve S5 çözümleri. Standart dışı, `#ifdef` ile ayrılmış

**Durum:** Kabul edildi
**Tarih:** 26.09.2026
**Karar veren:** alitalhq
**İlgili:** spec §15 madde 4, rapor §8, ADR-001 (UART IT), ADR-003 (deney akışı)

## Bağlam

Resmi S5 ölçümünde (100 Hz + 5 ms CPU işi) 35 basıştan 12'sinin yanıtı kayboldu, gelen yanıtların 22/23'ü 20 ms'yi aştı. Gecikme her basışla ~10 ms büyüdü (rapor §4.4).

Kök nedeni ölçümden çıkardık. Her 10 ms'lik periyodun ~5,05 ms'i öncelik 3'teki TelemetryTask'ın işi. Geriye ~4,95 ms'lik boş pencere kalıyor. 64 baytlık bir mesaj ise hatta 5,56 ms sürüyor. Öncelik 1'deki UartTxTask, bir gönderim biter bitmez sıradakini başlatamıyor, çünkü CPU o sırada yine hesaplamada. Bu yüzden hat periyot başına **en fazla 1 mesaj** taşıyabiliyor. Bu, telemetri üretimine tam eşit. Boş kapasite sıfır olduğu için her buton yanıtı kalıcı bir birikim yaratıyor.

İki şey istendi:
1. Çözümleri denemek ve en iyisini bulmak.
2. Başkalarının da kendi ayarlarıyla (frekans, CPU yükü, çözüm, elle/otomatik basış) deney yapabileceği bir arayüz.

Kısıt: ödevin zorunlu S0–S5 ölçümleri **standart ayarlarla** alındı ve değişmemeli.

## Karar

1. **Lab modu, derleme bayrağıyla ayrılıyor:** `APP_LAB_MODE` (varsayılan **0**).
   - `0`: resmi derleme. Çözüm kodu ve UART komut kanalı hiç derlenmiyor. S0–S5 bu derlemeyle ölçüldü.
   - `1`: lab derlemesi. Kart **bir kez** yükleniyor. PC arayüzü UART'tan `RUN period=… work=… fix=… inject=…` gönderiyor. Kart ayarı SRAM2'ye yazıp **yeniden başlıyor**, böylece her deney boş kuyruklar, sıfır sayaçlar ve yeni kalibrasyonla başlıyor.
2. **Her çözüm kendi `#ifdef` bloğunda** (`ENABLE_FIX_UART_PRIO`, `ENABLE_FIX_BTN_PRIO`, `ENABLE_FIX_TC_CHAIN`), çalışma anında `fix_mask` ile seçiliyor. Arayüzde 5 seçenek var: standart (0), naif (F4), kök neden (F1), öncelik değiştirmeden TC zinciri (F8), optimal (F1+F4).
3. **Otomatik basış** (`inject=1`): EXTI13, yazılımla (`SWIER`) tetikleniyor. Gerçek butonla aynı ISR, aynı 30 ms filtre ve aynı t₀ noktası kullanılıyor. Aralıklar `[gmin, gmax]` içinde sözde rastgele ve `seed` ile tekrarlanabilir. `inject=0` ise elle basış.
4. **Önerilen çözüm:** F1 + F4, yani UartTxTask ve ButtonTask'ın ikisi de CPU işinin üstünde (öncelik 4). **Görev önceliklerinin değişmemesi gerekiyorsa F8 (TC zinciri).**

## Değerlendirilen çözümler

Hepsi S5 yükünde, 35 otomatik basışla ve **aynı basış dizisiyle** (`seed=7`) ölçüldü:

| Maske | Çözüm | Yanıt | Ort. R | Max R | > 20 ms | txQ max | Yorum |
|---|---|---|---|---|---|---|---|
| 0 | Standart (ödev) | 24/35 | 117 ms | 165 ms | 24 | 16 | Sorunun kendisi |
| F4 | ButtonTask önceliği 2→4 (naif) | 35/35 | 129 ms | 165 ms | **34** | 16 | Görev beklemesi kalktı, birikim kalmadı değil. **Yanlış yere bakan çözüm** |
| **F1** | **UartTxTask önceliği 1→4 (kök neden)** | **35/35** | **11,0 ms** | **16,3 ms** | **0** | 1 | Hat bir daha boşta beklemiyor, birikim yok |
| **F8** | **Sonraki gönderim TC kesmesinden (öncelikler 3 > 2 > 1 aynı)** | **35/35** | **11,0 ms** | **16,4 ms** | **0** | 2 | Kök nedeni öncelik değiştirmeden gideriyor |
| **F1+F4** | **UART ve Button görevleri CPU işinin üstünde** | **35/35** | **7,2 ms** | **10,3 ms** | **0** | 1 | **En iyisi** |

### Neden F1+F4?

- **F1 kök nedeni gideriyor.** UART görevi CPU işini birkaç µs kesip sıradaki mesajı hemen başlatıyor. Hattın kapasitesi yeniden ~180 mesaj/s'ye çıkıyor, telemetri ise 100 mesaj/s üretiyor. Bedeli ölçüldü, sıfır değil ama küçük: UART görevi işi keserek her mesajda birkaç on µs alıyor. Ortalama iş süresi 5 050 → 5 086 µs (+%0,7), en uzun iş 5 086 → 5 221 µs (F1+F4'te 5 347 µs). Telemetri periyodunun ortalaması 9 999 µs'de kaldı, ama sapması arttı: 9 972–10 031 µs'den 9 899–10 034 µs'ye (F1+F4'te 9 887–10 109 µs). Telemetri için ±~110 µs'lik bu sapma, 10 ms periyotta %1,1 demek. Yanıt süresindeki ~150 ms'lik kazançla karşılaştırıldığında kabul edilebilir.
- **F4 tek başına işe yaramıyor, ama F1 ile birlikte kalan gecikmeyi alıyor.** F1'den sonra kalan en büyük değişken, basışın hesaplama penceresine denk gelmesi (t₁−t₀ ≤ 5 ms). ButtonTask da işin üstüne alınınca bu kalkıyor ve max R 16,3'ten 10,3 ms'ye iniyor. Kalan süre fizik: hatta o an giden mesaj (≤ 5,56 ms) artı yanıtın kendi 5,56 ms'si.
- **Kural:** Yanıt yolundaki her görev (ButtonTask → UartTxTask), uzun süren hesaplamadan daha yüksek öncelikli olmalı. Bu görevlerin kendileri kısa sürüyor, uzun işi kesmelerinin maliyeti µs düzeyinde.
- **CPU işini kesmek hata mı?** Öncelik "ne kadar önemli"ye göre değil, "ne kadar acil ve ne kadar kısa"ya göre verilir (rate/deadline-monotonic yaklaşım). Üste alınan iki görev iş başına yalnızca onlarca µs sürüyor ve CPU kullanımları sınırlı: basışları 30 ms'lik tekrar-kenar filtresi saniyede en fazla ~33 ile sınırlıyor (~%0,1 CPU), UART görevi saniyede en fazla ~180 mesaj başlatabiliyor (~%0,5). CPU işi periyotta ~36 µs uzuyor ve 10 ms'lik periyoduna yine rahatça sığıyor. Üstelik UART artık aç kalmadığı için telemetri kaybı 9'dan 0'a indi: CPU işinin ürettiği veri önceden kayboluyordu. Bu karar ancak üstteki görevlerin CPU kullanımı sınırlı olduğu sürece geçerli. Sınırsız çalışabilen bir görev üste konsaydı CPU işini aç bırakırdı.
- **F8 (TC zinciri) öncelik değiştirmeden aynı sonucu veriyor.** Standartta UART bir mesajı bitirince sıradakini başlatmak için UartTxTask'ın CPU alması gerekiyordu. F8'de sıradaki mesajı TC kesmesinin kendisi kuyruktan alıp başlatıyor. Kesme görev önceliklerinden bağımsız çalıştığı için hat boşta beklemiyor. Görev öncelikleri ödevdeki gibi 3 > 2 > 1 kalıyor; kartın gönderdiği TSK kaydı da bunu doğruluyor. Telemetriye etkisi F1'den küçük: ortalama iş 5 054 µs (F1'de 5 086), periyot 9 966–10 031 µs (standartta 9 972–10 031). Sınırı: ButtonTask CPU işinin altında kaldığı için görev beklemesi (≤ 5 ms) sürüyor, bu yüzden en büyük R 16,4 ms. t₃ bu varyantta görevde değil kesmede alınıyor.
- **Denenip çıkarılanlar:** İki varyant daha ölçüldü ve tekrar ettikleri için kaldırıldı:
  - **BTN yanıtını kuyruğun önüne almak:** geç kalan yok, ama kuyruk dolunca öne de giremediği için 11 yanıt kayboldu. Naif çözümle aynı dersi veriyor.
  - **F1 + öne alma:** F1 ile birebir aynı sonucu verdi.

## Sonuçlar

- **Kolaylaşan:** Aynı kartla, yeniden derlemeden istenen senaryo ve çözüm deneniyor. Basışlar otomatik ve tekrarlanabilir.
- **Zorlaşan:** İki derleme var. README'de hangisinin ne için kullanıldığı açıkça yazıyor. Lab derlemesinde RX kesmesi açık; ancak deney sırasında PC komut göndermediği için bu kesme boşta kalıyor.
- **Karşılaştırma notu:** Lab ölçümleri otomatik basışla alındı, resmi S0–S5 elle basışla. Standart S5, otomatik basışla da aynı resmi verdi (24/35 yanıt, hepsi geç, txQ 16/16).
- **Seçilim yanlılığı:** Standart S5'te ortalama t₁−t₀ (0,47 ms), F1'dekinden (1,38 ms) düşük görünüyor. Nedeni, hesaplama penceresine denk gelen basışların standart koşuda **kaybolan** basışlar olması; ortalamalar yalnızca yanıtı gelen olaylardan hesaplanıyor.
- **Tekrar bakılacak:** Kalan 10,3 ms'nin çoğu hat süresi. Daha düşük değer için mesajı kısaltmak ya da baud'u artırmak gerekir, ki bu ikisi ödevin standart ayarları.
