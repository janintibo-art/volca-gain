import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.test_audio import make_wav  # noqa: E402
from volca import audio, project  # noqa: E402


class TestProjet(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.wav = os.path.join(self.tmp, "s.wav")
        make_wav(self.wav, secs=0.5, amp=0.2)

    def test_assigner_et_vider(self):
        p = project.Projet("t")
        p.assigner(3, self.wav)
        self.assertEqual(len(p.occupes()), 1)
        self.assertFalse(p.slots[3].vide)
        self.assertAlmostEqual(p.slots[3].duree_ms, 500, delta=20)
        p.vider(3)
        self.assertEqual(len(p.occupes()), 0)

    def test_slot_hors_limites(self):
        p = project.Projet("t")
        with self.assertRaises(ValueError):
            p.assigner(100, self.wav)

    def test_memoire(self):
        p = project.Projet("t")
        p.assigner(0, self.wav)
        self.assertAlmostEqual(p.memoire_utilisee_s(), 0.5, delta=0.05)
        self.assertEqual(p.memoire_totale_s(), 65.0)
        self.assertFalse(p.depassement())
        p2 = project.Projet("t", "sample2")
        self.assertEqual(p2.memoire_totale_s(), 130.0)

    def test_remplir_dossier(self):
        for i in range(4):
            make_wav(os.path.join(self.tmp, "x%d.wav" % i), secs=0.1)
        p = project.Projet("t")
        places = p.remplir_depuis_dossier(self.tmp, depart=10)
        self.assertGreaterEqual(len(places), 4)
        self.assertEqual(places[0].index, 10)

    def test_sauver_charger(self):
        p = project.Projet("kit", "sample2")
        p.assigner(7, self.wav, "max", 3.0)
        f = p.sauver(os.path.join(self.tmp, "k.volca.json"))
        q = project.Projet.charger(f)
        self.assertEqual(q.nom, "kit")
        self.assertEqual(q.modele, "sample2")
        self.assertEqual(q.slots[7].preset, "max")
        self.assertEqual(q.slots[7].gain_db, 3.0)
        self.assertEqual(q.pour_envoi(), [(7, self.wav)])

    def test_pour_envoi_filtre(self):
        p = project.Projet("t")
        p.assigner(1, self.wav)
        p.assigner(2, self.wav)
        self.assertEqual(len(p.pour_envoi([2])), 1)


if __name__ == "__main__":
    unittest.main()


class TestOptimisation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        # son sombre : pas d'aigu, donc taux reductible
        self.sombre = os.path.join(self.tmp, "sombre.wav")
        make_wav(self.sombre, secs=1.0, amp=0.3, freq=60.0)
        # son clair : a besoin de son aigu
        self.clair = os.path.join(self.tmp, "clair.wav")
        make_wav(self.clair, secs=1.0, amp=0.3, freq=9000.0)

    def test_cout_suit_le_taux(self):
        p = project.Projet("t")
        s = p.assigner(0, self.sombre)
        avant = s.cout_s()
        s.taux = 22050
        self.assertAlmostEqual(s.cout_s(), avant / 2.0, delta=0.05)

    def test_optimiser_reduit_le_sombre(self):
        p = project.Projet("t")
        p.assigner(0, self.sombre)
        avant = p.memoire_utilisee_s()
        rap, gagne = p.optimiser()
        self.assertEqual(len(rap), 1)
        self.assertLess(p.slots[0].taux, 44100)
        self.assertGreater(gagne, 0.2)
        self.assertLess(p.memoire_utilisee_s(), avant)

    def test_optimiser_epargne_laigu(self):
        p = project.Projet("t")
        p.assigner(3, self.clair)
        _rap, gagne = p.optimiser()
        self.assertIsNone(p.slots[3].taux)
        self.assertEqual(gagne, 0.0)

    def test_progression_appelee(self):
        p = project.Projet("t")
        p.assigner(0, self.sombre)
        p.assigner(1, self.clair)
        vus = []
        p.optimiser(lambda n, total, slot: vus.append((n, total)))
        self.assertEqual(vus, [(1, 2), (2, 2)])

    def test_taux_survit_a_la_sauvegarde(self):
        p = project.Projet("t")
        p.assigner(0, self.sombre)
        p.optimiser()
        taux = p.slots[0].taux
        f = p.sauver(os.path.join(self.tmp, "k.volca.json"))
        q = project.Projet.charger(f)
        self.assertEqual(q.slots[0].taux, taux)
        self.assertAlmostEqual(q.memoire_utilisee_s(),
                               p.memoire_utilisee_s(), delta=0.01)

    def test_reinitialiser(self):
        p = project.Projet("t")
        p.assigner(0, self.sombre)
        p.optimiser()
        p.reinitialiser_taux()
        self.assertIsNone(p.slots[0].taux)


class TestEgalisation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.fort = os.path.join(self.tmp, "fort.wav")
        make_wav(self.fort, secs=0.5, amp=0.6, freq=440.0)
        self.faible = os.path.join(self.tmp, "faible.wav")
        make_wav(self.faible, secs=0.5, amp=0.02, freq=440.0)

    def _lufs(self, slot):
        s = audio.read_wav(slot.chemin)
        s, _ = audio.process(s, slot.preset, slot.gain_db)
        return audio.loudness_lufs(s)

    def test_kit_homogene_apres_egalisation(self):
        p = project.Projet("t")
        p.assigner(0, self.fort, "max")
        p.assigner(1, self.faible, "doux")
        p.assigner(2, self.fort, "punch")
        avant = [self._lufs(s) for s in p.occupes()]
        self.assertGreater(max(avant) - min(avant), 1.0)
        p.egaliser()
        apres = [self._lufs(s) for s in p.occupes()]
        self.assertLess(max(apres) - min(apres), 1.0)

    def test_egaliser_natenue_que(self):
        p = project.Projet("t")
        p.assigner(0, self.fort, "max")
        p.assigner(1, self.faible, "doux")
        for r in p.egaliser():
            self.assertLessEqual(r["gain_db"], 0.0)

    def test_cible_trop_haute_ramenee(self):
        p = project.Projet("t")
        p.assigner(0, self.fort, "punch")
        rap = p.egaliser(cible=0.0)
        self.assertLess(rap[0]["cible"], 0.0)

    def test_projet_vide(self):
        self.assertEqual(project.Projet("t").egaliser(), [])

    def test_deplacer(self):
        p = project.Projet("t")
        p.assigner(0, self.fort)
        p.deplacer(0, 40)
        self.assertTrue(p.slots[0].vide)
        self.assertEqual(p.slots[40].index, 40)
        self.assertFalse(p.slots[40].vide)

    def test_deplacer_vers_occupe_refuse(self):
        p = project.Projet("t")
        p.assigner(0, self.fort)
        p.assigner(1, self.faible)
        with self.assertRaises(ValueError):
            p.deplacer(0, 1)

    def test_echanger(self):
        p = project.Projet("t")
        p.assigner(0, self.fort)
        p.assigner(1, self.faible)
        a, b = p.slots[0].nom, p.slots[1].nom
        p.echanger(0, 1)
        self.assertEqual(p.slots[0].nom, b)
        self.assertEqual(p.slots[1].nom, a)
        self.assertEqual(p.slots[0].index, 0)
        self.assertEqual(p.slots[1].index, 1)

    def test_dupliquer(self):
        p = project.Projet("t")
        p.assigner(0, self.fort, "max", -3.0)
        p.dupliquer(0, 50)
        self.assertEqual(p.slots[50].chemin, p.slots[0].chemin)
        self.assertEqual(p.slots[50].gain_db, -3.0)
        self.assertEqual(p.slots[50].index, 50)
        p.slots[50].gain_db = 1.0
        self.assertEqual(p.slots[0].gain_db, -3.0)

    def test_tasser(self):
        p = project.Projet("t")
        p.assigner(7, self.fort)
        p.assigner(30, self.faible)
        self.assertEqual(p.tasser(), 2)
        self.assertEqual([s.index for s in p.occupes()], [0, 1])

    def test_rangement_hors_limites(self):
        p = project.Projet("t")
        p.assigner(0, self.fort)
        with self.assertRaises(ValueError):
            p.echanger(0, 100)


class TestModeles(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.w = os.path.join(self.tmp, "s.wav")
        make_wav(self.w, secs=0.3, amp=0.3)

    def test_nombre_de_slots(self):
        self.assertEqual(project.Projet("t", "sample").nb_slots, 100)
        self.assertEqual(project.Projet("t", "sample2").nb_slots, 200)

    def test_memoire_par_modele(self):
        self.assertEqual(project.Projet("t", "sample").memoire_totale_s(), 65.0)
        self.assertEqual(project.Projet("t", "sample2").memoire_totale_s(),
                         130.0)

    def test_slot_150_refuse_sur_sample(self):
        p = project.Projet("t", "sample")
        with self.assertRaises(ValueError):
            p.assigner(150, self.w)

    def test_slot_150_accepte_sur_sample2(self):
        p = project.Projet("t", "sample2")
        s = p.assigner(150, self.w)
        self.assertEqual(s.index, 150)
        self.assertEqual(len(p.occupes()), 1)

    def test_agrandir_conserve_tout(self):
        p = project.Projet("t", "sample")
        p.assigner(0, self.w)
        p.assigner(99, self.w)
        perdus = p.changer_modele("sample2")
        self.assertEqual(perdus, [])
        self.assertEqual(p.nb_slots, 200)
        self.assertEqual(len(p.occupes()), 2)

    def test_reduire_signale_les_pertes(self):
        p = project.Projet("t", "sample2")
        p.assigner(5, self.w)
        p.assigner(150, self.w)
        annonce = p.perdus_si("sample")
        self.assertEqual([s.index for s in annonce], [150])
        perdus = p.changer_modele("sample")
        self.assertEqual([s.index for s in perdus], [150])
        self.assertEqual(p.nb_slots, 100)
        self.assertEqual([s.index for s in p.occupes()], [5])

    def test_perdus_si_ne_modifie_rien(self):
        p = project.Projet("t", "sample2")
        p.assigner(150, self.w)
        p.perdus_si("sample")
        self.assertEqual(p.nb_slots, 200)
        self.assertEqual(len(p.occupes()), 1)

    def test_modele_inconnu(self):
        p = project.Projet("t")
        with self.assertRaises(ValueError):
            p.changer_modele("volca beats")

    def test_sauvegarde_conserve_le_modele(self):
        p = project.Projet("kit", "sample2")
        p.assigner(180, self.w)
        f = p.sauver(os.path.join(self.tmp, "k.volca.json"))
        q = project.Projet.charger(f)
        self.assertEqual(q.modele, "sample2")
        self.assertEqual(q.nb_slots, 200)
        self.assertFalse(q.slots[180].vide)

    def test_chargement_ignore_les_slots_hors_limites(self):
        """Un projet sample2 relu en sample ne doit pas planter."""
        p = project.Projet("kit", "sample2")
        p.assigner(150, self.w)
        f = p.sauver(os.path.join(self.tmp, "k2.volca.json"))
        import json
        d = json.load(open(f))
        d["modele"] = "sample"
        json.dump(d, open(f, "w"))
        q = project.Projet.charger(f)
        self.assertEqual(q.nb_slots, 100)
        self.assertEqual(len(q.occupes()), 0)


class TestRenommer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.w = os.path.join(self.tmp, "s.wav")
        make_wav(self.w, secs=0.3, amp=0.3)
        self.p = project.Projet("t", "sample2")
        self.p.assigner(3, self.w)

    def test_renommer(self):
        s = self.p.renommer(3, "Kick sub 808")
        self.assertEqual(s.nom, "Kick sub 808")
        self.assertEqual(self.p.slots[3].nom, "Kick sub 808")

    def test_nom_vide_refuse(self):
        with self.assertRaises(ValueError):
            self.p.renommer(3, "   ")

    def test_slot_vide_refuse(self):
        with self.assertRaises(ValueError):
            self.p.renommer(50, "Rien")

    def test_nom_tronque(self):
        s = self.p.renommer(3, "x" * 100)
        self.assertEqual(len(s.nom), 40)

    def test_nom_survit_a_la_sauvegarde(self):
        self.p.renommer(3, "Snare vintage")
        f = self.p.sauver(os.path.join(self.tmp, "k.volca.json"))
        q = project.Projet.charger(f)
        self.assertEqual(q.slots[3].nom, "Snare vintage")
