"""
Transfert direct vers la volca sample (remplace le librarian Korg).

La volca ne recoit pas de fichiers : elle recoit du SON, par la prise SYNC IN.
Le "Syro SDK" de Korg transforme WAV + numero de slot -> flux audio a jouer.

Ce module charge la bibliotheque native (libsyro.so / syro.dll) construite a
partir de native/syro_wrap.c + du SDK Korg. Si elle est absente, tout reste
utilisable : le traitement audio fonctionne, seul l'envoi direct est desactive
(on repasse alors par le librarian officiel).

Chaine complete :
    WAV -> traitement (volca.audio) -> build_stream() -> WAV de transfert
        -> lecture par la sortie casque -> cable jack -> SYNC IN de la volca
"""

import ctypes
import os
import platform
import sys
import wave
from array import array

from . import audio

# ---------------------------------------------------------------- constantes
TYPE_SAMPLE = 0
TYPE_ERASE = 1
TYPE_PATTERN = 2

ERREURS = {
    -1: ("SyroVolcaSample_Start a echoue. Causes possibles : donnees trop "
         "grosses, ou slot au-dela de 99 refuse par le SDK (le SDK d'origine "
         "vise la volca sample ; verifie s'il gere la sample2)."),
    -2: "memoire insuffisante",
    -3: "erreur pendant le rendu du flux",
    -4: "aucune donnee a envoyer",
}

STREAM_RATE = 44100  # le flux Syro est toujours en 44100 stereo 16 bits

# La volca sample a 100 emplacements, la sample2 en a 200.
# On laisse passer jusqu'a 199 : si le SDK Korg refuse au-dela de 99,
# l'erreur remontera clairement plutot que d'etre bloquee ici.
SLOT_MAX = 199


class SyroIndisponible(RuntimeError):
    pass


# ---------------------------------------------------------------- structures
class VGData(ctypes.Structure):
    """Doit correspondre exactement a VGData dans native/syro_wrap.c"""
    _fields_ = [
        ("type", ctypes.c_int32),
        ("number", ctypes.c_int32),
        ("quality", ctypes.c_int32),
        ("compress", ctypes.c_int32),
        ("fs", ctypes.c_uint32),
        ("size", ctypes.c_uint32),
        ("data", ctypes.POINTER(ctypes.c_uint8)),
    ]


# ---------------------------------------------------------------- chargement
def _noms_possibles():
    s = platform.system()
    if s == "Windows":
        return ["syro.dll", "libsyro.dll"]
    if s == "Darwin":
        return ["libsyro.dylib", "syro.dylib"]
    return ["libsyro.so", "syro.so"]


def _dossiers_possibles():
    ici = os.path.dirname(os.path.abspath(__file__))
    racine = os.path.dirname(ici)
    d = [
        ici,
        racine,
        os.path.join(racine, "native"),
        os.path.join(racine, "native", "build"),
        os.path.join(racine, "native", "prebuilt"),
        os.path.join(racine, "lib"),
        os.getcwd(),
    ]
    if hasattr(sys, "_MEIPASS"):          # PyInstaller
        d.insert(0, sys._MEIPASS)
    for env in ("ANDROID_PRIVATE", "ANDROID_ARGUMENT"):
        p = os.environ.get(env)
        if p:
            d.append(p)
            d.append(os.path.join(os.path.dirname(p), "lib"))
    return d


_LIB = None
_ERREUR_CHARGEMENT = None


def _configurer(lib):
    lib.volcagain_render.argtypes = [
        ctypes.POINTER(VGData), ctypes.c_int,
        ctypes.POINTER(ctypes.POINTER(ctypes.c_int16)),
        ctypes.POINTER(ctypes.c_uint32),
    ]
    lib.volcagain_render.restype = ctypes.c_int
    lib.volcagain_free.argtypes = [ctypes.POINTER(ctypes.c_int16)]
    lib.volcagain_free.restype = None
    lib.volcagain_version.restype = ctypes.c_char_p


