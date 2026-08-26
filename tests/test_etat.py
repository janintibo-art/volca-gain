import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from volca import etat  # noqa: E402


class TestEtat(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.f = os.path.join(self.tmp, "etat.json")
        self.projet = os.path.join(self.tmp, "kit.volca.json")
        with open(self.projet, "w") as fh:
            fh.write("{}")

    def test_aller_retour(self):
        self.assertTrue(etat.memoriser_projet(self.projet, self.f))
        self.assertEqual(etat.dernier_projet(self.f), self.projet)

    def test_fichier_absent(self):
        self.assertIsNone(etat.dernier_projet(self.f))

    def test_projet_disparu_ignore(self):
        etat.memoriser_projet(self.projet, self.f)
        os.remove(self.projet)
        self.assertIsNone(etat.dernier_projet(self.f))

    def test_oublier(self):
        etat.memoriser_projet(self.projet, self.f)
        etat.oublier(self.f)
        self.assertIsNone(etat.dernier_projet(self.f))

    def test_fichier_corrompu_ne_plante_pas(self):
        with open(self.f, "w") as fh:
            fh.write("ceci n'est pas du json")
        self.assertIsNone(etat.dernier_projet(self.f))
        self.assertTrue(etat.memoriser_projet(self.projet, self.f))
        self.assertEqual(etat.dernier_projet(self.f), self.projet)

    def test_ecrase_le_precedent(self):
        autre = os.path.join(self.tmp, "autre.volca.json")
        with open(autre, "w") as fh:
            fh.write("{}")
        etat.memoriser_projet(self.projet, self.f)
        etat.memoriser_projet(autre, self.f)
        self.assertEqual(etat.dernier_projet(self.f), autre)


if __name__ == "__main__":
    unittest.main()
