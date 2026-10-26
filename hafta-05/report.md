# Ödev 5: StreamBuffer ve Task Notification ile çerçeveli veri hattı

> **Ölçüm durumu:** bu sürümde tasarım, hesaplar ve beklenen davranış var. Kart ölçümleri (T1–T9) henüz alınmadı. "Ölçülecek" yazan her yer, `evidence/` dolunca `host/figures.py` çıktısıyla doldurulacak. Burada hiçbir sayı ölçüm gibi sunulmuyor.

## 1. Gereksinimin iki kaynağı

Ödev belgesi ile eğitmenin sesli açıklaması birlikte kullanıldı:

- **Belge** protokolü, CRC'yi, testleri (T1–T8) ve teslim biçimini tanımlıyor.
- **Ses** iki şeyi netleştiriyor:
  - cevap, işi yapan task'tan notification ile çıkıp yine bir StreamBuffer üzerinden aynı çevre birimine dönmeli;
  - sistem yük altında denenmeli. Yük, düşük öncelikli task'ların aynı UART'tan bastığı log verisi; cevaplar seyrek ama acil.

Bu yüzden belgeye ek olarak:
- TX yolu da bir StreamBuffer (`txStream`) ve kesmeyle boşalıyor.
- Ek bir **T9** testi var: log yükü artarken cevap gecikmesi.

## 2. Tasarım

```
UART RX ─ISR─▶ rxStream ─▶ Parser (3) ─Job + Give─▶ Execute (2) ─Resp + bit─▶ Tx (2) ─▶ txStream (128 B) ─ISR─▶ UART TX
                              ├─ bitler ─▶ Control (4)          Log (1) ─▶ logMsgs ─▶ Tx
                              └─ değer  ─▶ Setpoint (1)         B1 ─EXTI─▶ Control
```

**Parser.** Durum makinesi `SYNC0 → SYNC1 → HDR → BODY`. Durum `Receive` çağrıları arasında korunuyor; bir `Receive` dönüşü çerçeve sayılmıyor.
- **Geçerli çerçeve:** `LEN` alanı kadar bayt tüketiliyor. Bu yüzden payload içindeki `A5 5A` yeni çerçeve sanılmıyor.
- **Hata (başlık, LEN > 48, CRC):** çerçevenin ilk SYNC baytı atılıyor. Kalan baytlar küçük bir *replay* tamponuna konup baştan taranıyor. Böylece bozuk çerçevenin içine gömülü gerçek bir çerçeve kaybolmuyor; atılan tek bayt ilerlemeyi garanti ediyor.
- **Timeout:** UART ISR her baytta zaman damgası yazıyor. Yarım çerçeve varken parser yalnız "son bayttan beri kalan süre" kadar bekliyor; 100 ms dolunca yarım çerçeveyi siliyor (`to` sayacı).
  - Trigger 8/32'de `Receive` her baytta uyanmadığı için zaman `Receive`'in dönüşüne değil ISR'ın damgasına bağlı.
  - Böylece "veri yok" ile "veri var ama trigger dolmadı" durumları ayrılıyor.

**İş yolu.** Parser doğrulanmış DATA'yı önce `jobQ`'ya koyuyor, ancak kabul edilirse `xTaskNotifyGiveIndexed` yapıyor. Böylece sayaç hiçbir zaman kuyruktaki işten fazla olmuyor.
- Execute her `Take(pdFALSE)` için bir iş alıyor.
- Her iş için checksum ve SEQ hesaplıyor, 2 ms `vTaskDelay` (çevre birimi bekleme modeli) uyguluyor.
- Cevabı `respQ`'ya koyup Tx'e bit gönderiyor.

**STOP politikası.** STOP veri hattını kapatmıyor; yalnız yeni iş başlatmayı durduruyor.
- **Bekleyen işler saklanıyor (iptal yok, `jx` = 0)**; yürüyen iş bitiyor.
- STOP kontrolü ile kuyruktan alma `vTaskSuspendAll` içinde tek adım. Control (öncelik 4) araya giremiyor; STOP uygulandıktan sonra hiçbir iş başlamıyor.
  - Execute, `Take` ile işi almadan önce STOP görürse sayaç birimini geri veriyor.
