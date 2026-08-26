"""
Patterns de la volca sample.

Format documente dans le SDK Korg (pattern/volcasample_pattern.h) et
reproduit ici en Python pur, sans dependance.

Un pattern fait exactement 2624 octets (0xA40) :

    +0x000  Header "PTST" (4) | DevCode 0x33b8 (2) | reserve (2)
            ActiveStep (2) | padding (22)                       = 32 octets
    +0x020  Part[10], 256 octets chacune                        = 2560
    +0xA20  padding (28) | Footer "PTED" (4)                    = 32
                                                        total   = 2624

Et chaque partie, 256 octets :

    SampleNum (2) | StepOn (2) | Accent (2) | Reserved (2)
    Level (1) | Param[11] | FuncMemoryPart (1) | Padding1[11]
    Motion[14][16]

Tout est en petit-boutiste.
"""

import os
import struct

from . import audio

TAILLE = 0xA40          # 2624 octets
TAILLE_PARTIE = 0x100   # 256 octets
NB_PARTIES = 10
NB_PAS = 16
NB_MOTION = 14
NB_PARAM = 11

HEADER = 0x54535450     # "PTST"
FOOTER = 0x44455450     # "PTED"
DEVCODE = 0x33B8

# Potards, dans l'ordre du tableau Param
PARAMS = ["level", "pan", "speed", "ampeg_attack", "ampeg_decay",
          "pitcheg_int", "pitcheg_attack", "pitcheg_decay",
          "start_point", "length", "hicut"]

# Drapeaux de FuncMemoryPart
BIT_MOTION = 0
BIT_LOOP = 1
BIT_REVERB = 2
BIT_REVERSE = 3
BIT_MUTE = 4

FONCTIONS = {"motion": BIT_MOTION, "loop": BIT_LOOP, "reverb": BIT_REVERB,
             "reverse": BIT_REVERSE, "mute": BIT_MUTE}

# Valeurs de depart d'une partie neuve.
# Elles paraissent neutres a l'oreille, mais elles ne sont PAS forcement
# celles de VolcaSample_Pattern_Init du SDK : pour coller exactement a
# l'usine, pars d'un preset avec Motif.charger(preset_pattern_01.dat).
DEFAUTS = {"level": 127, "pan": 64, "speed": 64, "ampeg_attack": 0,
           "ampeg_decay": 127, "pitcheg_int": 64, "pitcheg_attack": 0,
           "pitcheg_decay": 0, "start_point": 0, "length": 127,
           "hicut": 127}


class FormatInvalide(ValueError):
    pass


