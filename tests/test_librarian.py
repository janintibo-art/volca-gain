"""
Import des sauvegardes du librarian Korg.

Le format n'etant pas documente, ces tests construisent une sauvegarde
synthetique conforme a ce qui a ete observe sur un fichier reel.
"""
import os
import struct
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from volca import audio, librarian  # noqa: E402

INFO = """<?xml version="1.0" encoding="UTF-8"?>
<KorgMSLibrarian_Data>
  <Product>%s</Product>
  <Contents NumProgramData="%d" NumSampleData="%d" NumPresetInformation="0">
  </Contents>
</KorgMSLibrarian_Data>
"""

SMPL = """<?xml version="1.0" encoding="UTF-8"?>
<SampleInformation>
  <Name>%s</Name>
  <Length>%d</Length>
  <Level>65535</Level>
  <Speed>16384</Speed>
</SampleInformation>
"""

PROG = """<?xml version="1.0" encoding="UTF-8"?>
<ProgramInformation>
  <Name>%s</Name>
</ProgramInformation>
"""


def pcm(n, amp=8000):
    import math
    return b"".join(struct.pack("<h", int(amp * math.sin(i / 12.0)))
                    for i in range(n))


def programme(nom="Test", parties=None):
    """Fabrique un Prog_bin volca sample2 de 7936 octets."""
    b = bytearray(librarian.PROG2_TAILLE)
    b[0:4] = b"PTST"
    b[4:6] = struct.pack("<H", 0x33B8)
    b[0x10:0x10 + len(nom)] = nom.encode("ascii")
    for i, (num, pas, niveau, func) in enumerate(parties or []):
        d = librarian.PROG2_DEBUT_PARTIES + i * librarian.PROG2_TAILLE_PARTIE
        b[d:d + 8] = struct.pack("<HHHH", num, pas, 0, 0)
        b[d + 8] = niveau
        b[d + 20] = func
    b[-4:] = b"PTED"
    return bytes(b)


def sauvegarde(chemin, sons, produit="volca sample 2", progs=None):
    """sons : {numero: (nom, nb_echantillons)}"""
    progs = progs or []
    with zipfile.ZipFile(chemin, "w") as z:
        z.writestr(librarian.INFO_FICHIER,
                   INFO % (produit, len(progs), 200))
        for num in range(200):
            nom, n = sons.get(num, ("", 0))
            z.writestr("Smpl_%03d.smpl_info" % num, SMPL % (nom, n))
            if n:
                z.writestr("Smpl_%03d.smpl_bin" % num, pcm(n))
        for i, (nom, parties) in enumerate(progs):
            z.writestr("Prog_%03d.prog_info" % i, PROG % nom)
            z.writestr("Prog_%03d.prog_bin" % i, programme(nom, parties))
    return chemin


