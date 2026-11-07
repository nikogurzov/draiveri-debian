import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import jezgro as j

LSPCI = """Slot:\t01:00.0
Class:\tVGA compatible controller [0300]
Vendor:\tNVIDIA Corporation [10de]
Device:\tGB206M [GeForce RTX 5070] [2d18]
Driver:\tnvidia
Module:\tnvidiafb, nouveau, nvidia

Slot:\t02:00.0
Class:\tNetwork controller [0280]
Vendor:\tIntel Corporation [8086]
Device:\tWi-Fi 6 [2725]
Module:\tiwlwifi

Slot:\t03:00.0
Class:\tEthernet controller [0200]
Vendor:\tSome [1234]
Device:\tThing [5678]

Slot:\t00:14.0
Class:\tEncryption controller [1080]
Vendor:\tAMD [1022]
Device:\tPSP [1649]
"""


class T(unittest.TestCase):
    def test_lspci(self):
        d = j.parse_lspci(LSPCI)
        self.assertEqual(4, len(d))
        self.assertEqual(("nvidia", j.OK), (d[0].driver, d[0].state))
        self.assertEqual("NVIDIA Corporation GB206M [GeForce RTX 5070]", d[0].name)
        self.assertEqual("VGA compatible controller", d[0].kind)

    def test_only_important_devices_warn(self):
        d = j.parse_lspci(LSPCI)
        self.assertEqual(j.WARN, d[1].state)
        self.assertIn("iwlwifi", d[1].note)
        self.assertEqual(j.WARN, d[2].state)
        self.assertIn("Няма драйвер", d[2].note)
        self.assertEqual(j.INFO, d[3].state)      # без драйвер, но не е тревога

    def test_modules(self):
        m = j.parse_modules("nvidia 12345678 42 - Live 0x0\nsnd 2048 3 a,b, Live 0x0\nbad line\n")
        self.assertEqual(["nvidia", "snd"], [x.name for x in m])
        self.assertEqual(2, m[1].size_kb)
        self.assertEqual(42, m[0].used)

    def test_packages_filter(self):
        t = "firmware-realtek\t2024\tRealtek firmware\tii \nvim\t9\teditor\tii \nnvidia-driver:amd64\t550\tdriver\tii \nfirmware-old\t1\tx\trc \nsome-dkms\t1\tmod\tii \n"
        self.assertEqual(["firmware-realtek", "nvidia-driver", "some-dkms"], [p.name for p in j.parse_packages(t)])

    def test_firmware_log(self):
        log = "\n".join(["kernel: bluetooth hci0: Direct firmware load for rtl_bt/rtl8852bu_fw.bin failed with error -2",
                         "kernel: i915 0000:00:02.0: firmware: failed to load i915/adlp_dmc.bin (-2)",
                         "kernel: iwlwifi: Failed to load firmware \"iwlwifi-so-a0-gf-a0-89.ucode\"",
                         "kernel: bluetooth hci0: Direct firmware load for rtl_bt/rtl8852bu_fw.bin failed with error -2",
                         "kernel: nothing here"])
        self.assertEqual(["rtl_bt/rtl8852bu_fw.bin", "i915/adlp_dmc.bin", "iwlwifi-so-a0-gf-a0-89.ucode"], j.parse_firmware_log(log))

    def test_firmware_package(self):
        self.assertEqual("firmware-realtek", j.firmware_package("rtl_bt/x.bin"))
        self.assertEqual("firmware-iwlwifi", j.firmware_package("iwlwifi-so.ucode"))
        self.assertEqual("firmware-amd-graphics", j.firmware_package("amdgpu/x.bin"))
        self.assertEqual("", j.firmware_package("unknown/x.bin"))

    def test_firmware_findings(self):
        no = lambda n: False
        f = j.firmware_findings(["rtl_bt/x.bin"], set(), no)
        self.assertEqual((j.WARN, "firmware-realtek"), (f[0].level, f[0].package))
        f = j.firmware_findings(["rtl_bt/x.bin"], {"firmware-realtek"}, no)
        self.assertEqual(j.INFO, f[0].level)       # пакетът го има: не вдигаме тревога
        self.assertEqual([], j.firmware_findings(["rtl_bt/x.bin"], set(), lambda n: True))
        self.assertEqual(j.INFO, j.firmware_findings(["zzz.bin"], set(), no)[0].level)

    def test_gpu(self):
        d = [j.Device("PCI", "VGA compatible controller", "NVIDIA RTX", "nvidia")]
        self.assertEqual(j.OK, j.gpu_findings(d, "550.1", set())[0].level)
        self.assertIn("550.1", j.gpu_findings(d, "550.1", set())[0].detail)
        d[0].driver = "nouveau"
        self.assertEqual(j.INFO, j.gpu_findings(d, "", set())[0].level)
        d[0].driver = ""
        self.assertEqual(j.WARN, j.gpu_findings(d, "", set())[0].level)
        self.assertEqual([], j.gpu_findings([j.Device("PCI", "VGA", "AMD Radeon", "amdgpu")], "", set()))

    def test_verdict(self):
        r = j.Report()
        self.assertEqual(j.OK, j.verdict(r)[0])
        r.findings = [j.Finding(j.INFO, "a", "b")]
        self.assertEqual(j.OK, j.verdict(r)[0])
        r.findings = [j.Finding(j.WARN, "a", "b")]
        self.assertEqual(j.WARN, j.verdict(r)[0])
        self.assertIn("1", j.verdict(r)[1])
        self.assertEqual(j.INFO, j.verdict(j.Report(limits=["x"]))[0])

    def test_findings_order(self):
        s = j.summary_findings([j.Device("PCI", "Network", "Wi", "", "", j.WARN, "няма")], [j.Finding(j.OK, "g", ""), j.Finding(j.INFO, "i", "")])
        self.assertEqual([j.WARN, j.OK, j.INFO], [x.level for x in s])

    def test_run_missing_command(self):
        self.assertIsNone(j.run(["komanda-koyato-ya-nyama-xyz"]))


if __name__ == "__main__":
    unittest.main()
