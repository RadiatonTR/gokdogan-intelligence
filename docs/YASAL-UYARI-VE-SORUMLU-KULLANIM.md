# Yasal Uyarı ve Sorumlu Kullanım

## Genel amaç

Gökdoğan Intelligence açık kaynak bilgi toplama, görselleştirme ve durum farkındalığı amacıyla geliştirilmiştir. Uygulama, üçüncü taraf sistemlere yetkisiz erişim sağlama veya erişim kontrolünü aşma amacı taşımaz.

## Kullanıcının sorumluluğu

Kullanıcı;

- ülkesindeki ve verinin toplandığı/yayımlandığı ülkedeki hukuka,
- üçüncü taraf sağlayıcıların kullanım şartlarına,
- telif, veri tabanı hakkı ve atıf şartlarına,
- kişisel verilerin korunması ve mahremiyet yükümlülüklerine

uymaktan sorumludur.

## Yasaklanan / desteklenmeyen kullanım örnekleri

- özel veya kapalı kameralara yetkisiz erişim,
- parola/kimlik doğrulama aşma,
- kişi hedefli gizli takip, taciz veya stalking,
- kolluk kuvvetlerinden kaçınmak için gerçek zamanlı takip,
- kamuya açık askerî/stratejik veriyi operasyonel hedefleme veya zarar verme amacıyla kullanma,
- üçüncü taraf API kotası/erişim kısıtını atlatma,
- veri sağlayıcının lisansını ihlal ederek yeniden dağıtım.

## Askerî ve stratejik veriler

Uygulamada görünen askerî hava aracı, altyapı veya üs/reference bilgileri yalnız kamuya açık veri setlerinden gelebilir. Bu görünüm:

- gizli tesis keşfi,
- kapalı telemetri elde etme,
- gerçek zamanlı hedefleme,
- operasyonel saldırı planlama

için tasarlanmamıştır.

## Kamera verileri

GitHub deposu canlı üçüncü taraf kamera karelerini yeniden yayımlamamalıdır. Uygulama yalnız kamu/yetkili kaynak URL'sini açmalı veya sağlayıcının izin verdiği API üzerinden görüntülemelidir.

## Veri doğruluğu

Gökdoğan'daki bilgiler:

- gecikmeli,
- eksik,
- yanlış sınıflandırılmış,
- geçici olarak çevrimdışı,
- önbellekten

olabilir. Acil durum, seyrüsefer, güvenlik, sağlık, yatırım veya resmî karar için tek kaynak olarak kullanılmamalıdır.

## Finansal uyarı

Piyasa verileri bilgilendirme amaçlıdır; yatırım tavsiyesi değildir.

## Garanti reddi

Yazılım AGPL-3.0 kapsamında sunulur. Uygulama ve üçüncü taraf veriler için kesintisiz erişim, doğruluk veya belirli bir amaca uygunluk garantisi verilmez.

## Güvenlik açığı bildirimi

Hassas güvenlik açığını herkese açık issue içinde API anahtarı veya istismar ayrıntısıyla paylaşmayın. Projenin [`../SECURITY.md`](../SECURITY.md) politikasını izleyin.
