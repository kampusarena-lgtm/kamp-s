# Eski isimlerle PanCafe kilit.png secimi — V4

79 mevcut BUSINESS / ELITE / VIP bilgisayar adi, 21 guncel gorsele eslestirilir. Bilgisayar adlari degistirilmez.

[Tum dosyalari ve 21 gorseli indir](KAMPUS_KILIT_V4_KURULUM.zip).

1. ZIP icerigini ayni klasore cikarin. BAT, PS1, CSV ve 21 JPG yan yana kalmalidir. Onerilen klasor: `C:\Program Files (x86)\Pan Group\PanCafe Pro Client\upload`.
2. Eski V3 acilis gorevini durdurun; V3 ve V4 ayni anda calismasin.
3. Once `KAMPUS_GAME_ARENA_KILIT_V4.bat -Kontrol` calistirin. Bu mod gorseli ve eslesmeyi kontrol eder, kilit dosyasini degistirmez.
4. `KAMPUS_GAME_ARENA_KILIT_V4.bat` calistirildiginda secilen JPG gercek PNG olarak donusturulur ve `C:\Program Files (x86)\Pan Group\PanCafe Pro Client\upload\kilit.png` atomik olarak degistirilir.

Eslesme yoksa, gorsel eksik/bozuksa, boyut uygun degilse, yazma yetkisi yoksa veya degistirme basarisizsa mevcut kilit.png korunur. Turuncu yedege gecis yoktur. kilit.jpg kullanilmaz. Mevcut kilit.png yoksa basarili islemde olusturulur.

Program Files klasorune yazma yetkisi gereklidir. Otomatik baslatma Gorev Zamanlayici ile uygun hesap ve en yuksek ayricaliklarla yapilabilir. PanCafe resmi okumadan once islemin tamamlanmasi gerekir; kesin acilis sirasi Windows bilgisayarda ayrica kontrol edilmelidir. Kurulum BAT dosyasi KampusArena_Kilit_V4 adli SYSTEM acilis gorevini kurar. Gorev PanCafe ile baslama sirasi garantisi vermez.

PowerShell 5.1 ve Windows System.Drawing kullanilir. BAT, ayni klasordeki PS1 yardimcisini cagirir. Windows bilgisayarda calistirma testi bu bulut ortaminda yapilmamistir; paket eslestirmeleri, kaynak gorseller ve ZIP butunlugu kontrol edilmistir.

- [Eski isimler / gorseller TXT](eski-isim-eslestirmeleri.txt)
- [Donanim ve ekipman CSV](eski-isim-eslestirmeleri.csv)

ELMAS Valorant V1.3; ZUMRUT CS:GO V1.1; PLATIN PUBG V1.1; GOLD League of Legends V1.1.

## Otomatik kurulum

ZIP dosyasini tamamen cikarin. `KURULUM_YONETICI_OLARAK_CALISTIR_V4.bat` dosyasina sag tiklayip Yonetici olarak calistir secin. Kurulum 21 gorseli, eslestirme CSV dosyasini ve secici BAT/PS1 dosyalarini upload klasorune kopyalar. Mevcut kilit.png kurulum sirasinda degistirilmez. Her acilista SYSTEM hesabi ile calisacak KampusArena_Kilit_V4 gorevi olusturulur. Ayni adli V4 gorevi varsa guncellenir. Eski V3 gorevini elle kapatin; bilinmeyen gorevler otomatik silinmez. Upload klasorundeki secici ve CSV dosyalarina yalniz yetkili kisiler yazabilmelidir.

Kurulumdan sonra BAT -Kontrol ile ilk kontrolu yapin; normal BAT calistirmasi kilit.png dosyasini gunceller. Ardindan bir bilgisayarda yeniden baslatma testi yapin. Otomatik acilisin PanCafe goruntuyu okumadan once tamamlandigini bu testte dogrulayin.

Otomatik calismayi durdurmak icin Gorev Zamanlayici icinde KampusArena_Kilit_V4 gorevini devre disi birakin.