def _charger():
    global _LIB, _ERREUR_CHARGEMENT
    if _LIB is not None or _ERREUR_CHARGEMENT is not None:
        return _LIB

    essais = []
    for dossier in _dossiers_possibles():
        for nom in _noms_possibles():
            chemin = os.path.join(dossier, nom)
            if os.path.isfile(chemin):
                try:
                    lib = ctypes.CDLL(chemin)
                    _configurer(lib)
                    _LIB = lib
                    return _LIB
                except (OSError, AttributeError) as e:
                    essais.append("%s : %s" % (chemin, e))
    for nom in _noms_possibles():
        try:
            lib = ctypes.CDLL(nom)
            _configurer(lib)
            _LIB = lib
            return _LIB
        except (OSError, AttributeError):
            pass

    _ERREUR_CHARGEMENT = (
        "bibliotheque native introuvable. Construis-la :\n"
        "  git submodule update --init --recursive\n"
        "  cmake -S native -B native/build && cmake --build native/build"
        + ("\nEssais : " + " | ".join(essais) if essais else "")
    )
    return None


def disponible():
    """True si l'envoi direct est possible sur cette machine."""
    return _charger() is not None


def raison_indisponible():
    _charger()
    return _ERREUR_CHARGEMENT


def version():
    lib = _charger()
    return lib.volcagain_version().decode() if lib else None


# ---------------------------------------------------------------- conversion
def _pcm16(sample):
    """Sample -> bytes PCM 16 bits mono little endian."""
    a = array("h")
    for v in sample.data:
        if v > 1.0:
            v = 1.0
        elif v < -1.0:
            v = -1.0
        a.append(int(round(v * 32767.0)))
    if sys.byteorder == "big":
        a.byteswap()
    return a.tobytes()