class TestInfos(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.f = sauvegarde(os.path.join(self.tmp, "s.vlcspllib"),
                            {0: ("Kick", 4000), 5: ("Snare", 3000)},
                            progs=[("Intro", [(3, 0x1111, 127, 0)])])

    def test_infos(self):
        i = librarian.infos(self.f)
        self.assertEqual(i["produit"], "volca sample 2")
        self.assertEqual(i["modele"], "sample2")
        self.assertEqual(i["emplacements"], 200)
        self.assertEqual(i["sons"], 2)
        self.assertEqual(i["programmes"], 1)

    def test_zip_quelconque_refuse(self):
        faux = os.path.join(self.tmp, "faux.zip")
        with zipfile.ZipFile(faux, "w") as z:
            z.writestr("rien.txt", "bidon")
        with self.assertRaises(librarian.FormatInvalide):
            librarian.infos(faux)

    def test_volca_sample_premiere_generation(self):
        f = sauvegarde(os.path.join(self.tmp, "v1.vlcspllib"),
                       {0: ("Kick", 1000)}, produit="volca sample")
        self.assertEqual(librarian.infos(f)["modele"], "sample")


class TestImport(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.f = sauvegarde(os.path.join(self.tmp, "kit.vlcspllib"),
                            {0: ("Kick sub", 6250),
                             7: ("Clap salle", 3125),
                             150: ("Nappe", 12500)})

    def test_projet_reconstruit(self):
        p, rap = librarian.importer(self.f, os.path.join(self.tmp, "out"))
        self.assertEqual(p.modele, "sample2")
        self.assertEqual(p.nb_slots, 200)
        self.assertEqual([s.index for s in p.occupes()], [0, 7, 150])
        self.assertEqual(len(rap), 3)

    def test_noms_conserves(self):
        p, _ = librarian.importer(self.f, os.path.join(self.tmp, "out"))
        self.assertEqual(p.slots[0].nom, "Kick sub")
        self.assertEqual(p.slots[7].nom, "Clap salle")

    def test_wav_ecrits_et_lisibles(self):
        p, _ = librarian.importer(self.f, os.path.join(self.tmp, "out"))
        for s in p.occupes():
            self.assertTrue(os.path.isfile(s.chemin))
            son = audio.read_wav(s.chemin)
            self.assertGreater(len(son.data), 0)
            self.assertEqual(son.rate, audio.TARGET_RATE)

    def test_duree_correcte(self):
        """6250 echantillons a 31250 Hz = 200 ms."""
        p, rap = librarian.importer(self.f, os.path.join(self.tmp, "out"))
        r = next(x for x in rap if x["slot"] == 0)
        self.assertAlmostEqual(r["duree_ms"], 200, delta=5)

    def test_taux_personnalise(self):
        p, rap = librarian.importer(self.f, os.path.join(self.tmp, "out2"),
                                    taux=15625)
        r = next(x for x in rap if x["slot"] == 0)
        self.assertAlmostEqual(r["duree_ms"], 400, delta=10)

    def test_projet_sauve(self):
        p, _ = librarian.importer(self.f, os.path.join(self.tmp, "out"))
        self.assertTrue(os.path.isfile(p.chemin_fichier))

    def test_progression(self):
        vus = []
        librarian.importer(self.f, os.path.join(self.tmp, "out"),
                           progression=lambda n, t, num, nom: vus.append(n))
        self.assertEqual(vus, [1, 2, 3])


class TestProgrammes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.f = sauvegarde(
            os.path.join(self.tmp, "p.vlcspllib"), {0: ("Kick", 1000)},
            progs=[("Intro", [(3, 0b0001000100010001, 127, 0b10),
                              (12, 0b0000000100000001, 100, 0b10000)]),
                   ("Break", [(5, 0b1111000000000000, 127, 0)])])

    def test_lecture(self):
        progs = librarian.programmes(self.f)
        self.assertEqual(len(progs), 2)
        self.assertEqual(progs[0]["nom"], "Intro")
        self.assertEqual(len(progs[0]["parties"]), 10)

    def test_pas_decodes(self):
        p = librarian.programmes(self.f)[0]
        self.assertEqual(p["parties"][0]["liste_pas"], [1, 5, 9, 13])
        self.assertEqual(p["parties"][0]["sample"], 3)
        self.assertEqual(p["parties"][1]["liste_pas"], [1, 9])

    def test_fonctions(self):
        p = librarian.programmes(self.f)[0]
        self.assertTrue(p["parties"][0]["loop"])
        self.assertFalse(p["parties"][0]["mute"])
        self.assertTrue(p["parties"][1]["mute"])

    def test_parties_utilisees(self):
        p = librarian.programmes(self.f)[0]
        self.assertEqual(len(p["utilisees"]), 2)

    def test_taille_invalide(self):
        with self.assertRaises(librarian.FormatInvalide):
            librarian.lire_programme(b"\x00" * 100)

    def test_entete_absente(self):
        b = bytearray(programme())
        b[0] = 0
        with self.assertRaises(librarian.FormatInvalide):
            librarian.lire_programme(bytes(b))

    def test_grille(self):
        p = librarian.programmes(self.f)[0]
        g = librarian.grille(p)
        self.assertEqual(len(g.splitlines()), 11)
        self.assertIn("X", g)


if __name__ == "__main__":
    unittest.main()


class TestFichierPatternsSeul(unittest.TestCase):
    """Un .vlcsplpatt : meme conteneur, mais sans aucun son."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.f = os.path.join(self.tmp, "p.vlcsplpatt")
        with zipfile.ZipFile(self.f, "w") as z:
            z.writestr(librarian.INFO_FICHIER, INFO % ("volca sample 2", 1, 0))
            z.writestr("Prog_000.prog_info", PROG % "Scratching")
            z.writestr("Prog_000.prog_bin",
                       programme("Scratching",
                                 [(128, 0b0001000100010001, 127, 0b10),
                                  (3, 0b0000000100000001, 100, 0)]))

    def test_reconnu(self):
        self.assertTrue(librarian.est_fichier_korg(self.f))

    def test_infos(self):
        i = librarian.infos(self.f)
        self.assertEqual(i["sons"], 0)
        self.assertEqual(i["emplacements"], 0)
        self.assertEqual(i["programmes"], 1)

    def test_import_sans_son_ne_plante_pas(self):
        p, rap = librarian.importer(self.f, os.path.join(self.tmp, "out"))
        self.assertEqual(rap, [])
        self.assertEqual(len(p.occupes()), 0)

    def test_pattern_lisible(self):
        progs = librarian.programmes(self.f)
        self.assertEqual(len(progs), 1)
        self.assertEqual(progs[0]["nom"], "Scratching")
        self.assertEqual(progs[0]["parties"][0]["liste_pas"], [1, 5, 9, 13])


class TestConversion(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.f = sauvegarde(
            os.path.join(self.tmp, "c.vlcspllib"), {},
            progs=[("Groove", [(42, 0b0001000100010001, 120, 0b110),
                               (7, 0b1000000000000001, 90, 0b10000)])])

    def test_vers_motif(self):
        prog = librarian.programmes(self.f)[0]
        m = librarian.vers_motif(prog)
        self.assertEqual(m.nom, "Groove")
        self.assertEqual(m.partie(1).sample_num, 42)
        self.assertEqual(m.partie(1).liste_pas(), [1, 5, 9, 13])
        self.assertEqual(m.partie(1).level, 120)
        self.assertTrue(m.partie(1).actif("loop"))
        self.assertTrue(m.partie(1).actif("reverb"))
        self.assertTrue(m.partie(2).actif("mute"))

    def test_motif_converti_est_valide(self):
        """La conversion doit produire un pattern premiere generation."""
        prog = librarian.programmes(self.f)[0]
        b = librarian.vers_motif(prog).to_bytes()
        self.assertEqual(len(b), 0xA40)
        from volca import pattern as pat
        relu = pat.Motif.from_bytes(b)
        self.assertEqual(relu.partie(1).sample_num, 42)

    def test_fichier_quelconque_non_reconnu(self):
        f = os.path.join(self.tmp, "x.dat")
        open(f, "wb").write(b"\x00" * 100)
        self.assertFalse(librarian.est_fichier_korg(f))
