# Gözlemler

Ayrıntılı sayılar için: [analiz raporu](analysis/report.md).

## Ne yaptım ve nasıl çalışıyor?

FreeRTOS ile üç görevli bir sistem kurdum: TelemetryTask (öncelik 3) telemetri üretiyor, ButtonTask (öncelik 2) buton yanıtını hazırlıyor, UartTxTask (öncelik 1) UART'ı kullanan tek görev. Basıştan yanıtın son bitine kadar beş zaman damgası (t0…t4) alınıyor ve yanıt süresi R = t4 − t0. Kayıtlar deney sonunda PC'ye gönderiliyor.

Çalıştırmak için:

1. `firmware/odev01` projesini CubeIDE'de aç, `App/app_config.h` içinde `SCENARIO` seç, derle ve yükle.
2. `cd hafta-01/interface && pip install -r requirements.txt && python monitor.py` → portu seç, Connect.
3. RESET'e bas, LD2 yanınca B1'e 35 kez bas. Sonuç `measurements/Sx.csv` dosyasına kaydedilir.
4. Grafikler için: `python analysis/analyze.py`

## Ne bekledim, ne gözlemledim?

| Senaryo | Beklenti | Ölçülen |
|---|---|---|
| S0 | R ≈ 5,6 ms, sabit | 5,67 ms |
| S1→S3 | TX öncesi bekleme büyür | ort. 0,06 → 1,69 ms |
| S4 | Görev beklemesi 0–2 ms | en fazla 2,03 ms |
| S5 | Deadline aşımı olabilir | 23 yanıtın 22'si aştı, 12 yanıt kayboldu |

S0–S4'te beklentilerim tuttu. S5 beni şaşırttı: gecikme her basışta ~10 ms birikerek büyüdü. Nedeni, en düşük öncelikli UART görevinin CPU işi yüzünden periyot başına yalnızca bir mesaj gönderebilmesi. CPU %50 doluyken bile deadline kaçabiliyor.

## Çözüm olarak ne yaptım?

Ayrı bir lab derlemesinde iki çözüm denedim:

- **TC zinciri:** Sıradaki mesajı görev yerine UART'ın TC kesmesi başlatıyor, böylece hat boşta beklemiyor. Görev öncelikleri 3 > 2 > 1 kalırken de 35 yanıtın hiçbiri 20 ms'yi aşmadı (en büyük R 16,4 ms).
- **UART ve ButtonTask önceliğini CPU işinin üstüne almak:** UART sıradaki mesajı hesaplamayı kısa süre keserek başlatıyor, ButtonTask da artık hesaplamayı beklemiyor. En büyük R 10,3 ms'ye indi.
