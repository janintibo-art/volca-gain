"""
Moteur de traitement audio pour Korg volca sample.

100 % Python standard : aucune dependance externe (pas de numpy, pas de scipy).
C'est volontaire -> ca marche dans Termux, dans un .exe PyInstaller et dans un
APK Buildozer sans aucune recette de compilation.

Format de sortie vise par la volca sample : WAV mono, 16 bits, 44100 Hz.
"""

import math
import sys
import wave
from array import array

TARGET_RATE = 44100
EPS = 1e-12


# --------------------------------------------------------------------------
# Utilitaires dB
# --------------------------------------------------------------------------
def lin_to_db(x):
    return 20.0 * math.log10(max(abs(x), EPS))


def db_to_lin(db):
    return 10.0 ** (db / 20.0)


# --------------------------------------------------------------------------
# Objet Sample
# --------------------------------------------------------------------------
class Sample:
    """Audio mono en flottants -1.0 .. 1.0"""

    def __init__(self, data, rate, name="sample"):
        self.data = data
        self.rate = rate
        self.name = name

    @property
    def duration_ms(self):
        return 1000.0 * len(self.data) / float(self.rate) if self.rate else 0.0

    def peak(self):
        return max((abs(v) for v in self.data), default=0.0)

    def peak_db(self):
        return lin_to_db(self.peak())

    def rms(self):
        if not self.data:
            return 0.0
        s = 0.0
        for v in self.data:
            s += v * v
        return math.sqrt(s / len(self.data))

    def rms_db(self):
        return lin_to_db(self.rms())

    def copy(self):
        return Sample(list(self.data), self.rate, self.name)

    def info(self):
        return {
            "nom": self.name,
            "duree_ms": round(self.duration_ms, 1),
            "echantillons": len(self.data),
            "rate": self.rate,
            "peak_db": round(self.peak_db(), 2),
            "rms_db": round(self.rms_db(), 2),
        }


# --------------------------------------------------------------------------
# Lecture / ecriture WAV
# --------------------------------------------------------------------------
def _decode(raw, sampwidth, nchannels):
    """bytes PCM -> liste de flottants entrelaces."""
    if sampwidth == 1:
        # 8 bits non signe
        return [(b - 128) / 128.0 for b in raw]

    if sampwidth == 2:
        a = array("h")
        a.frombytes(raw[: len(raw) - (len(raw) % 2)])
        if sys.byteorder == "big":
            a.byteswap()
        return [v / 32768.0 for v in a]

    if sampwidth == 3:
        out = []
        for i in range(0, len(raw) - 2, 3):
            v = raw[i] | (raw[i + 1] << 8) | (raw[i + 2] << 16)
            if v & 0x800000:
                v -= 0x1000000
            out.append(v / 8388608.0)
        return out

    if sampwidth == 4:
        a = array("i")
        a.frombytes(raw[: len(raw) - (len(raw) % 4)])
        if sys.byteorder == "big":
            a.byteswap()
        return [v / 2147483648.0 for v in a]

    raise ValueError("Profondeur non supportee : %d octets" % sampwidth)


def _downmix(inter, nchannels):
    if nchannels <= 1:
        return inter
    out = []
    n = len(inter) - (len(inter) % nchannels)
    for i in range(0, n, nchannels):
        s = 0.0
        for c in range(nchannels):
            s += inter[i + c]
        out.append(s / nchannels)
    return out


def resample_linear(data, src_rate, dst_rate):
    """Reechantillonnage par interpolation lineaire."""
    if src_rate == dst_rate or not data:
        return list(data)
    ratio = float(src_rate) / float(dst_rate)
    n_out = int(len(data) / ratio)
    out = [0.0] * n_out
    last = len(data) - 1
    for i in range(n_out):
        pos = i * ratio
        i0 = int(pos)
        if i0 >= last:
            out[i] = data[last]
        else:
            frac = pos - i0
            out[i] = data[i0] * (1.0 - frac) + data[i0 + 1] * frac
    return out


