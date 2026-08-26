import math
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from volca import audio, morceau, pattern  # noqa: E402


def son(freq=440.0, secs=0.1):
    n = int(44100 * secs)
    return audio.Sample([0.4 * math.sin(2 * math.pi * freq * i / 44100)
                         for i in range(n)], 44100)


def motif(nom, parties):
    m = pattern.vierge(nom)
    for i, (num, pas) in enumerate(parties, 1):
        m.partie(i).sample_num = num
        m.partie(i).depuis_liste(pas)
    return m


class TestSections(unittest.TestCase):
    def setUp(self):
        self.m = morceau.Morceau("essai", 120)
        self.m.ajouter(motif("intro", [(3, [1, 9])]), 2)
        self.m.ajouter(motif("couplet", [(3, [1, 5, 9, 13])]), 4)

    def test_duree(self):
        # 6 mesures de 16 pas a 120 bpm : un pas = 0,125 s
        self.assertEqual(self.m.pas, 6 * 16)
        self.assertAlmostEqual(self.m.duree_s(), 12.0, delta=0.1)

    def test_tempo_change_la_duree(self):
        self.m.bpm = 240
        self.assertAlmostEqual(self.m.duree_s(), 6.0, delta=0.1)

    def test_repetitions_minimum_un(self):
        self.m.repeter(0, 0)
        self.assertEqual(self.m.sections[0].repetitions, 1)

    def test_deplacer(self):
        self.assertTrue(self.m.deplacer(0, 1))
        self.assertEqual(self.m.sections[0].nom, "couplet")

    def test_deplacer_hors_limites(self):
        self.assertFalse(self.m.deplacer(0, -1))
        self.assertFalse(self.m.deplacer(1, 1))

    def test_supprimer(self):
        self.m.supprimer(0)
        self.assertEqual(len(self.m.sections), 1)
        self.assertEqual(self.m.sections[0].nom, "couplet")

    def test_index_invalide(self):
        with self.assertRaises(ValueError):
            self.m.supprimer(9)

    def test_dupliquer_est_independant(self):
        self.m.dupliquer(0)
        self.assertEqual(len(self.m.sections), 3)
        self.m.sections[0].motif.partie(1).sample_num = 42
        self.assertNotEqual(self.m.sections[1].motif.partie(1).sample_num, 42)

    def test_samples_utilises(self):
        self.assertEqual(self.m.samples_utilises(), [3])

    def test_partie_muette_exclue(self):
        self.m.sections[0].motif.partie(1).mettre("mute")
        self.m.sections[1].motif.partie(1).mettre("mute")
        self.assertEqual(self.m.samples_utilises(), [])


class TestRenduMorceau(unittest.TestCase):
    def setUp(self):
        self.sons = {3: son(220), 7: son(880)}
        self.m = morceau.Morceau("essai", 120)
        self.m.ajouter(motif("a", [(3, [1, 5, 9, 13])]), 2)
        self.m.ajouter(motif("b", [(7, [1, 9])]), 1)

    def test_duree_du_rendu(self):
        r = self.m.rendu(self.sons)
        self.assertGreater(r.duration_ms, 5900)
        self.assertLess(r.duration_ms, 6400)

    def test_pas_de_saturation(self):
        self.assertLessEqual(self.m.rendu(self.sons).peak_db(), 0.0)

    def test_morceau_vide(self):
        r = morceau.Morceau("vide").rendu(self.sons)
        self.assertEqual(len(r.data), 0)

    def test_sections_placees_dans_l_ordre(self):
        """La seconde section commence apres la premiere."""
        r = self.m.rendu(self.sons)
        rate = 44100
        debut_b = int(2 * 16 * pattern.duree_pas(120) * rate)
        avant = max(abs(v) for v in r.data[debut_b - 2000:debut_b - 100])
        apres = max(abs(v) for v in r.data[debut_b:debut_b + 2000])
        self.assertGreater(apres, avant)

    def test_progression(self):
        vus = []
        self.m.rendu(self.sons,
                     progression=lambda n, t, nom: vus.append((n, t)))
        self.assertEqual(vus[-1], (3, 3))


