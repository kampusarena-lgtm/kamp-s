# Python kurulumu gerektirmeyen Windows sürümü

Bu klasördeki ZIP dosyaları GitHub Windows ortamında derleme ve paket açılış kontrolleri başarılı olduğunda yayımlanır.

- **KASA_WINDOWS.zip:** ZIP içindeki CafeMining klasörünün tamamını kasada C:\CafeMining olarak çıkar; Panel.exe aç. İlk açılışta cihaz ayarları ve anahtarlar kasada oluşturulur. Genel durdurmayı açık bırak.
- Kasada oluşan panel_private\agent_settings\PC19-BUSINESS.json dosyasını yalnızca PC19'un device-settings klasörüne aktar.
- **PC19_WINDOWS.zip:** Klasörün tamamını PC19'da C:\CafeMining olarak çıkar; PC19Deneme.exe aç. Menüden önce boş ekranı, sonra müşteri ekranını dene.

Python/pip kurulumu veya py komutu gerekmez. EXE'nin yanındaki DLL ve klasörleri birlikte tut; yalnız EXE dosyasını taşıma. Panel ilk açılışta 192.168.1.77:8790 adresinde ajanları bekler. Güvenlik duvarı bu uygulama tarafından değiştirilmez.

Bu sürüm yalnızca deneme yapar: mining, OC, monitör kapatma veya reset komutu verilmez. Kafe bilgisayarlarında gerçek ekran/Netkafem davranışı ayrıca doğrulanmalıdır. KayitKontrol.exe kasadaki kaydın normal Windows yeniden başlatmasında korunmasını iki aşamada kontrol eder; kendisi reboot yapmaz.

İndirmeler gizli cihaz anahtarı ve kişisel ödeme cüzdanı içermez. Kasa tarafından üretilen panel_private klasörünü diğer PC'lere/ortak imaja kopyalama. Özetler SHA256SUMS.txt dosyasındadır.