def read_wav(path, to_rate=TARGET_RATE):
    """Lit un WAV PCM et renvoie un Sample mono au rate demande."""
    with wave.open(path, "rb") as w:
        nch = w.getnchannels()
        sw = w.getsampwidth()
        rate = w.getframerate()
        raw = w.readframes(w.getnframes())

    data = _downmix(_decode(raw, sw, nch), nch)
    if to_rate:
        data = resample_linear(data, rate, to_rate)
        rate = to_rate

    import os
    name = os.path.splitext(os.path.basename(path))[0]
    return Sample(data, rate, name)


def write_wav(path, sample, sampwidth=2):
    """Ecrit un WAV mono 16 bits (format attendu par la volca)."""
    if sampwidth != 2:
        raise ValueError("Seul le 16 bits est gere en sortie.")
    a = array("h")
    for v in sample.data:
        if v > 1.0:
            v = 1.0
        elif v < -1.0:
            v = -1.0
        a.append(int(round(v * 32767.0)))
    if sys.byteorder == "big":
        a.byteswap()
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample.rate)
        w.writeframes(a.tobytes())
    return path


# --------------------------------------------------------------------------
# Traitements
# --------------------------------------------------------------------------
def apply_gain(sample, gain_db):
    g = db_to_lin(gain_db)
    sample.data = [v * g for v in sample.data]
    return sample


def normalize_peak(sample, ceiling_db=-0.3):
    """Amene la crete la plus haute au plafond demande."""
    pk = sample.peak()
    if pk <= EPS:
        return sample
    return apply_gain(sample, ceiling_db - lin_to_db(pk))


def target_rms(sample, target_db=-12.0, max_gain_db=30.0):
    """Amene le niveau moyen (RMS) a la cible. C'est ca qui rend un son
    'fort' a l'oreille, pas la crete."""
    cur = sample.rms_db()
    if cur <= -200:
        return sample
    gain = target_db - cur
    if gain > max_gain_db:
        gain = max_gain_db
    return apply_gain(sample, gain)


def trim_silence(sample, threshold_db=-55.0, pad_ms=3.0):
    """Coupe le silence au debut et a la fin."""
    thr = db_to_lin(threshold_db)
    d = sample.data
    start = 0
    while start < len(d) and abs(d[start]) < thr:
        start += 1
    end = len(d) - 1
    while end > start and abs(d[end]) < thr:
        end -= 1
    if start >= end:
        return sample
    pad = int(sample.rate * pad_ms / 1000.0)
    start = max(0, start - pad)
    end = min(len(d) - 1, end + pad)
    sample.data = d[start:end + 1]
    return sample


