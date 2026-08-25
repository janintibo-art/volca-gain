import math
import os
import sys
import tempfile
import unittest
import wave
from array import array

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from volca import audio  # noqa: E402


def make_wav(path, secs=0.3, amp=0.05, rate=48000, nch=1, freq=110.0):
    a = array("h")
    n = int(rate * secs)
    for i in range(n):
        v = amp * math.sin(2 * math.pi * freq * i / rate)
        for _c in range(nch):
            a.append(int(v * 32767))
    with wave.open(path, "wb") as w:
        w.setnchannels(nch)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(a.tobytes())


class TestAudio(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_db(self):
        self.assertAlmostEqual(audio.lin_to_db(1.0), 0.0, places=6)
        self.assertAlmostEqual(audio.db_to_lin(0.0), 1.0, places=6)
        self.assertAlmostEqual(audio.lin_to_db(0.5), -6.02, places=1)

    def test_lecture_et_resample(self):
        p = os.path.join(self.tmp, "a.wav")
        make_wav(p, rate=48000)
        s = audio.read_wav(p)
        self.assertEqual(s.rate, audio.TARGET_RATE)
        self.assertAlmostEqual(s.duration_ms, 300, delta=15)

    def test_stereo_vers_mono(self):
        p = os.path.join(self.tmp, "st.wav")
        make_wav(p, nch=2, rate=44100)
        s = audio.read_wav(p)
        self.assertAlmostEqual(s.duration_ms, 300, delta=15)

    def test_normalisation(self):
        p = os.path.join(self.tmp, "b.wav")
        make_wav(p, amp=0.02)
        s = audio.read_wav(p)
        self.assertLess(s.peak_db(), -25)
        audio.normalize_peak(s, -0.3)
        self.assertAlmostEqual(s.peak_db(), -0.3, delta=0.2)

    def test_preset_augmente_le_niveau(self):
        p = os.path.join(self.tmp, "c.wav")
        make_wav(p, amp=0.02)
        s = audio.read_wav(p)
        avant = s.rms_db()
        s, rap = audio.process(s, "punch")
        self.assertGreater(s.rms_db(), avant + 10)
        self.assertLessEqual(s.peak_db(), 0.0)
        self.assertGreater(rap["gain_db"], 10)

    def test_limiteur_ne_depasse_pas(self):
        s = audio.Sample([0.9 * math.sin(i / 5.0) for i in range(4410)], 44100)
        audio.apply_gain(s, 20)
        audio.limit(s, -0.3)
        self.assertLessEqual(s.peak_db(), -0.2)

    def test_ecriture_format_volca(self):
        p = os.path.join(self.tmp, "d.wav")
        make_wav(p, rate=22050, nch=2)
        s = audio.read_wav(p)
        s, _ = audio.process(s, "max")
        out = os.path.join(self.tmp, "out.wav")
        audio.write_wav(out, s)
        with wave.open(out, "rb") as w:
            self.assertEqual(w.getnchannels(), 1)
            self.assertEqual(w.getsampwidth(), 2)
            self.assertEqual(w.getframerate(), 44100)

    def test_trim(self):
        d = [0.0] * 5000 + [0.5] * 5000 + [0.0] * 5000
        s = audio.Sample(d, 44100)
        audio.trim_silence(s)
        self.assertLess(len(s.data), 6000)

    def test_tous_les_presets(self):
        for nom in audio.PRESETS:
            p = os.path.join(self.tmp, "e.wav")
            make_wav(p, amp=0.1)
            s = audio.read_wav(p)
            s, _ = audio.process(s, nom)
            self.assertLessEqual(s.peak_db(), 0.0, nom)
            self.assertGreater(len(s.data), 0, nom)


if __name__ == "__main__":
    unittest.main()
