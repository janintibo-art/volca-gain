import math
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.test_audio import make_wav  # noqa: E402
from volca import audio, reglages  # noqa: E402


class TestCanaux(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.st = os.path.join(self.tmp, "st.wav")
        make_wav(self.st, secs=0.3, nch=2, rate=44100, amp=0.4)

    def test_tous_les_canaux_lisibles(self):
        for c in audio.CANAUX:
            s = audio.read_wav(self.st, canal=c)
            self.assertGreater(len(s.data), 0, c)

    def test_side_annule_le_centre(self):
        # make_wav ecrit le meme signal sur les deux canaux : side ~ silence
        s = audio.read_wav(self.st, canal="side")
        self.assertLess(s.rms_db(), -60)

    def test_mono_insensible_au_canal(self):
        m = os.path.join(self.tmp, "m.wav")
        make_wav(m, secs=0.2, nch=1)
        a = audio.read_wav(m, canal="gauche")
        b = audio.read_wav(m, canal="side")
        self.assertEqual(len(a.data), len(b.data))


class TestTraitementsFins(unittest.TestCase):
    def test_inverser(self):
        s = audio.Sample([0.5, -0.25, 0.0], 44100)
        audio.inverser(s)
        self.assertEqual(s.data, [-0.5, 0.25, 0.0])

    def test_inverser_conserve_le_niveau(self):
        s = audio.Sample([math.sin(i / 9.0) for i in range(2000)], 44100)
        avant = s.rms_db()
        audio.inverser(s)
        self.assertAlmostEqual(s.rms_db(), avant, places=6)

    def test_porte_coupe_le_souffle(self):
        souffle = [0.001] * 22050
        son = [0.5 * math.sin(i / 8.0) for i in range(22050)]
        s = audio.Sample(souffle + son, 44100)
        audio.porte(s, seuil_db=-40.0)
        debut = audio.Sample(s.data[:20000], 44100)
        self.assertLess(debut.rms_db(), -70)

    def test_porte_epargne_le_signal(self):
        s = audio.Sample([0.5 * math.sin(i / 8.0) for i in range(22050)],
                         44100)
        avant = s.rms_db()
        audio.porte(s, seuil_db=-40.0)
        self.assertAlmostEqual(s.rms_db(), avant, delta=1.5)

    def test_raccord_boucle_raccourcit(self):
        s = audio.Sample([0.3] * 44100, 44100)
        n = len(s.data)
        audio.raccord_boucle(s, 20.0)
        self.assertLess(len(s.data), n)
        self.assertGreater(len(s.data), n * 0.9)

    def test_raccord_ignore_les_samples_courts(self):
        s = audio.Sample([0.3] * 100, 44100)
        audio.raccord_boucle(s, 20.0)
        self.assertEqual(len(s.data), 100)


class TestPresetsPerso(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.f = os.path.join(self.tmp, "p.json")
        self.usine = dict(audio.PRESETS)

    def tearDown(self):
        audio.PRESETS.clear()
        audio.PRESETS.update(self.usine)

    def test_aller_retour_a_plat(self):
        for nom in ("punch", "max", "loop", "voix"):
            plat = reglages.a_plat(audio.PRESETS[nom])
            cfg = reglages.depuis_plat(audio.PRESETS[nom], plat)
            self.assertEqual(reglages.a_plat(cfg)["hp"], plat["hp"], nom)
            self.assertEqual(reglages.a_plat(cfg)["cible"], plat["cible"], nom)

    def test_sauver_puis_charger(self):
        plat = reglages.a_plat(audio.PRESETS["punch"])
        plat["hp"] = 130.0
        cfg = reglages.depuis_plat(audio.PRESETS["punch"], plat)
        reglages.sauver("essai", cfg, self.f)
        self.assertIn("essai", audio.PRESETS)
        del audio.PRESETS["essai"]
        reglages.charger(self.f)
        self.assertEqual(audio.PRESETS["essai"]["hp"], 130.0)
        self.assertTrue(audio.PRESETS["essai"]["perso"])

    def test_refuse_ecraser_un_preset_usine(self):
        with self.assertRaises(ValueError):
            reglages.sauver("punch", audio.PRESETS["punch"], self.f)

    def test_supprimer(self):
        cfg = reglages.depuis_plat(audio.PRESETS["doux"],
                                   reglages.a_plat(audio.PRESETS["doux"]))
        reglages.sauver("jetable", cfg, self.f)
        self.assertTrue(reglages.supprimer("jetable", self.f))
        self.assertNotIn("jetable", audio.PRESETS)
        self.assertFalse(reglages.supprimer("jetable", self.f))

    def test_preset_perso_utilisable(self):
        tmp = tempfile.mkdtemp()
        w = os.path.join(tmp, "a.wav")
        make_wav(w, secs=0.3, amp=0.05)
        plat = reglages.a_plat(audio.PRESETS["punch"])
        plat["cible"] = -10.0
        plat["sat_drive"] = 2.5
        cfg = reglages.depuis_plat(audio.PRESETS["punch"], plat)
        reglages.sauver("chaud", cfg, self.f)
        s = audio.read_wav(w)
        s, rap = audio.process(s, "chaud")
        self.assertLessEqual(s.peak_db(), 0.0)
        self.assertGreater(rap["gain_db"], 5)

    def test_fichier_absent(self):
        self.assertEqual(reglages.charger(self.f + "_absent"), {})


if __name__ == "__main__":
    unittest.main()