def fade(sample, in_ms=2.0, out_ms=5.0):
    """Petits fondus : evite les clics, indispensable sur la volca."""
    d = sample.data
    n = len(d)
    ni = min(int(sample.rate * in_ms / 1000.0), n // 2)
    no = min(int(sample.rate * out_ms / 1000.0), n // 2)
    for i in range(ni):
        d[i] *= i / float(ni)
    for i in range(no):
        d[n - 1 - i] *= i / float(no)
    return sample


def compress(sample, threshold_db=-20.0, ratio=3.0,
             attack_ms=5.0, release_ms=80.0):
    """Compresseur a detection d'enveloppe (mono, feed-forward).

    Reduit l'ecart crete/moyenne -> on peut ensuite monter beaucoup plus le
    niveau avant d'ecreter. C'est l'etape qui manque dans le librarian Korg.
    """
    rate = sample.rate
    att = math.exp(-1.0 / max(rate * attack_ms / 1000.0, 1.0))
    rel = math.exp(-1.0 / max(rate * release_ms / 1000.0, 1.0))
    env = 0.0
    slope = 1.0 - 1.0 / max(ratio, 1.0001)
    out = []
    for x in sample.data:
        a = abs(x)
        coef = att if a > env else rel
        env = coef * env + (1.0 - coef) * a
        over = lin_to_db(env) - threshold_db
        gr = over * slope if over > 0 else 0.0
        out.append(x * db_to_lin(-gr))
    sample.data = out
    return sample


def limit(sample, ceiling_db=-0.3, release_ms=30.0, lookahead_ms=1.0):
    """Limiteur avec lookahead : plafonne sans distordre."""
    rate = sample.rate
    ceil_lin = db_to_lin(ceiling_db)
    la = max(int(rate * lookahead_ms / 1000.0), 1)
    rel = math.exp(-1.0 / max(rate * release_ms / 1000.0, 1.0))

    d = sample.data
    n = len(d)
    if n == 0:
        return sample

    # gain requis par echantillon (glissiere de max sur la fenetre lookahead)
    need = [1.0] * n
    for i, x in enumerate(d):
        a = abs(x)
        if a > ceil_lin:
            need[i] = ceil_lin / a

    gains = [1.0] * n
    for i in range(n):
        g = 1.0
        for j in range(i, min(i + la, n)):
            if need[j] < g:
                g = need[j]
        gains[i] = g

    # lissage (attaque instantanee, relachement progressif)
    cur = 1.0
    out = [0.0] * n
    for i in range(n):
        g = gains[i]
        if g < cur:
            cur = g
        else:
            cur = rel * cur + (1.0 - rel) * g
        v = d[i] * cur
        if v > 1.0:
            v = 1.0
        elif v < -1.0:
            v = -1.0
        out[i] = v
    sample.data = out
    return sample


def dc_offset_remove(sample):
    if not sample.data:
        return sample
    m = sum(sample.data) / len(sample.data)
    if abs(m) > 1e-5:
        sample.data = [v - m for v in sample.data]
    return sample


# --------------------------------------------------------------------------
# Presets
# --------------------------------------------------------------------------
PRESETS = {
    "doux": {
        "trim": False, "dc": True, "compress": None,
        "rms": None, "ceiling": -1.0, "fade_in": 1.0, "fade_out": 3.0,
        "desc": "Normalisation crete seule. Garde toute la dynamique.",
    },
    "punch": {
        "trim": True, "dc": True,
        "compress": {"threshold_db": -18.0, "ratio": 3.0,
                     "attack_ms": 8.0, "release_ms": 90.0},
        "rms": -13.0, "ceiling": -0.3, "fade_in": 1.0, "fade_out": 4.0,
        "desc": "Compression douce + niveau moyen -13 dB. Bon defaut.",
    },
    "max": {
        "trim": True, "dc": True,
        "compress": {"threshold_db": -24.0, "ratio": 6.0,
                     "attack_ms": 2.0, "release_ms": 60.0},
        "rms": -9.0, "ceiling": -0.2, "fade_in": 0.5, "fade_out": 3.0,
        "desc": "Le plus fort possible. Pour kicks, claps, one-shots.",
    },
    "loop": {
        "trim": False, "dc": True,
        "compress": {"threshold_db": -20.0, "ratio": 2.5,
                     "attack_ms": 15.0, "release_ms": 150.0},
        "rms": -14.0, "ceiling": -0.5, "fade_in": 0.5, "fade_out": 0.5,
        "desc": "Boucles : fondus minuscules pour ne pas casser le raccord.",
    },
}


def process(sample, preset="punch", extra_gain_db=0.0, overrides=None):
    """Applique la chaine complete et renvoie (sample, rapport)."""
    if preset not in PRESETS:
        raise ValueError("Preset inconnu : %s" % preset)
    cfg = dict(PRESETS[preset])
    if overrides:
        cfg.update(overrides)

    before = sample.info()

    if cfg.get("dc"):
        dc_offset_remove(sample)
    if cfg.get("trim"):
        trim_silence(sample)
    if cfg.get("compress"):
        compress(sample, **cfg["compress"])
    if cfg.get("rms") is not None:
        target_rms(sample, cfg["rms"])
    else:
        normalize_peak(sample, cfg["ceiling"])
    if extra_gain_db:
        apply_gain(sample, extra_gain_db)
    fade(sample, cfg.get("fade_in", 1.0), cfg.get("fade_out", 3.0))
    limit(sample, cfg["ceiling"])

    after = sample.info()
    rapport = {
        "preset": preset,
        "avant": before,
        "apres": after,
        "gain_db": round(after["rms_db"] - before["rms_db"], 2),
    }
    return sample, rapport
