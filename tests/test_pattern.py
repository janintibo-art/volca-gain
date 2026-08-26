import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from volca import pattern  # noqa: E402


class TestFormat(unittest.TestCase):
    """La taille et les marqueurs sont imposes par le SDK Korg."""

    def test_taille_exacte(self):
        self.assertEqual(len(pattern.vierge().to_bytes()), 0xA40)
        self.assertEqual(pattern.TAILLE, 2624)

    def test_taille_partie(self):
        self.assertEqual(len(pattern.Partie().to_bytes()), 0x100)
        self.assertEqual(pattern.TAILLE_PARTIE * pattern.NB_PARTIES, 0xA00)

    def test_marqueurs(self):
        b = pattern.vierge().to_bytes()
        self.assertEqual(b[:4], b"PTST")
        self.assertEqual(b[-4:], b"PTED")

    def test_devcode(self):
        b = pattern.vierge().to_bytes()
        self.assertEqual(int.from_bytes(b[4:6], "little"), 0x33B8)

    def test_premiere_partie_a_0x20(self):
        m = pattern.vierge()
        m.partie(1).sample_num = 0x1234
        b = m.to_bytes()
        self.assertEqual(int.from_bytes(b[0x20:0x22], "little"), 0x1234)

    def test_partie_10_bien_placee(self):
        m = pattern.vierge()
        m.partie(10).sample_num = 42
        b = m.to_bytes()
        d = 0x20 + 9 * 0x100
        self.assertEqual(int.from_bytes(b[d:d + 2], "little"), 42)


class TestPas(unittest.TestCase):
    def setUp(self):
        self.p = pattern.Partie()

    def test_liste_et_masque(self):
        self.p.depuis_liste([1, 5, 9, 13])
        self.assertEqual(self.p.pas, 0b0001000100010001)
        self.assertEqual(self.p.liste_pas(), [1, 5, 9, 13])

    def test_basculer(self):
        self.p.basculer_pas(0)
        self.assertTrue(self.p.pas_actif(0))
        self.p.basculer_pas(0)
        self.assertFalse(self.p.pas_actif(0))

    def test_pas_16(self):
        self.p.depuis_liste([16])
        self.assertEqual(self.p.pas, 0x8000)

    def test_hors_limites(self):
        with self.assertRaises(ValueError):
            self.p.mettre_pas(16)

    def test_vide(self):
        self.assertTrue(self.p.vide())
        self.p.mettre_pas(3)
        self.assertFalse(self.p.vide())


class TestFonctions(unittest.TestCase):
    def test_bits(self):
        p = pattern.Partie()
        p.mettre("loop")
        p.mettre("reverse")
        self.assertEqual(p.func, 0b1010)
        self.assertTrue(p.actif("loop"))
        self.assertFalse(p.actif("mute"))

    def test_retirer(self):
        p = pattern.Partie()
        p.mettre("reverb")
        p.mettre("reverb", False)
        self.assertEqual(p.func, 0)


class TestAllerRetour(unittest.TestCase):
    def setUp(self):
        self.m = pattern.vierge("essai")
        self.m.partie(1).depuis_liste([1, 5, 9, 13])
        self.m.partie(1).sample_num = 3
        self.m.partie(2).depuis_liste([5, 13])
        self.m.partie(2).sample_num = 199
        self.m.partie(2).mettre("reverse")
        self.m.partie(3).params["speed"] = 80
        self.m.partie(3).level = 100
        self.m.partie(3).depuis_liste([2])
        self.m.parties[4].motion[3][7] = 99

    def test_octets_identiques(self):
        r = pattern.Motif.from_bytes(self.m.to_bytes())
        self.assertEqual(r.to_bytes(), self.m.to_bytes())

    def test_valeurs_conservees(self):
        r = pattern.Motif.from_bytes(self.m.to_bytes())
        self.assertEqual(r.partie(1).liste_pas(), [1, 5, 9, 13])
        self.assertEqual(r.partie(2).sample_num, 199)
        self.assertTrue(r.partie(2).actif("reverse"))
        self.assertEqual(r.partie(3).params["speed"], 80)
        self.assertEqual(r.partie(3).level, 100)
        self.assertEqual(r.parties[4].motion[3][7], 99)

    def test_fichier(self):
        tmp = tempfile.mkdtemp()
        f = os.path.join(tmp, "p.dat")
        self.m.sauver(f)
        self.assertEqual(os.path.getsize(f), 2624)
        r = pattern.Motif.charger(f)
        self.assertEqual(r.to_bytes(), self.m.to_bytes())
        self.assertEqual(r.nom, "p")