# --------------------------------------------------------------------------
class Partie:
    """Une des 10 parties d'un pattern."""

    def __init__(self, numero=0):
        self.numero = numero
        self.sample_num = 0
        self.pas = 0                 # masque de bits, b0 = pas 1
        self.accent = 0              # non gere par la machine
        self.level = 127
        self.params = dict(DEFAUTS)
        self.func = 0
        self.motion = [[0] * NB_PAS for _ in range(NB_MOTION)]

    # ------------------------------------------------------------ pas
    def pas_actif(self, i):
        return bool(self.pas & (1 << i))

    def mettre_pas(self, i, actif=True):
        if not 0 <= i < NB_PAS:
            raise ValueError("pas hors limites : %d" % i)
        if actif:
            self.pas |= (1 << i)
        else:
            self.pas &= ~(1 << i)
        return self

    def basculer_pas(self, i):
        return self.mettre_pas(i, not self.pas_actif(i))

    def depuis_liste(self, indices):
        """Active les pas donnes, en numerotation musicale 1 a 16."""
        self.pas = 0
        for n in indices:
            self.mettre_pas(int(n) - 1, True)
        return self

    def liste_pas(self):
        return [i + 1 for i in range(NB_PAS) if self.pas_actif(i)]

    def vide(self):
        return self.pas == 0

    # ------------------------------------------------------------ fonctions
    def actif(self, nom):
        return bool(self.func & (1 << FONCTIONS[nom]))

    def mettre(self, nom, valeur=True):
        b = 1 << FONCTIONS[nom]
        if valeur:
            self.func |= b
        else:
            self.func &= ~b
        return self

    def fonctions_actives(self):
        return [n for n in FONCTIONS if self.actif(n)]

    # ------------------------------------------------------------ binaire
    def to_bytes(self):
        out = struct.pack("<HHHH", self.sample_num & 0xFFFF,
                          self.pas & 0xFFFF, self.accent & 0xFFFF, 0)
        out += bytes([self.level & 0x7F])
        out += bytes(max(0, min(127, int(self.params.get(p, 0))))
                     for p in PARAMS)
        out += bytes([self.func & 0xFF])
        out += bytes(11)
        for piste in self.motion:
            out += bytes(v & 0xFF for v in piste)
        if len(out) != TAILLE_PARTIE:
            raise FormatInvalide("partie de %d octets au lieu de %d"
                                 % (len(out), TAILLE_PARTIE))
        return out

    @classmethod
    def from_bytes(cls, brut, numero=0):
        if len(brut) != TAILLE_PARTIE:
            raise FormatInvalide("partie de %d octets" % len(brut))
        p = cls(numero)
        p.sample_num, p.pas, p.accent, _ = struct.unpack("<HHHH", brut[:8])
        p.level = brut[8]
        p.params = {nom: brut[9 + i] for i, nom in enumerate(PARAMS)}
        p.func = brut[9 + NB_PARAM]
        base = 32
        p.motion = [list(brut[base + i * NB_PAS: base + (i + 1) * NB_PAS])
                    for i in range(NB_MOTION)]
        return p

    def resume(self):
        f = ",".join(self.fonctions_actives()) or "-"
        return "part %2d  sample %3d  pas %-28s  niv %3d  [%s]" % (
            self.numero + 1, self.sample_num,
            " ".join(str(n) for n in self.liste_pas()) or "aucun",
            self.level, f)


# --------------------------------------------------------------------------
class Motif:
    """Un pattern complet : 10 parties de 16 pas."""

    def __init__(self, nom="pattern"):
        self.nom = nom
        self.pas_actifs = 0xFFFF     # les 16 pas jouent
        self.parties = [Partie(i) for i in range(NB_PARTIES)]

    # ------------------------------------------------------------ binaire
    def to_bytes(self):
        out = struct.pack("<IHH", HEADER, DEVCODE, 0)
        out += struct.pack("<H", self.pas_actifs & 0xFFFF)
        out += bytes(0x16)
        for p in self.parties:
            out += p.to_bytes()
        out += bytes(0x1C)
        out += struct.pack("<I", FOOTER)
        if len(out) != TAILLE:
            raise FormatInvalide("pattern de %d octets au lieu de %d"
                                 % (len(out), TAILLE))
        return out

    @classmethod
    def from_bytes(cls, brut, nom="pattern"):
        if len(brut) != TAILLE:
            raise FormatInvalide(
                "taille %d octets, attendu %d : ce fichier n'est pas un "
                "pattern volca sample" % (len(brut), TAILLE))
        entete, dev, _res, actifs = struct.unpack("<IHHH", brut[:10])
        if entete != HEADER:
            raise FormatInvalide("en-tete PTST absente")
        pied = struct.unpack("<I", brut[TAILLE - 4:])[0]
        if pied != FOOTER:
            raise FormatInvalide("pied PTED absent")
        m = cls(nom)
        m.pas_actifs = actifs
        if dev != DEVCODE:
            m.devcode_inattendu = dev
        for i in range(NB_PARTIES):
            d = 0x20 + i * TAILLE_PARTIE
            m.parties[i] = Partie.from_bytes(brut[d:d + TAILLE_PARTIE], i)
        return m

    # ------------------------------------------------------------ fichier
    @classmethod
    def charger(cls, chemin):
        with open(chemin, "rb") as f:
            brut = f.read()
        nom = os.path.splitext(os.path.basename(chemin))[0]
        return cls.from_bytes(brut, nom)

    def sauver(self, chemin):
        with open(chemin, "wb") as f:
            f.write(self.to_bytes())
        return chemin

    # ------------------------------------------------------------ confort
    def partie(self, numero):
        """Numerotation musicale : partie 1 a 10."""
        if not 1 <= numero <= NB_PARTIES:
            raise ValueError("partie hors limites : %d" % numero)
        return self.parties[numero - 1]

    def parties_utilisees(self):
        return [p for p in self.parties if not p.vide()]

    def vider(self):
        self.parties = [Partie(i) for i in range(NB_PARTIES)]
        return self

    def resume(self):
        lignes = ["Pattern '%s' - %d partie(s) utilisee(s), %d pas actifs"
                  % (self.nom, len(self.parties_utilisees()),
                     bin(self.pas_actifs).count("1"))]
        for p in self.parties_utilisees():
            lignes.append("  " + p.resume())
        if not self.parties_utilisees():
            lignes.append("  (vide)")
        return "\n".join(lignes)

    def grille(self):
        """Rendu texte de la grille, pratique en console."""
        lignes = ["      " + "".join("%-2d" % (i + 1) for i in range(NB_PAS))]
        for p in self.parties:
            marques = "".join("X " if p.pas_actif(i) else ". "
                              for i in range(NB_PAS))
            lignes.append("P%-2d s%-3d %s" % (p.numero + 1, p.sample_num,
                                              marques))
        return "\n".join(lignes)


