import math
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from volca import audio, bibliotheque, pattern  # noqa: E402


def son(freq=440.0, secs=0.2, amp=0.3):
    n = int(44100 * secs)
    return audio.Sample([amp * math.sin(2 * math.pi * freq * i / 44100)
                         for i in range(n)], 44100)


def motif(nom="p", pas=None, num=3):
    m = pattern.vierge(nom)
    m.partie(1).sample_num = num
    m.partie(1).depuis_liste(pas or [1, 5, 9, 13])
    return m


class TestBibliotheque(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.b = bibliotheque.ouvrir(self.tmp)

    def test_vide_au_depart(self):
        self.assertEqual(self.b.compte(), {"patterns": 0, "sons": 0})

    def test_ajouter_pattern(self):
        e = self.b.ajouter_pattern(motif("Kick droit"))
        self.assertEqual(e["nom"], "Kick droit")
        self.assertEqual(e["parties"], 1)
        self.assertEqual(e["samples"], [3])
        self.assertTrue(os.path.isfile(self.b._chemin("patterns", e)))

    def test_ajouter_son(self):
        e = self.b.ajouter_son(son(), "Snare")
        self.assertEqual(e["nom"], "Snare")
        self.assertAlmostEqual(e["duree_ms"], 200, delta=10)
        self.assertLess(e["rms_db"], 0)

    def test_ajouter_son_depuis_fichier(self):
        f = os.path.join(self.tmp, "un son.wav")
        audio.write_wav(f, son())
        e = self.b.ajouter_son(f)
        self.assertEqual(e["nom"], "un son")

    def test_noms_en_double_acceptes(self):
        a = self.b.ajouter_son(son(), "Kick")
        c = self.b.ajouter_son(son(), "Kick")
        self.assertEqual(a["nom"], c["nom"])
        self.assertNotEqual(a["fichier"], c["fichier"])
        self.assertEqual(self.b.compte()["sons"], 2)

    def test_autonome(self):
        """Le son est copie : supprimer l'original ne casse rien."""
        f = os.path.join(self.tmp, "source.wav")
        audio.write_wav(f, son())
        e = self.b.ajouter_son(f, "Copie")
        os.remove(f)
        relu = self.b.son(e)
        self.assertGreater(len(relu.data), 0)

    def test_relecture_apres_reouverture(self):
        self.b.ajouter_pattern(motif("A"))
        self.b.ajouter_son(son(), "B")
        autre = bibliotheque.ouvrir(self.tmp)
        self.assertEqual(autre.compte(), {"patterns": 1, "sons": 1})

    def test_motif_relu_identique(self):
        m = motif("Groove", [1, 4, 7, 12])
        m.partie(1).mettre_motion("hicut", 3, 90)
        e = self.b.ajouter_pattern(m)
        r = self.b.motif(e)
        self.assertEqual(r.partie(1).liste_pas(), [1, 4, 7, 12])
        self.assertEqual(r.partie(1).motion("hicut", 3), 90)
        self.assertEqual(r.nom, "Groove")

    def test_motions_signalees(self):
        m = motif("Avec")
        m.partie(1).mettre_motion("speed", 0, 100)
        e = self.b.ajouter_pattern(m)
        self.assertIn("speed", e["motions"])

    def test_recherche(self):
        self.b.ajouter_son(son(), "Kick sub")
        self.b.ajouter_son(son(), "Snare vintage")
        self.b.ajouter_son(son(), "Kick punchy")
        self.assertEqual(len(self.b.lister("sons", "kick")), 2)
        self.assertEqual(len(self.b.lister("sons", "SNARE")), 1)
        self.assertEqual(len(self.b.lister("sons", "zzz")), 0)

    def test_tri_par_nom(self):
        self.b.ajouter_son(son(), "Zulu")
        self.b.ajouter_son(son(), "Alpha")
        noms = [e["nom"] for e in self.b.lister("sons", tri="nom")]
        self.assertEqual(noms, ["Alpha", "Zulu"])

    def test_renommer(self):
        e = self.b.ajouter_son(son(), "Ancien")
        self.b.renommer("sons", e, "Nouveau")
        autre = bibliotheque.ouvrir(self.tmp)
        self.assertEqual(autre.lister("sons")[0]["nom"], "Nouveau")

    def test_renommer_vide_refuse(self):
        e = self.b.ajouter_son(son(), "Nom")
        with self.assertRaises(ValueError):
            self.b.renommer("sons", e, "   ")

    def test_supprimer(self):
        e = self.b.ajouter_son(son(), "Jetable")
        chemin = self.b._chemin("sons", e)
        self.b.supprimer("sons", e)
        self.assertFalse(os.path.isfile(chemin))
        self.assertEqual(self.b.compte()["sons"], 0)

    def test_fichier_disparu_ignore_au_chargement(self):
        e = self.b.ajouter_son(son(), "Fantome")
        os.remove(self.b._chemin("sons", e))
        autre = bibliotheque.ouvrir(self.tmp)
        self.assertEqual(autre.compte()["sons"], 0)

    def test_index_corrompu_ne_plante_pas(self):
        self.b.ajouter_son(son(), "Un")
        with open(self.b.chemin_index, "w") as f:
            f.write("pas du json")
        autre = bibliotheque.ouvrir(self.tmp)
        self.assertEqual(autre.compte()["sons"], 0)

    def test_taille(self):
        self.b.ajouter_son(son(), "Un")
        self.assertGreater(self.b.taille_octets(), 1000)

    def test_resume(self):
        self.b.ajouter_pattern(motif("P"))
        self.b.ajouter_son(son(), "S")
        r = self.b.resume()
        self.assertIn("1 pattern", r)
        self.assertIn("S", r)

    def test_nom_de_fichier_assaini(self):
        e = self.b.ajouter_son(son(), "Nom / avec: caracteres?")
        self.assertNotIn("/", e["fichier"])
        self.assertNotIn(":", e["fichier"])
        self.assertTrue(os.path.isfile(self.b._chemin("sons", e)))


if __name__ == "__main__":
    unittest.main()
