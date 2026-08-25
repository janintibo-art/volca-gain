"""
Teste la couche native (syro_wrap.c + wrapper ctypes) en la compilant contre
le faux SDK de native/fake_sdk. Ne valide pas le contenu du flux Syro (ca
demande le code de Korg), mais valide tout le reste : disposition des
structures, appels, memoire, ecriture du WAV.

Ignore automatiquement si aucun compilateur C n'est disponible.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import wave

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from tests.test_audio import make_wav  # noqa: E402

NATIVE = os.path.join(RACINE, "native")
FAKE = os.path.join(NATIVE, "fake_sdk")


def compilateur():
    for c in ("gcc", "cc", "clang"):
        if shutil.which(c):
            return c
    return None


def nom_lib():
    if sys.platform.startswith("win"):
        return "syro.dll"
    if sys.platform == "darwin":
        return "libsyro.dylib"
    return "libsyro.so"


@unittest.skipIf(compilateur() is None, "aucun compilateur C")
class TestSyro(unittest.TestCase):
    tmp = None
    lib = None

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="volcagain_syro_")
        cls.lib = os.path.join(cls.tmp, nom_lib())
        cmd = [compilateur(), "-shared", "-fPIC", "-I", FAKE, "-o", cls.lib,
               os.path.join(FAKE, "fake_syro.c"),
               os.path.join(NATIVE, "syro_wrap.c")]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise unittest.SkipTest("compilation impossible : " + r.stderr[:300])

        # forcer le chargement de cette bibliotheque
        from volca import syro
        cls.syro = syro
        syro._LIB = None
        syro._ERREUR_CHARGEMENT = None
        import ctypes
        handle = ctypes.CDLL(cls.lib)
        syro._configurer(handle)
        syro._LIB = handle

    @classmethod
    def tearDownClass(cls):
        if cls.tmp:
            shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_disponible(self):
        self.assertTrue(self.syro.disponible())
        self.assertIn("volcagain", self.syro.version())

    def test_envoi_un_sample(self):
        src = os.path.join(self.tmp, "a.wav")
        make_wav(src, secs=0.2, amp=0.3)
        out = os.path.join(self.tmp, "t.wav")
        res = self.syro.build_stream([(0, src)], out)
        self.assertTrue(os.path.isfile(out))
        self.assertGreater(res["duree_s"], 0)
        self.assertEqual(res["slots"][0]["slot"], 0)
        with wave.open(out, "rb") as w:
            self.assertEqual(w.getnchannels(), 2)
            self.assertEqual(w.getsampwidth(), 2)
            self.assertEqual(w.getframerate(), 44100)
            self.assertGreater(w.getnframes(), 0)

    def test_envoi_plusieurs_slots(self):
        srcs = []
        for i in range(3):
            p = os.path.join(self.tmp, "m%d.wav" % i)
            make_wav(p, secs=0.15, amp=0.2)
            srcs.append((i * 7, p))
        out = os.path.join(self.tmp, "multi.wav")
        res = self.syro.build_stream(srcs, out, preset="punch")
        self.assertEqual(len(res["slots"]), 3)
        self.assertEqual([s["slot"] for s in res["slots"]], [0, 7, 14])

    def test_effacement(self):
        out = os.path.join(self.tmp, "e.wav")
        res = self.syro.erase_stream([1, 2, 99], out)
        self.assertEqual(len(res["slots"]), 3)
        self.assertTrue(os.path.isfile(out))

    def test_slot_invalide(self):
        src = os.path.join(self.tmp, "b.wav")
        make_wav(src, secs=0.1)
        with self.assertRaises(ValueError):
            self.syro.build_stream([(100, src)], os.path.join(self.tmp, "x.wav"))
        with self.assertRaises(ValueError):
            self.syro.erase_stream([-1], os.path.join(self.tmp, "y.wav"))

    def test_liste_vide(self):
        with self.assertRaises(ValueError):
            self.syro.build_stream([], os.path.join(self.tmp, "z.wav"))


if __name__ == "__main__":
    unittest.main()
