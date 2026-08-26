import os
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.test_audio import make_wav  # noqa: E402
from volca import audio, kit, project  # noqa: E402


class TestKit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.a = os.path.join(self.tmp, "un son.wav")
        make_wav(self.a, secs=0.4, amp=0.05, freq=220.0)
        self.b = os.path.join(self.tmp, "deux.wav")
        make_wav(self.b, secs=0.3, amp=0.4, freq=880.0)
        self.p = project.Projet("mon kit")
        self.p.assigner(0, self.a, "max")
        self.p.assigner(7, self.b, "punch", -2.0)
        self.zip = os.path.join(self.tmp, "k.zip")

    def test_export_contenu(self):
        kit.exporter(self.p, self.zip)
        noms = zipfile.ZipFile(self.zip).namelist()
        self.assertIn(kit.NOM_PROJET, noms)
        self.assertIn("LISEZMOI.txt", noms)
        self.assertEqual(sum(1 for n in noms if n.endswith(".wav")), 2)

    def test_nom_de_fichier_assaini(self):
        kit.exporter(self.p, self.zip)
        for n in zipfile.ZipFile(self.zip).namelist():
            self.assertNotIn(" ", n)

    def test_infos(self):
        kit.exporter(self.p, self.zip)
        i = kit.infos(self.zip)
        self.assertEqual(i["nom"], "mon kit")
        self.assertEqual(i["slots"], 2)
        self.assertTrue(i["traite"])

    def test_aller_retour(self):
        kit.exporter(self.p, self.zip)
        q = kit.importer(self.zip, os.path.join(self.tmp, "recu"))
        self.assertEqual(len(q.occupes()), 2)
        self.assertEqual([s.index for s in q.occupes()], [0, 7])
        for s in q.occupes():
            self.assertTrue(os.path.isfile(s.chemin))

    def test_sons_deja_traites(self):
        """Le son exporte doit etre bien plus fort que l'original faible."""
        kit.exporter(self.p, self.zip)
        q = kit.importer(self.zip, os.path.join(self.tmp, "recu"))
        avant = audio.read_wav(self.a).rms_db()
        apres = audio.read_wav(q.slots[0].chemin).rms_db()
        self.assertGreater(apres, avant + 10)
        self.assertEqual(q.slots[0].preset, "doux")
        self.assertEqual(q.slots[0].gain_db, 0.0)

    def test_export_brut_conserve_les_reglages(self):
        kit.exporter(self.p, self.zip, traiter=False)
        q = kit.importer(self.zip, os.path.join(self.tmp, "recu"))
        self.assertEqual(q.slots[7].preset, "punch")
        self.assertEqual(q.slots[7].gain_db, -2.0)

    def test_taux_conserve(self):
        self.p.slots[0].taux = 22050
        kit.exporter(self.p, self.zip)
        q = kit.importer(self.zip, os.path.join(self.tmp, "recu"))
        self.assertEqual(q.slots[0].taux, 22050)

    def test_projet_vide_refuse(self):
        with self.assertRaises(ValueError):
            kit.exporter(project.Projet("vide"), self.zip)

    def test_zip_quelconque_refuse(self):
        faux = os.path.join(self.tmp, "faux.zip")
        with zipfile.ZipFile(faux, "w") as z:
            z.writestr("bidon.txt", "rien")
        with self.assertRaises(ValueError):
            kit.infos(faux)
        with self.assertRaises(ValueError):
            kit.importer(faux, self.tmp)

    def test_projet_sauve_a_l_import(self):
        kit.exporter(self.p, self.zip)
        q = kit.importer(self.zip, os.path.join(self.tmp, "recu"))
        self.assertTrue(os.path.isfile(q.chemin_fichier))
        r = project.Projet.charger(q.chemin_fichier)
        self.assertEqual(len(r.occupes()), 2)

    def test_progression(self):
        vus = []
        kit.exporter(self.p, self.zip,
                     progression=lambda n, t, s: vus.append(n))
        self.assertEqual(vus, [1, 2])


if __name__ == "__main__":
    unittest.main()