- Her `R` satırında iş başladığı andaki STOP/START sayısı (`e`, `g`) var. `e == g` ⇔ iş RUNNING iken başladı; T7 bunu her cevapta kontrol ediyor.
- Saklama politikasının bedeli: STOP sürerken kuyruk 32 işte doluyor (200/s'de 160 ms). Sonrası `job_rej` olarak sayılıyor.

**TX.** UART'a yalnız Tx task'ı yazıyor (`txStream` tek yazıcı; tek okuyucu TXE kesmesi).
- Tx her satırdan önce yeniden seçiyor: önce ACK/olay notları, sonra cevaplar, en son loglar.
- Satır bölünmüyor.
- `txStream` 128 B olduğu için bir cevabın önünde en çok ~128 B bekliyor. 230400 baud'da bu yaklaşık 5,6 ms (Hafta 2'deki "büyük tampon gecikmeyi saklar" dersinin uygulaması).

## 3. Raporda istenen altı soru

**① Her buffer'ın yazıcısı / okuyucusu kim? Kuyruk elemanının sahibi kim?**

| Nesne | Yazan | Okuyan | Eleman | Doluysa |
|---|---|---|---|---|
| `rxStream` (StreamBuffer, 256/512/1024) | USART2 RX ISR | Parser | bayt | bayt reddedilir, `rej` |
| `jobQ` (32 × 60 B) | Parser | Execute | `Job` kopyası (SEQ, zaman, payload) | iş reddedilir, `jr` |
| `respQ` (16 × 28 B) | Execute | Tx | `Resp` kopyası | `rdr` |
| `noteQ` (16 × 16 B) | Parser, Control, Setpoint, Execute | Tx | `Note` kopyası | `ndr` |
| `logMsgs` (MessageBuffer 1024) | Log | Tx | ≤ 80 B satır | satır düşer, `ldr` |
| `txStream` (StreamBuffer 128) | Tx | USART2 TXE ISR | bayt | Tx bloklanır (satır bölünmez) |

Kuyruklardan geçen her şey **değer kopyası**; işaretçi yok, sahiplik devri yok. `noteQ` çok yazıcılı bir *Queue* (Queue bunu destekliyor). StreamBuffer ve MessageBuffer'ların hepsi tek yazıcı, tek okuyucu.

**② Kapasite hangi hesapla destekleniyor? Neden 1024?**
- **Normal akış:** 200 DATA/s × 44 B (32 B payload + 12) = **8 800 B/s**. UART'ın üst sınırı 230400 / 10 = 23 040 B/s.
- **Parser 80 ms durursa** (T4): 0,080 × 8 800 = **704 B** (+ 17 B STALL çerçevesi).
  - 1024 B bunu %30 payla karşılıyor.
  - 512 B bu akışta yalnız ~58 ms dayanır.
- **Hat tam hızda 80 ms dolarsa:** 1 843 B. 1024'ün bile üstünde; T5 bunu bilerek 512 ile yapıyor.
- **Sonuç:** ödevin izin verdiği en büyük değer olan 1024 seçildi. Normal akışta 80 ms'lik duraklama kayıpsız; daha büyük bir tampon yalnız gecikmeyi saklardı.
- **İş kuyruğu:** 80 ms duraklamadan sonra 16 iş aynı anda geliyor. Execute (2 ms/iş) bunları ~32 ms'de bitiriyor; 32 eleman iki katı pay.
- **RAM bütçesi (heap_4, 24 KB), hesap:**

  | Kalem | Boyut |
  |---|---|
  | Görev yığınları (2 560 word) | 10,0 KB |
  | `rxStream` | 1,0 KB |
  | `logMsgs` | 1,0 KB |
  | `jobQ` | 1,9 KB |
  | `respQ` + `noteQ` + `txStream` | ~0,9 KB |
  | Idle görevi ve TCB'ler | ~1,8 KB |
  | **Toplam** | **~16,6 KB** |

  Gerçek değer ve en düşük boş heap SNAPSHOT'tan (`heap`, `hmin`) okunacak. *Ölçülecek.*
- Stack yüksek su izi `S9` satırında. *Ölçülecek.* `-fstack-usage` en büyük çerçeveyi TxTask'ta 208 B olarak gösteriyor (`snprintf` hariç).

**③ Trigger 1, 8 ve 32 arasındaki fark?**
- **Beklenti:** `xStreamBufferReceive` buffer boş değilse hemen döner. Trigger yalnız *bloklanmış* okuyucunun kaç baytta uyandırılacağını belirler.
  - Trigger 32'de 44 B'lık bir çerçevenin son 12 baytı, okuyucu uyumuşsa bir sonraki çerçevenin baytları gelene kadar bekleyebilir. Bu, 200/s'de ~5 ms ek gecikme demek.
  - Trigger 1'de her bayt okuyucuyu uyandırabilir; bu da daha çok bağlam değişimi demek.
