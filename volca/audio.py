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


CANAUX = ("mix", "gauche", "droite", "side")


def _canal(inter, nchannels, canal="mix"):
    """Extrait un canal d'un signal entrelace.

    mix    : moyenne (le defaut)
    gauche : canal 1 seul
    droite : canal 2 seul
    side   : difference L-R. Isole ce qui n'est pas au centre : utile
             pour recuperer une nappe ou une reverb sans la voix.
    """
    if nchannels <= 1:
        return inter
    n = len(inter) - (len(inter) % nchannels)
    out = []
    if canal == "gauche":
        for i in range(0, n, nchannels):
            out.append(inter[i])
    elif canal == "droite":
        c = 1 if nchannels > 1 else 0
        for i in range(0, n, nchannels):
            out.append(inter[i + c])
    elif canal == "side" and nchannels >= 2:
        for i in range(0, n, nchannels):
            out.append((inter[i] - inter[i + 1]) / 2.0)
    else:
        for i in range(0, n, nchannels):
            v = 0.0
            for c in range(nchannels):
                v += inter[i + c]
            out.append(v / nchannels)
    return out


def _downmix(inter, nchannels):
    return _canal(inter, nchannels, "mix")


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


def read_wav(path, to_rate=TARGET_RATE, canal="mix"):
    """Lit un WAV PCM et renvoie un Sample mono au rate demande.

    canal : mix, gauche, droite ou side (voir _canal).
    """
    with wave.open(path, "rb") as w:
        nch = w.getnchannels()
        sw = w.getsampwidth()
        rate = w.getframerate()
        raw = w.readframes(w.getnframes())

    data = _canal(_decode(raw, sw, nch), nch, canal)
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
# Filtres biquad (formules RBJ)
# --------------------------------------------------------------------------
def _biquad_apply(data, b0, b1, b2, a1, a2):
    """Applique un biquad en forme directe I."""
    x1 = x2 = y1 = y2 = 0.0
    out = []
    for x0 in data:
        y0 = b0 * x0 + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
        x2, x1 = x1, x0
        y2, y1 = y1, y0
        out.append(y0)
    return out


def _hp_coeffs(freq, rate, q=0.707):
    w0 = 2.0 * math.pi * freq / rate
    cw = math.cos(w0)
    alpha = math.sin(w0) / (2.0 * q)
    a0 = 1.0 + alpha
    return ((1.0 + cw) / 2.0 / a0,
            -(1.0 + cw) / a0,
            (1.0 + cw) / 2.0 / a0,
            (-2.0 * cw) / a0,
            (1.0 - alpha) / a0)


def _shelf_coeffs(freq, rate, gain_db, q=0.707):
    """Plateau aigu, utilise pour la ponderation K."""
    a = 10.0 ** (gain_db / 40.0)
    w0 = 2.0 * math.pi * freq / rate
    cw, sw = math.cos(w0), math.sin(w0)
    alpha = sw / (2.0 * q)
    tsa = 2.0 * math.sqrt(a) * alpha
    a0 = (a + 1.0) - (a - 1.0) * cw + tsa
    return (a * ((a + 1.0) + (a - 1.0) * cw + tsa) / a0,
            -2.0 * a * ((a - 1.0) + (a + 1.0) * cw) / a0,
            a * ((a + 1.0) + (a - 1.0) * cw - tsa) / a0,
            2.0 * ((a - 1.0) - (a + 1.0) * cw) / a0,
            ((a + 1.0) - (a - 1.0) * cw - tsa) / a0)