class TestFichier(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.m = morceau.Morceau("kit", 174)
        self.m.ajouter(motif("intro", [(5, [1, 5, 9, 13])]), 3)

    def test_aller_retour(self):
        f = self.m.sauver(os.path.join(self.tmp, "m.json"))
        q = morceau.Morceau.charger(f)
        self.assertEqual(q.nom, "kit")
        self.assertEqual(q.bpm, 174)
        self.assertEqual(len(q.sections), 1)
        self.assertEqual(q.sections[0].repetitions, 3)
        self.assertEqual(q.sections[0].motif.partie(1).liste_pas(),
                         [1, 5, 9, 13])

    def test_autonome(self):
        """Le morceau contient les patterns, pas des chemins."""
        f = self.m.sauver(os.path.join(self.tmp, "m.json"))
        import json
        d = json.load(open(f))
        self.assertIn("motif", d["sections"][0])
        self.assertNotIn("chemin", d["sections"][0])

    def test_infos(self):
        f = self.m.sauver(os.path.join(self.tmp, "m.json"))
        i = morceau.infos(f)
        self.assertEqual(i["sections"], 1)
        self.assertEqual(i["samples"], [5])

    def test_export_wav(self):
        cible = os.path.join(self.tmp, "sortie.wav")
        r = morceau.exporter_wav(self.m, {5: son(220)}, cible)
        self.assertTrue(os.path.isfile(cible))
        self.assertGreater(r["duree_s"], 3)
        relu = audio.read_wav(cible)
        self.assertGreater(len(relu.data), 0)


if __name__ == "__main__":
    unittest.main()


class TestPlanEnvoi(unittest.TestCase):
    def setUp(self):
        from volca import project
        self.tmp = tempfile.mkdtemp()
        self.w = os.path.join(self.tmp, "s.wav")
        audio.write_wav(self.w, son(220, 0.2))
        self.p = project.Projet("k", "sample2")
        self.p.assigner(3, self.w)
        self.p.renommer(3, "Kick")
        self.p.assigner(7, self.w)
        self.p.renommer(7, "Snare")

        self.m = morceau.Morceau("demo", 140)
        self.a = motif("couplet", [(3, [1, 5, 9, 13])])
        self.b = motif("break", [(7, [1, 3, 5, 7])])
        self.m.ajouter(self.a, 4)
        self.m.ajouter(self.b, 1)

    def test_patterns_et_samples(self):
        plan = morceau.plan_envoi(self.m, self.p)
        self.assertEqual(len(plan["patterns"]), 2)
        self.assertEqual([s[0] for s in plan["samples"]], [3, 7])
        self.assertEqual(plan["avertissements"], [])

    def test_patterns_identiques_dedupliques(self):
        from volca import pattern as pat
        self.m.ajouter(pat.Motif.from_bytes(self.a.to_bytes()), 2)
        plan = morceau.plan_envoi(self.m, self.p)
        self.assertEqual(len(plan["patterns"]), 2)
        self.assertEqual(plan["ordre"], [0, 0, 0, 0, 1, 0, 0])

    def test_ordre_suit_les_repetitions(self):
        plan = morceau.plan_envoi(self.m, self.p)
        self.assertEqual(plan["ordre"], [0, 0, 0, 0, 1])

    def test_slot_vide_signale(self):
        self.p.vider(7)
        plan = morceau.plan_envoi(self.m, self.p)
        self.assertEqual(len(plan["samples"]), 1)
        self.assertTrue(any("7" in a for a in plan["avertissements"]))

    def test_limite_dix_patterns(self):
        m = morceau.Morceau("gros")
        for i in range(14):
            m.ajouter(motif("p%d" % i, [(3, [1 + (i % 15)])]), 1)
        plan = morceau.plan_envoi(m, self.p)
        self.assertEqual(len(plan["patterns"]), 10)
        self.assertTrue(plan["avertissements"])

    def test_sans_samples(self):
        plan = morceau.plan_envoi(self.m, self.p, avec_samples=False)
        self.assertEqual(plan["samples"], [])
        self.assertEqual(len(plan["patterns"]), 2)

    def test_sans_projet(self):
        plan = morceau.plan_envoi(self.m, None)
        self.assertEqual(plan["samples"], [])

    def test_resume_lisible(self):
        r = morceau.resume_plan(morceau.plan_envoi(self.m, self.p))
        self.assertIn("pattern 0", r)
        self.assertIn("Kick", r)
        self.assertIn("Ordre de jeu", r)


class TestSlotsManquants(unittest.TestCase):
    def setUp(self):
        from volca import project
        self.tmp = tempfile.mkdtemp()
        self.w = os.path.join(self.tmp, "s.wav")
        audio.write_wav(self.w, son(220, 0.2))
        self.p = project.Projet("k", "sample2")
        self.m = morceau.Morceau("demo")
        self.m.ajouter(motif("a", [(3, [1]), (7, [5])]), 1)

    def test_tous_manquants(self):
        self.assertEqual(morceau.slots_manquants(self.m, self.p), [3, 7])

    def test_partiellement_remplis(self):
        self.p.assigner(3, self.w)
        self.assertEqual(morceau.slots_manquants(self.m, self.p), [7])

    def test_aucun_manquant(self):
        self.p.assigner(3, self.w)
        self.p.assigner(7, self.w)
        self.assertEqual(morceau.slots_manquants(self.m, self.p), [])

    def test_partie_muette_non_comptee(self):
        self.m.sections[0].motif.partie(2).mettre("mute")
        self.assertEqual(morceau.slots_manquants(self.m, self.p), [3])


class TestPistes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.sons = {3: son(80, 0.1), 7: son(900, 0.05)}
        m = pattern.vierge("a")
        m.partie(1).sample_num = 3
        m.partie(1).depuis_liste([1, 5, 9, 13])
        m.partie(2).sample_num = 7
        m.partie(2).depuis_liste([5, 13])
        self.m = morceau.Morceau("t", 120)
        self.m.ajouter(m, 2)

    def test_parties_actives_en_numerotation_musicale(self):
        self.assertEqual(self.m.parties_actives(), [1, 2])

    def test_partie_muette_exclue(self):
        self.m.sections[0].motif.partie(2).mettre("mute")
        self.assertEqual(self.m.parties_actives(), [1])

    def test_filtre_par_partie(self):
        p1 = self.m.rendu(self.sons, parties={1}, normaliser=False)
        p2 = self.m.rendu(self.sons, parties={2}, normaliser=False)
        plein = self.m.rendu(self.sons, normaliser=False)
        self.assertGreater(p1.peak(), 0)
        self.assertGreater(p2.peak(), 0)
        self.assertGreaterEqual(plein.peak(), max(p1.peak(), p2.peak()))

    def test_export_fichiers(self):
        r = morceau.exporter_pistes(self.m, self.sons, self.tmp)
        self.assertEqual(len(r), 3)
        for e in r:
            self.assertTrue(os.path.isfile(e["chemin"]))
        noms = sorted(os.path.basename(e["chemin"]) for e in r)
        self.assertTrue(noms[0].startswith("00_melange"))

    def test_equilibre_conserve(self):
        """Les pistes gardent leur rapport de niveau : une partie reglee
        plus bas doit ressortir plus bas dans son fichier."""
        self.m.sections[0].motif.partie(2).level = 32   # environ -12 dB
        r = morceau.exporter_pistes(self.m, self.sons, self.tmp)
        cretes = {e["partie"]: audio.read_wav(e["chemin"]).peak_db()
                  for e in r if e["partie"]}
        self.assertLess(cretes[2], cretes[1] - 8)

    def test_pistes_non_normalisees_separement(self):
        """Si chaque piste etait normalisee dans son coin, les deux
        finiraient a la meme crete."""
        self.m.sections[0].motif.partie(2).level = 32
        r = morceau.exporter_pistes(self.m, self.sons, self.tmp)
        cretes = [audio.read_wav(e["chemin"]).peak_db()
                  for e in r if e["partie"]]
        self.assertNotAlmostEqual(cretes[0], cretes[1], places=0)

    def test_somme_des_pistes_egale_le_melange(self):
        r = morceau.exporter_pistes(self.m, self.sons, self.tmp)
        melange = audio.read_wav(
            next(e["chemin"] for e in r if e["partie"] == 0))
        pistes = [audio.read_wav(e["chemin"]) for e in r if e["partie"]]
        n = min([len(melange.data)] + [len(p.data) for p in pistes])
        ecart = max(abs(melange.data[i] - sum(p.data[i] for p in pistes))
                    for i in range(0, n, 97))
        self.assertLess(ecart, 0.01)

    def test_nom_depuis_le_projet(self):
        from volca import project
        w = os.path.join(self.tmp, "s.wav")
        audio.write_wav(w, son(220, 0.1))
        p = project.Projet("k", "sample2")
        p.assigner(3, w)
        p.renommer(3, "Kick sub")
        self.assertEqual(self.m.nom_partie(1, p), "Kick sub")

    def test_morceau_sans_partie(self):
        vide = morceau.Morceau("v")
        vide.ajouter(pattern.vierge("rien"), 1)
        with self.assertRaises(ValueError):
            morceau.exporter_pistes(vide, self.sons, self.tmp)