def _ecrire_stereo(path, buf_ptr, frames):
    """buffer C int16 stereo -> WAV 44100 stereo 16 bits."""
    brut = ctypes.string_at(ctypes.cast(buf_ptr, ctypes.c_void_p),
                            frames * 2 * 2)
    with wave.open(path, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(STREAM_RATE)
        w.writeframes(brut)
    return path


# ---------------------------------------------------------------- API
def build_stream(slots, out_path, compress=True, quality=16,
                 preset=None, gain_db=0.0):
    """Genere le WAV de transfert.

    slots   : liste de (numero_slot:int, chemin_wav:str)
    preset  : si donne, applique le traitement volca.audio avant l'envoi
    compress: mode compresse (transfert plus court)
    quality : 8..16 bits, seulement en mode compresse

    Renvoie un dict : chemin, duree_s, slots.
    """
    lib = _charger()
    if lib is None:
        raise SyroIndisponible(raison_indisponible())
    if not slots:
        raise ValueError("aucun slot a envoyer")

    items = (VGData * len(slots))()
    buffers = []  # garder les references vivantes pendant l'appel C
    detail = []

    for i, (num, chemin) in enumerate(slots):
        if not 0 <= num <= SLOT_MAX:
            raise ValueError("slot hors limites : %d (max %d)"
                             % (num, SLOT_MAX))
        s = audio.read_wav(chemin)
        if preset:
            s, _ = audio.process(s, preset, gain_db)
        elif gain_db:
            audio.apply_gain(s, gain_db)

        pcm = _pcm16(s)
        buf = (ctypes.c_uint8 * len(pcm)).from_buffer_copy(pcm)
        buffers.append(buf)

        items[i].type = TYPE_SAMPLE
        items[i].number = num
        items[i].quality = max(8, min(16, int(quality)))
        items[i].compress = 1 if compress else 0
        items[i].fs = s.rate
        items[i].size = len(pcm)
        items[i].data = ctypes.cast(buf, ctypes.POINTER(ctypes.c_uint8))

        detail.append({"slot": num, "nom": s.name,
                       "duree_ms": round(s.duration_ms, 1),
                       "octets": len(pcm)})

    return _rendre(lib, items, len(slots), out_path, detail)


PATTERN_MAX = 9         # la volca a 10 patterns, numerotes 0 a 9
PATTERN_TAILLE = 0xA40  # doit correspondre a volca.pattern.TAILLE


def pattern_stream(patterns, out_path):
    """Genere le WAV qui envoie des patterns a la volca.

    patterns : liste de (numero_pattern 0-9, donnees 2624 octets)
    Les donnees viennent de volca.pattern.Motif.to_bytes().
    """
    lib = _charger()
    if lib is None:
        raise SyroIndisponible(raison_indisponible())
    if not patterns:
        raise ValueError("aucun pattern a envoyer")

    items = (VGData * len(patterns))()
    buffers = []
    detail = []

    for i, (num, donnees) in enumerate(patterns):
        if not 0 <= num <= PATTERN_MAX:
            raise ValueError("pattern hors limites : %d (max %d)"
                             % (num, PATTERN_MAX))
        if len(donnees) != PATTERN_TAILLE:
            raise ValueError("pattern %d : %d octets au lieu de %d"
                             % (num, len(donnees), PATTERN_TAILLE))
        buf = (ctypes.c_uint8 * len(donnees)).from_buffer_copy(donnees)
        buffers.append(buf)

        items[i].type = TYPE_PATTERN
        items[i].number = num
        items[i].quality = 16
        items[i].compress = 0
        items[i].fs = STREAM_RATE
        items[i].size = len(donnees)
        items[i].data = ctypes.cast(buf, ctypes.POINTER(ctypes.c_uint8))
        detail.append({"slot": num, "nom": "pattern %d" % num,
                       "octets": len(donnees)})

    return _rendre(lib, items, len(patterns), out_path, detail)


def erase_stream(indices, out_path):
    """Genere le WAV qui efface les slots donnes."""
    lib = _charger()
    if lib is None:
        raise SyroIndisponible(raison_indisponible())
    indices = list(indices)
    if not indices:
        raise ValueError("aucun slot a effacer")

    items = (VGData * len(indices))()
    for i, num in enumerate(indices):
        if not 0 <= num <= SLOT_MAX:
            raise ValueError("slot hors limites : %d (max %d)"
                             % (num, SLOT_MAX))
        items[i].type = TYPE_ERASE
        items[i].number = num
        items[i].quality = 16
        items[i].compress = 0
        items[i].fs = STREAM_RATE
        items[i].size = 0
        items[i].data = None

    detail = [{"slot": n, "nom": "<efface>"} for n in indices]
    return _rendre(lib, items, len(indices), out_path, detail)


def flux_mixte(elements, out_path, compress=True, quality=16):
    """Un seul flux pour tout envoyer : samples ET patterns.

    elements : liste de dictionnaires
        {"type": "sample",  "slot": 0-199, "sample": audio.Sample}
        {"type": "pattern", "slot": 0-9,   "donnees": 2624 octets}
        {"type": "effacer", "slot": 0-199}

    Le SDK Korg accepte plusieurs elements par flux : tout part en une
    seule lecture, au lieu d'un transfert par element.
    """
    lib = _charger()
    if lib is None:
        raise SyroIndisponible(raison_indisponible())
    if not elements:
        raise ValueError("rien a envoyer")

    items = (VGData * len(elements))()
    buffers = []
    detail = []

    for i, e in enumerate(elements):
        genre = e.get("type", "sample")
        num = int(e.get("slot", 0))

        if genre == "pattern":
            donnees = e["donnees"]
            if not 0 <= num <= PATTERN_MAX:
                raise ValueError("pattern hors limites : %d" % num)
            if len(donnees) != PATTERN_TAILLE:
                raise ValueError("pattern %d : %d octets au lieu de %d"
                                 % (num, len(donnees), PATTERN_TAILLE))
            buf = (ctypes.c_uint8 * len(donnees)).from_buffer_copy(donnees)
            buffers.append(buf)
            items[i].type = TYPE_PATTERN
            items[i].number = num
            items[i].quality = 16
            items[i].compress = 0
            items[i].fs = STREAM_RATE
            items[i].size = len(donnees)
            items[i].data = ctypes.cast(buf, ctypes.POINTER(ctypes.c_uint8))
            detail.append({"slot": num, "nom": e.get("nom", "pattern %d" % num),
                           "genre": "pattern"})

        elif genre == "effacer":
            if not 0 <= num <= SLOT_MAX:
                raise ValueError("slot hors limites : %d" % num)
            items[i].type = TYPE_ERASE
            items[i].number = num
            items[i].quality = 16
            items[i].compress = 0
            items[i].fs = STREAM_RATE
            items[i].size = 0
            items[i].data = None
            detail.append({"slot": num, "nom": "<efface>", "genre": "effacer"})

        else:
            if not 0 <= num <= SLOT_MAX:
                raise ValueError("slot hors limites : %d" % num)
            son = e["sample"]
            pcm = _pcm16(son)
            buf = (ctypes.c_uint8 * len(pcm)).from_buffer_copy(pcm)
            buffers.append(buf)
            items[i].type = TYPE_SAMPLE
            items[i].number = num
            items[i].quality = max(8, min(16, int(quality)))
            items[i].compress = 1 if compress else 0
            items[i].fs = son.rate
            items[i].size = len(pcm)
            items[i].data = ctypes.cast(buf, ctypes.POINTER(ctypes.c_uint8))
            detail.append({"slot": num, "nom": e.get("nom", son.name),
                           "genre": "sample",
                           "duree_ms": round(son.duration_ms, 1)})

    return _rendre(lib, items, len(elements), out_path, detail)


def _rendre(lib, items, count, out_path, detail):
    ptr = ctypes.POINTER(ctypes.c_int16)()
    frames = ctypes.c_uint32(0)

    code = lib.volcagain_render(items, count, ctypes.byref(ptr),
                                ctypes.byref(frames))
    if code != 0:
        raise RuntimeError("Syro : " + ERREURS.get(code, "code %d" % code))

    try:
        _ecrire_stereo(out_path, ptr, frames.value)
    finally:
        lib.volcagain_free(ptr)

    return {
        "chemin": out_path,
        "duree_s": round(frames.value / float(STREAM_RATE), 1),
        "slots": detail,
    }


# ---------------------------------------------------------------- lecture
def jouer(path, bloquant=False):
    """Joue le WAV de transfert par la sortie audio.

    Branche un jack de la sortie casque vers SYNC IN de la volca, volume a
    fond, et surtout : desactive tout egaliseur / reduction de volume.
    """
    if "ANDROID_ARGUMENT" in os.environ:
        try:
            from kivy.core.audio import SoundLoader
            son = SoundLoader.load(path)
            if son:
                son.volume = 1.0
                son.play()
                return son
            raise RuntimeError("SoundLoader n'a pas pu ouvrir le fichier")
        except Exception as e:  # noqa: BLE001
            raise RuntimeError("lecture impossible : %s" % e)

    if platform.system() == "Windows":
        import winsound
        flags = winsound.SND_FILENAME
        if not bloquant:
            flags |= winsound.SND_ASYNC
        winsound.PlaySound(path, flags)
        return None

    import shutil
    import subprocess
    for prog in ("aplay", "paplay", "afplay", "play"):
        if shutil.which(prog):
            if bloquant:
                subprocess.run([prog, path], check=False)
            else:
                subprocess.Popen([prog, path])
            return None
    raise RuntimeError("aucun lecteur audio trouve (installe aplay ou sox)")
