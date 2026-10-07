# PC19 PRL deneme paketleri

Bu sürüm **mining çalıştırmaz**. İlk cihaz PC19-BUSINESS (RTX 5060 Ti); ayrı panel 192.168.1.77 adresindeki PanCafe bilgisayarında açılır. Netkafem sunucusu ayrıdır.

## İndir

- [Kasa paneli ZIP](KASA_192-168-1-77_DENEME.zip)
- [PC19 deneme ZIP](PC19_BUSINESS_DENEME.zip)
- [SHA-256 dosya özetleri](SHA256SUMS.txt)

GitHub ZIP dosyası sayfasında **Download raw file** ile gerçek ZIP indirilir.

## Kasada: 192.168.1.77

1. Kasa ZIP'ini aç; içindeki CafeMining klasörünü yerel diske `C:\CafeMining` olarak çıkar.
2. Python 3.11+ ve `py` başlatıcısı gerekir. Python yoksa [resmî Windows kurulumu](https://www.python.org/downloads/windows/) kullanılır. `ONKOSULLAR.bat` Pillow kurar.
3. `PANEL_DEMO.bat` ile arayüzü görebilirsin. Gerçek bağlantı için `KASA-HAZIRLA.bat`, ardından `PANEL.bat` aç. Genel durdurmayı açık bırak.
4. Kasa PC'de TCP 8790 erişimi yalnızca kafe yerel ağı için sağlanır. Bu paket güvenlik duvarını değiştirmez veya internet portu açmaz.
5. Kasada oluşan `C:\CafeMining\panel_private\agent_settings\PC19-BUSINESS.json` dosyasını yalnızca PC19'a aktar.

## PC19-BUSINESS

1. PC19 ZIP'ini aç; CafeMining klasörünü `C:\CafeMining` olarak çıkar.
2. Kasadan aldığın PC19-BUSINESS.json dosyasını `C:\CafeMining\device-settings` içine koy. Diğer cihaz dosyalarını kopyalama.
3. Python ön koşulunu hazırla; `ONKOSULLAR.bat` aç. Ajan zaten açıksa önce onu kapat. Yerel Windows kullanıcı oturumunda dene.
4. Kasada PANEL.bat açıkken PC19'da `PC19-DENEME.bat` aç. Önce 1 (boş kilit ekranı), sonra 2 (müşteri masaüstü) dene. Seçimden sonraki beş saniye içinde ilgili ekranı öne getir; yaklaşık bir dakika bekle, sonra konsola dön.
5. Sonuçlar `%LOCALAPPDATA%\CafeMining\diagnostics` içindedir. Boş ekran denemesinde `panel_connection_pass=true` ve `image_candidate_pass=true` beklenir. Müşteri ekranında `matched_samples=0` olmalıdır. Yakalama hatası başarılı ayrım sayılmaz; kalibrasyon kendiliğinden açılmaz.

Netkafem yazma önbelleği silinebilir. Pilot ayar PC19'a özel sağlanır; kasanın panel_private klasörü ve tüm anahtarlar ortak Windows imajına eklenmez. Kalıcı imaj düzeni gerçek Netkafem kurulum akışında ayrıca yapılır.

## Merkezi kaydın kalıcılığı

Kasada panel açılıp kapatıldıktan sonra, panel kapalıyken `py -3 storage_check.py arm` çalıştır. Windows'u normal yeniden başlat; paneli açmadan `py -3 storage_check.py verify` çalıştır. Araç aynı kayıt dosyasının farklı Windows açılışında kaldığını kontrol eder; kendisi reboot vermez. `state_storage_verified=false` varsayılandır ve test tamamlanmadan değiştirilmez.

## Paket kapsamı

İndirme dosyalarında cihaz anahtarları, kişisel ödeme cüzdanı ve miner EXE yoktur. Anahtarlar ilk kasa hazırlığında yerel olarak oluşturulur. Bütün cihaz ayarları deneme modunda hazırlanır. Tanılama mining, OC, monitör veya reset komutu vermez; ekran görüntüsü ve cihaz anahtarını rapora yazmaz.

Gerçek Windows/Netkafem/OC/miner/havuz çalışması henüz doğrulanmadı. Kalibrasyon, monitör kapalıyken yakalama, güncel gelir verisi ve doğrulanmış OC aracı canlı mining öncesinde ayrıca hazırlanmalıdır.