- Timeout ile veri durumunun nasıl ayrıldığı yukarıda (Parser) anlatıldı.
- T1'in üç turu p50/p99 farkını gösterecek. *Ölçülecek.*

**④ Sayaç, bitler ve mailbox hangi bilgiyi koruyor, hangisini kaybediyor?**

| Anlam | Koruduğu | Kaybettiği | T6'daki kanıt |
|---|---|---|---|
| Sayaç (Give/Take) | Kaç iş bekliyor | İşin kendisini taşımaz; veri `jobQ`'da | 3 iş, STEP ×4 → dönüş 3/2/1/0, kalan 2/1/0/0 |
| Bitler (eSetBits) | *Hangi* olay türleri oldu | Kaç kez ve hangi sırayla | STOP+STOP+CRC hatası → tek uyanış, bitler 0x11. STOP+START → 0x03, STOP baskın |
| Mailbox (Overwrite) | En son değer (0 dahil) | Aradaki değerler | 21, 22, 23 → yalnız 23; ardından 0 → 0 |
| WithoutOverwrite | Okunmamış değer | Yeni değer reddedilir (`pdFAIL`) | 5 beklerken 7 → `pdFAIL`, alınan 5; boşta 9 → `pdPASS` |

T6 sonuçları *ölçülecek*. Testin beklediği değerler `host/run_tests.py` içinde yazılı.

**⑤ STOP garantisi tam olarak nereden nereye?**
- **UART STOP:**
  - t0 = parser'ın CONTROL çerçevesini CRC ile doğruladığı an (TIM2, 1 µs).
  - t1 = ControlTask'ın `running = 0` yapıp LED'i söndürdüğü an.
  - Control en yüksek öncelikli görev ve bit gelince hemen uyanıyor. Beklenen gecikme mikrosaniyeler. **Hedef ≤ 50 ms, 100 tekrarın en büyüğü.** *Ölçülecek.*
- **Buton STOP:** t0 = EXTI ISR girişi; debounce 50 ms (ISR'da zaman karşılaştırması, reddedilen sekmeler `bnc`). *En az 20 basış, ölçülecek.*
- **Garantinin dışında kalanlar:**
  - host → USB → UART aktarımı;
  - komutun `rxStream`'de önündeki baytları beklemesi (dolu bir hatta yüzlerce bayt);
  - parser'ın STALL ile durması (doğrulamanın kendisi gecikir);
  - ACK satırının TX'te beklemesi;
  - buton için mekanik sekme ve kenar → ISR gecikmesi.
- Host'un "gönderdim → ACK geldi" süresi ayrıca raporlanacak. Bu, kart içi garanti değildir.

**⑥ AI önerilerinden en az ikisi nasıl doğrulandı / düzeltildi?** Ayrıntı: [AI_KULLANIMI.md](AI_KULLANIMI.md). Kısaca:
1. **İlk parser taslağı** timeout'u `Receive(…, 100 ms)` dönüşüne bağlıyordu. Trigger 8/32'de okuyucu her baytta uyanmadığı için süre "her baytta yenilenmiyordu". ISR zaman damgasına geçildi. Kanıt: T3'ün kesik çerçeve turları ve trigger turları. *Ölçülecek.*
2. **İlk Execute taslağı** `Take` ile bloklanmışken gelen STOP'tan sonra işe başlayabiliyordu. Askıya alınmış bölüm ve sayaç geri verme eklendi. Kanıt: T7'de `e == g` kontrolü. *Ölçülecek.*
3. **SNAPSHOT satırları** en kötü durumda 130 baytı aşıp 124 B'lık tamponu taşırıyordu (`snprintf` uzunluğu ile kesilmiş satır). Satır başına en çok 6 alan yapıldı ve uzunluk `configASSERT` ile korunuyor.

## 4. Sonuçlar

*Ölçülecek.* Tablo `evidence/summary.md`'den, grafikler `evidence/figures/`'dan gelecek.

## 5. Ölçümün kapsamadıkları

- Port kapatma (T8), fiziksel kablo çekme ile aynı test değil. Kart USB'den beslendiği için kabloyu çekmek kartı da kapatır.
- Oturum kimliği yazılım resetlerinde değişir (SRAM2'deki açılış sayacı). Güç kesilirse sayaç sıfırlandığı için kimlik tekrar edebilir.
- Gözlenen en büyük değerler worst-case değildir; her koşul bir kez çalıştırılacak.