# --------------------------------------------------------------------------
def poser(melange, motif, sons, rate, par_pas, offset_pas=0):
    """Mele un pattern dans un tampon deja alloue, a partir d'un pas donne.

    Sert a la fois pour l'ecoute d'un pattern seul et pour l'enchainement
    d'un morceau entier : les queues de sons debordent naturellement sur
    la suite, comme sur la machine.
    """
    for p in motif.parties_utilisees():
        if p.actif("mute"):
            continue
        s = sons.get(p.sample_num)
        if s is None or not s.data:
            continue
        niveau = max(0.0, min(1.0, p.level / 127.0))
        data = s.data[::-1] if p.actif("reverse") else s.data
        for i in range(NB_PAS):
            if not p.pas_actif(i):
                continue
            d = int((offset_pas + i) * par_pas * rate)
            for j, v in enumerate(data):
                k = d + j
                if k >= len(melange):
                    break
                melange[k] += v * niveau
    return melange


def duree_pas(bpm):
    """Duree d'un pas, une double croche, en secondes."""
    return 15.0 / max(bpm, 1.0)


def queue_max(sons):
    return max((len(s.data) for s in sons.values() if s), default=0)


def rendu(motif, sons, bpm=120.0, rate=None):
    """Fabrique l'audio d'un pattern, pour l'ecouter avant de l'envoyer.

    motif : le Motif a jouer
    sons  : {numero_de_sample: audio.Sample} - les sons disponibles
    bpm   : tempo. Un pas vaut une double croche.

    Les parties muettes sont ignorees, comme sur la machine. Le melange
    est ensuite ramene sous le plafond pour ne pas saturer.
    """
    rate = rate or audio.TARGET_RATE
    par_pas = duree_pas(bpm)
    total = int(rate * par_pas * NB_PAS)
    if total <= 0:
        return audio.Sample([], rate, motif.nom)

    melange = [0.0] * (total + queue_max(sons))
    poser(melange, motif, sons, rate, par_pas, 0)

    out = audio.Sample(melange, rate, motif.nom)
    crete = out.peak()
    if crete > 0:
        audio.apply_gain(out, min(0.0, -1.0 - audio.lin_to_db(crete)))
    return out


def vierge(nom="pattern"):
    return Motif(nom)


def infos(chemin):
    """Fiche rapide d'un fichier pattern."""
    m = Motif.charger(chemin)
    return {"nom": m.nom, "parties": len(m.parties_utilisees()),
            "pas_actifs": bin(m.pas_actifs).count("1"),
            "samples": sorted({p.sample_num for p in m.parties_utilisees()})}
