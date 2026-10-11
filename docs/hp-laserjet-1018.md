# HP LaserJet 1018 on Linux

*[Türkçe](hp-laserjet-1018.tr.md)*

Yazdır was built on an HP LaserJet 1018 (Fedora 43, HPLIP 3.26). These are the steps that got the printer working.
The same applies to the 1020, 1022 and P1005/P1505/P1102 family, which also need a firmware upload.

## 1. Use the `hpcups` driver, not `hpijs`

If jobs disappear with

```
foomatic-rip: ERROR: The value of the key FoomaticRIPOptionSetting is not among the allowed values
```

the queue uses the old foomatic/`hpijs` PPD. Switch it to `hpcups`:

```sh
sudo lpadmin -p HP-LaserJet-1018 -m drv:///hp/hpcups.drv/hp-laserjet_1018.ppd -E
```

(`lpinfo -m | grep 1018` lists the available drivers.)

## 2. Install the HP plugin

The 1018 has no firmware of its own; HPLIP sends it on every power-up, and that firmware ships in HP's proprietary plugin.

```sh
sudo hp-plugin -i
```

If the download fails ("download 0"), fetch the plugin matching your HPLIP version manually and point `hp-plugin` at it:

```sh
v=3.26.4   # your HPLIP version: rpm -q hplip  or  dpkg -l hplip
mkdir -p ~/hplip-plugin && cd ~/hplip-plugin
curl -fLO https://www.openprinting.org/download/printdriver/auxfiles/HP/plugins/hplip-$v-plugin.run
curl -fLO https://www.openprinting.org/download/printdriver/auxfiles/HP/plugins/hplip-$v-plugin.run.asc
sudo hp-plugin -i -p ~/hplip-plugin/
```

## 3. Load the firmware

```sh
sudo hp-firmware -n
```

HPLIP's udev rule does this automatically when the printer is switched on or plugged in. If the first job after a power cycle produces nothing, run the command above.

## 4. Two-sided printing

The 1018 has no duplex unit. Use Yazdır's **Two-sided (manual)** or **Booklet** mode. The default calibration
(*reverse order in the second pass* and *rotate backs 180°*) matches this printer's paper path:

- the input tray feeds the **top** sheet first, printed side up, leading edge first;
- printed sheets come out on top **face down**, leading edge towards the printer;
- you take the stack and put it back into the input tray **without flipping or rotating it**.

So the last printed sheet is the first one fed again (hence the reverse order), and the back is printed starting from the
opposite edge (hence the 180° turn for book-style reading).
