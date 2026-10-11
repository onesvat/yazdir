# Linux'ta HP LaserJet 1018

*[English](hp-laserjet-1018.md)*

Yazdır, bir HP LaserJet 1018 üzerinde geliştirildi (Fedora 43, HPLIP 3.26). Yazıcıyı çalıştıran adımlar aşağıda.
Firmware yüklemesi gereken 1020, 1022 ve P1005/P1505/P1102 ailesi için de aynısı geçerli.

## 1. `hpijs` yerine `hpcups` sürücüsünü kullanın

İşler şu hatayla kayboluyorsa

```
foomatic-rip: ERROR: The value of the key FoomaticRIPOptionSetting is not among the allowed values
```

kuyruk eski foomatic/`hpijs` PPD'sini kullanıyordur. `hpcups`'a geçirin:

```sh
sudo lpadmin -p HP-LaserJet-1018 -m drv:///hp/hpcups.drv/hp-laserjet_1018.ppd -E
```

(Kullanılabilir sürücüleri `lpinfo -m | grep 1018` listeler.)

## 2. HP eklentisini kurun

1018'in kendi firmware'i yok; HPLIP her açılışta gönderiyor ve bu firmware HP'nin kapalı kaynak eklentisinde.

```sh
sudo hp-plugin -i
```

İndirme başarısız olursa ("download 0"), HPLIP sürümünüze uyan eklentiyi elle indirip `hp-plugin`'e gösterin:

```sh
v=3.26.4   # HPLIP sürümünüz: rpm -q hplip  ya da  dpkg -l hplip
mkdir -p ~/hplip-plugin && cd ~/hplip-plugin
curl -fLO https://www.openprinting.org/download/printdriver/auxfiles/HP/plugins/hplip-$v-plugin.run
curl -fLO https://www.openprinting.org/download/printdriver/auxfiles/HP/plugins/hplip-$v-plugin.run.asc
sudo hp-plugin -i -p ~/hplip-plugin/
```

## 3. Firmware'i yükleyin

```sh
sudo hp-firmware -n
```

HPLIP'in udev kuralı bunu yazıcı açılınca ya da takılınca kendiliğinden yapar. Kapat-aç sonrası ilk iş hiçbir şey basmazsa yukarıdaki komutu çalıştırın.

## 4. Arkalı önlü baskı

1018'de arkalı önlü ünitesi yok. Yazdır'ın **Arkalı önlü (elle)** ya da **Kitapçık** modunu kullanın. Varsayılan ayar
(*2. turda sırayı ters çevir* ve *arka yüzü 180° döndür*) bu yazıcının kâğıt yoluna uyar:

- besleme tepsisi önce **en üstteki** kâğıdı, basılacak yüz yukarıda ve ön kenarı önde olacak şekilde çeker;
- basılan kâğıtlar üstteki çıktı tepsisine **yüzü aşağı**, ön kenarı yazıcıya doğru çıkar;
- desteyi alıp **ters çevirmeden ve döndürmeden** besleme tepsisine geri koyarsınız.

Böylece son basılan kâğıt yeniden beslemede ilk girer (sıranın ters çevrilmesi bu yüzden) ve arka yüz karşı kenardan başlayarak
basılır (kitap gibi okumak için 180° döndürme bu yüzden).