class TestRefus(unittest.TestCase):
    def test_taille_invalide(self):
        with self.assertRaises(pattern.FormatInvalide):
            pattern.Motif.from_bytes(b"\x00" * 100)

    def test_entete_absente(self):
        b = bytearray(pattern.vierge().to_bytes())
        b[0] = 0
        with self.assertRaises(pattern.FormatInvalide):
            pattern.Motif.from_bytes(bytes(b))

    def test_pied_absent(self):
        b = bytearray(pattern.vierge().to_bytes())
        b[-1] = 0
        with self.assertRaises(pattern.FormatInvalide):
            pattern.Motif.from_bytes(bytes(b))

    def test_partie_hors_limites(self):
        m = pattern.vierge()
        with self.assertRaises(ValueError):
            m.partie(11)
        with self.assertRaises(ValueError):
            m.partie(0)


class TestConfort(unittest.TestCase):
    def test_parties_utilisees(self):
        m = pattern.vierge()
        self.assertEqual(m.parties_utilisees(), [])
        m.partie(4).depuis_liste([1])
        self.assertEqual(len(m.parties_utilisees()), 1)

    def test_vider(self):
        m = pattern.vierge()
        m.partie(1).depuis_liste([1, 2, 3])
        m.vider()
        self.assertEqual(m.parties_utilisees(), [])
        self.assertEqual(len(m.to_bytes()), 2624)

    def test_grille(self):
        m = pattern.vierge()
        m.partie(1).depuis_liste([1])
        g = m.grille()
        self.assertIn("X", g)
        self.assertEqual(len(g.splitlines()), 11)

    def test_infos(self):
        tmp = tempfile.mkdtemp()
        f = os.path.join(tmp, "p.dat")
        m = pattern.vierge()
        m.partie(1).sample_num = 5
        m.partie(1).depuis_liste([1, 9])
        m.sauver(f)
        i = pattern.infos(f)
        self.assertEqual(i["parties"], 1)
        self.assertEqual(i["samples"], [5])
        self.assertEqual(i["pas_actifs"], 16)

    def test_valeurs_bornees(self):
        p = pattern.Partie()
        p.params["level"] = 999
        self.assertEqual(p.to_bytes()[9], 127)


if __name__ == "__main__":
    unittest.main()


class TestRendu(unittest.TestCase):
    """Ecoute d'un pattern : melange des sons aux bons instants."""

    def setUp(self):
        import math
        sys.path.insert(0, os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))))
        from volca import audio
        self.audio = audio
        n = int(44100 * 0.1)
        self.sons = {
            3: audio.Sample([0.5 * math.sin(i / 30.0) for i in range(n)],
                            44100),
            7: audio.Sample([0.3 * math.sin(i / 8.0) for i in range(n)],
                            44100),
        }
        self.m = pattern.vierge("essai")
        self.m.partie(1).sample_num = 3
        self.m.partie(1).depuis_liste([1, 5, 9, 13])

    def test_duree_selon_le_tempo(self):
        a = pattern.rendu(self.m, self.sons, 120)
        b = pattern.rendu(self.m, self.sons, 240)
        self.assertGreater(a.duration_ms, b.duration_ms)
        # 16 pas de double croche a 120 bpm = 2 s, plus la queue du son
        self.assertGreater(a.duration_ms, 2000)
        self.assertLess(a.duration_ms, 2300)

    def test_pattern_vide_est_silencieux(self):
        r = pattern.rendu(pattern.vierge(), self.sons)
        self.assertEqual(r.peak(), 0.0)

    def test_partie_muette_ignoree(self):
        avec = pattern.rendu(self.m, self.sons, 120).rms_db()
        self.m.partie(1).mettre("mute")
        sans = pattern.rendu(self.m, self.sons, 120)
        self.assertEqual(sans.peak(), 0.0)
        self.assertGreater(avec, -100)

    def test_sample_absent_ignore(self):
        self.m.partie(2).sample_num = 99
        self.m.partie(2).depuis_liste([3])
        r = pattern.rendu(self.m, self.sons, 120)
        self.assertGreater(r.peak(), 0.0)

    def test_pas_de_saturation(self):
        for i in range(1, 6):
            self.m.partie(i).sample_num = 3
            self.m.partie(i).depuis_liste(list(range(1, 17)))
        r = pattern.rendu(self.m, self.sons, 120)
        self.assertLessEqual(r.peak_db(), 0.0)

    def test_niveau_pris_en_compte(self):
        fort = pattern.rendu(self.m, self.sons, 120).rms_db()
        self.m.partie(1).level = 20
        faible = pattern.rendu(self.m, self.sons, 120)
        self.assertGreater(fort, -100)
        self.assertGreater(faible.peak(), 0.0)

    def test_reverse(self):
        self.m.partie(1).mettre("reverse")
        r = pattern.rendu(self.m, self.sons, 120)
        self.assertGreater(r.peak(), 0.0)