def highpass(sample, freq=45.0, order=2):
    """Coupe le grave. Libere enormement de marge avant ecretage :
    l'energie sous 40 Hz est inaudible sur la plupart des systemes mais
    mange la dynamique."""
    if freq <= 0 or freq >= sample.rate / 2.0:
        return sample
    c = _hp_coeffs(freq, sample.rate)
    d = sample.data
    for _ in range(max(1, order // 2)):
        d = _biquad_apply(d, *c)
    sample.data = d
    return sample


# --------------------------------------------------------------------------
# Saturation
# --------------------------------------------------------------------------
def saturate(sample, drive=1.5, mix=0.4):
    """Saturation douce (tanh). Ajoute des harmoniques au lieu d'ecreter :
    le son parait plus fort sans monter le niveau."""
    if drive <= 0 or mix <= 0:
        return sample
    norm = math.tanh(drive)
    out = []
    for x in sample.data:
        wet = math.tanh(x * drive) / norm
        out.append(x * (1.0 - mix) + wet * mix)
    sample.data = out
    return sample


# --------------------------------------------------------------------------
# Transient shaper
# --------------------------------------------------------------------------
def transient(sample, attack_db=3.0, sustain_db=0.0,
              fast_ms=1.0, slow_ms=40.0):
    """Accentue ou mate l'attaque, independamment du volume.

    Plus utile qu'un compresseur sur les percussions : deux suiveurs
    d'enveloppe, un rapide un lent. Leur ecart revele les transitoires.
    """
    if attack_db == 0 and sustain_db == 0:
        return sample
    rate = sample.rate
    af = math.exp(-1.0 / max(rate * fast_ms / 1000.0, 1.0))
    as_ = math.exp(-1.0 / max(rate * slow_ms / 1000.0, 1.0))
    ef = es = 0.0
    out = []
    for x in sample.data:
        a = abs(x)
        ef = af * ef + (1.0 - af) * a if a <= ef else a
        es = as_ * es + (1.0 - as_) * a
        diff = lin_to_db(ef) - lin_to_db(es)
        if diff > 0:
            g = attack_db * min(diff / 6.0, 1.0)
        else:
            g = sustain_db * min(-diff / 6.0, 1.0)
        out.append(x * db_to_lin(g))
    sample.data = out
    return sample


# --------------------------------------------------------------------------
# Niveau percu (ponderation K, approximation de la norme BS.1770)
# --------------------------------------------------------------------------
def loudness_lufs(sample):
    """Niveau percu approximatif, en LUFS.

    Le RMS brut surestime les sons graves : l'oreille y est moins sensible.
    La ponderation K corrige ca. Approximation : filtres RBJ au lieu des
    coefficients exacts de la norme, mais l'ecart reste sous 0,5 dB.
    """
    if not sample.data:
        return -200.0
    d = _biquad_apply(sample.data, *_shelf_coeffs(1500.0, sample.rate, 4.0))
    d = _biquad_apply(d, *_hp_coeffs(38.0, sample.rate, 0.5))
    s = 0.0
    for v in d:
        s += v * v
    return -0.691 + 10.0 * math.log10(max(s / len(d), EPS))


def target_lufs(sample, target=-14.0, max_gain_db=30.0):
    """Amene le niveau percu a la cible. Plus fiable que le RMS pour
    egaliser un kit entier."""
    cur = loudness_lufs(sample)
    if cur <= -190:
        return sample
    g = target - cur
    return apply_gain(sample, min(g, max_gain_db))


# --------------------------------------------------------------------------
# Decoupe fine
# --------------------------------------------------------------------------
def snap_zero(sample, index, fenetre_ms=5.0):
    """Deplace un point de decoupe vers le passage par zero le plus proche.
    C'est ce qui supprime les clics."""
    d = sample.data
    if not d:
        return 0
    index = max(0, min(index, len(d) - 1))
    w = int(sample.rate * fenetre_ms / 1000.0)
    meilleur, score = index, abs(d[index])
    for i in range(max(0, index - w), min(len(d), index + w)):
        if abs(d[i]) < score:
            meilleur, score = i, abs(d[i])
    return meilleur


def decouper(sample, debut_ms=None, fin_ms=None, zero=True):
    """Decoupe manuelle, calee sur les passages par zero."""
    d = sample.data
    n = len(d)
    i0 = 0 if debut_ms is None else int(sample.rate * debut_ms / 1000.0)
    i1 = n if fin_ms is None else int(sample.rate * fin_ms / 1000.0)
    i0 = max(0, min(i0, n - 1))
    i1 = max(i0 + 1, min(i1, n))
    if zero:
        i0 = snap_zero(sample, i0)
        i1 = snap_zero(sample, i1 - 1) + 1
    sample.data = d[i0:i1]
    return sample


# --------------------------------------------------------------------------
# Memoire : la volca n'a que 65 s au total
# --------------------------------------------------------------------------
TAUX_MEMOIRE = [44100, 32000, 22050, 16000, 11025]


def changer_taux(sample, nouveau_rate):
    """Reduit le taux d'echantillonnage. Le Syro accepte n'importe quel Fs :
    une nappe sombre a 22 kHz ne s'entend pas et coute moitie moins cher
    en memoire."""
    if nouveau_rate == sample.rate:
        return sample
    sample.data = resample_linear(sample.data, sample.rate, nouveau_rate)
    sample.rate = nouveau_rate
    return sample


def cout_memoire_s(sample):
    """Cout en secondes de memoire volca (referme sur 44,1 kHz)."""
    return len(sample.data) / float(TARGET_RATE)


def taux_conseille(sample, seuil_hf_db=-28.0):
    """Propose un taux reduit si le sample n'a pas de contenu aigu.

    Mesure grossiere : energie au-dessus de 5 kHz obtenue en soustrayant
    une version filtree passe-bas.
    """
    if len(sample.data) < 64:
        return sample.rate
    total = sample.rms()
    if total <= EPS:
        return sample.rate
    # passe-bas simple a un pole vers 5 kHz
    a = math.exp(-2.0 * math.pi * 5000.0 / sample.rate)
    y = 0.0
    hf = 0.0
    for x in sample.data:
        y = a * y + (1.0 - a) * x
        hf += (x - y) ** 2
    hf = math.sqrt(hf / len(sample.data))
    ratio_db = lin_to_db(hf) - lin_to_db(total)
    if ratio_db < seuil_hf_db - 12:
        return 11025
    if ratio_db < seuil_hf_db - 6:
        return 16000
    if ratio_db < seuil_hf_db:
        return 22050
    return sample.rate


# --------------------------------------------------------------------------
# Porte de bruit, inversion, raccord de boucle
# --------------------------------------------------------------------------
def porte(sample, seuil_db=-45.0, attaque_ms=2.0, maintien_ms=40.0,
          relachement_ms=80.0, plancher_db=-60.0):
    """Porte de bruit : coupe ce qui passe sous le seuil.

    Indispensable sur les enregistrements au telephone : le souffle de
    fond devient tres audible une fois qu'on a monte le niveau de 25 dB.
    """
    rate = sample.rate
    seuil = db_to_lin(seuil_db)
    plancher = db_to_lin(plancher_db)
    att = math.exp(-1.0 / max(rate * attaque_ms / 1000.0, 1.0))
    rel = math.exp(-1.0 / max(rate * relachement_ms / 1000.0, 1.0))
    maintien = int(rate * maintien_ms / 1000.0)

    env = 0.0
    g = plancher
    reste = 0
    out = []
    for x in sample.data:
        a = abs(x)
        env = max(a, att * env + (1.0 - att) * a)
        if env >= seuil:
            reste = maintien
        elif reste > 0:
            reste -= 1
        cible = 1.0 if reste > 0 or env >= seuil else plancher
        if cible > g:
            g = cible - (cible - g) * att
        else:
            g = cible + (g - cible) * rel
        out.append(x * g)
    sample.data = out
    return sample


def inverser(sample):
    """Inverse la polarite. Ne s'entend pas seul, mais change tout quand
    deux samples se superposent sur la volca."""
    sample.data = [-v for v in sample.data]
    return sample


def raccord_boucle(sample, duree_ms=15.0):
    """Fondu enchaine de la fin sur le debut : la boucle tourne sans clic.

    Le sample raccourcit de la duree du fondu, c'est normal : la queue
    est fondue dans la tete au lieu d'etre juxtaposee.
    """
    d = sample.data
    n = len(d)
    x = int(sample.rate * duree_ms / 1000.0)
    if x < 2 or n < 4 * x:
        return sample
    tete = d[:x]
    queue = d[n - x:]
    fondu = []
    for i in range(x):
        f = i / float(x - 1)
        fondu.append(tete[i] * f + queue[i] * (1.0 - f))
    sample.data = fondu + d[x:n - x]
    return sample


# --------------------------------------------------------------------------
# Presets
# --------------------------------------------------------------------------
PRESETS = {
    "doux": {
        "hp": 25.0, "trim": False, "dc": True, "transient": None,
        "compress": None, "rms": None, "lufs": None, "sat": None,
        "ceiling": -1.0, "fade_in": 1.0, "fade_out": 3.0,
        "desc": "Normalisation crete seule. Garde toute la dynamique.",
    },
    "punch": {
        "hp": 45.0, "trim": True, "dc": True,
        "transient": {"attack_db": 2.0, "sustain_db": -1.0},
        "compress": {"threshold_db": -18.0, "ratio": 3.0,
                     "attack_ms": 8.0, "release_ms": 90.0},
        "rms": -13.0, "lufs": None,
        "sat": {"drive": 1.3, "mix": 0.25},
        "ceiling": -0.3, "fade_in": 1.0, "fade_out": 4.0,
        "desc": "Compression douce + attaque + niveau -13 dB. Bon defaut.",
    },
    "max": {
        "hp": 55.0, "trim": True, "dc": True,
        "transient": {"attack_db": 3.0, "sustain_db": -2.0},
        "compress": {"threshold_db": -24.0, "ratio": 6.0,
                     "attack_ms": 2.0, "release_ms": 60.0},
        "rms": -9.0, "lufs": None,
        "sat": {"drive": 2.2, "mix": 0.45},
        "ceiling": -0.2, "fade_in": 0.5, "fade_out": 3.0,
        "desc": "Le plus fort possible. Kicks, claps, one-shots.",
    },
    "loop": {
        "hp": 35.0, "trim": False, "dc": True, "transient": None,
        "compress": {"threshold_db": -20.0, "ratio": 2.5,
                     "attack_ms": 15.0, "release_ms": 150.0},
        "rms": None, "lufs": -14.0,
        "sat": {"drive": 1.2, "mix": 0.2},
        "ceiling": -0.5, "fade_in": 0.5, "fade_out": 0.5,
        "xfade": 12.0,
        "desc": "Boucles : niveau -14 LUFS, raccord fondu sans clic.",
    },
    "sub": {
        "hp": 20.0, "trim": True, "dc": True,
        "transient": {"attack_db": 1.5, "sustain_db": 0.0},
        "compress": {"threshold_db": -20.0, "ratio": 4.0,
                     "attack_ms": 12.0, "release_ms": 120.0},
        "rms": -11.0, "lufs": None, "sat": None,
        "ceiling": -0.5, "fade_in": 2.0, "fade_out": 6.0,
        "desc": "Basses et subs : garde le grave, pas de saturation.",
    },
    "voix": {
        "hp": 90.0, "trim": True, "dc": True,
        "transient": {"attack_db": 1.0, "sustain_db": 1.0},
        "compress": {"threshold_db": -22.0, "ratio": 4.0,
                     "attack_ms": 10.0, "release_ms": 120.0},
        "rms": None, "lufs": -13.0,
        "sat": {"drive": 1.2, "mix": 0.2},
        "porte": {"seuil_db": -42.0},
        "ceiling": -0.3, "fade_in": 2.0, "fade_out": 8.0,
        "desc": "Voix et field : coupe le souffle grave + porte de bruit.",
    },
}


def process(sample, preset="punch", extra_gain_db=0.0, overrides=None):
    """Chaine complete. Renvoie (sample, rapport)."""
    if preset not in PRESETS:
        raise ValueError("Preset inconnu : %s" % preset)
    cfg = dict(PRESETS[preset])
    if overrides:
        cfg.update(overrides)

    before = sample.info()
    before["lufs"] = round(loudness_lufs(sample), 2)

    if cfg.get("dc"):
        dc_offset_remove(sample)
    if cfg.get("hp"):
        highpass(sample, cfg["hp"])
    if cfg.get("trim"):
        trim_silence(sample)
    if cfg.get("porte"):
        porte(sample, **cfg["porte"])
    if cfg.get("inverser"):
        inverser(sample)
    if cfg.get("transient"):
        transient(sample, **cfg["transient"])
    if cfg.get("compress"):
        compress(sample, **cfg["compress"])

    # la saturation passe avant la mise a niveau : sinon elle deplace le
    # niveau qu'on vient tout juste de caler
    if cfg.get("sat"):
        normalize_peak(sample, -6.0)   # amene le signal dans la zone utile
        saturate(sample, **cfg["sat"])

    # Le gain supplementaire DEPLACE LA CIBLE au lieu de s'ajouter apres.
    # Ajoute apres coup, il etait repris par le limiteur : sur un preset
    # qui pousse deja au plafond, monter ou baisser le gain ne changeait
    # presque rien au niveau de sortie.
    if cfg.get("lufs") is not None:
        target_lufs(sample, cfg["lufs"] + extra_gain_db)
    elif cfg.get("rms") is not None:
        target_rms(sample, cfg["rms"] + extra_gain_db)
    else:
        # normalisation crete : on ne peut que descendre sous le plafond
        normalize_peak(sample, min(cfg["ceiling"] + extra_gain_db,
                                   cfg["ceiling"]))

    if cfg.get("xfade"):
        raccord_boucle(sample, cfg["xfade"])
        fade(sample, 0.3, 0.3)
    else:
        fade(sample, cfg.get("fade_in", 1.0), cfg.get("fade_out", 3.0))
    limit(sample, cfg["ceiling"])

    after = sample.info()
    after["lufs"] = round(loudness_lufs(sample), 2)
    return sample, {
        "preset": preset,
        "avant": before,
        "apres": after,
        "gain_db": round(after["rms_db"] - before["rms_db"], 2),
        "gain_lufs": round(after["lufs"] - before["lufs"], 2),
    }


# --------------------------------------------------------------------------
# Affichage de la forme d'onde
# --------------------------------------------------------------------------
def peaks(sample, colonnes=400):
    """Reduit le sample a une liste de (min, max) par colonne d'affichage.

    C'est ce qui permet de dessiner une forme d'onde sans parcourir des
    centaines de milliers d'echantillons a chaque rafraichissement.
    """
    d = sample.data
    n = len(d)
    if n == 0 or colonnes < 1:
        return []
    pas = max(1, n // colonnes)
    out = []
    for i in range(0, n, pas):
        bloc = d[i:i + pas]
        if bloc:
            out.append((min(bloc), max(bloc)))
    return out


def copie_decoupee(sample, debut_ms, fin_ms, zero=True):
    """Comme decouper(), mais renvoie une copie sans toucher a l'original."""
    c = sample.copy()
    return decouper(c, debut_ms, fin_ms, zero)
