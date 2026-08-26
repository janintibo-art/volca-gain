"""
Import des sauvegardes du librarian Korg (.vlcspllib).

Format decouvert par analyse d'un fichier reel, pas documente par Korg.

Une sauvegarde est une archive ZIP contenant :

    FileInformation.xml     produit, nombre de programmes et de samples
    Smpl_NNN.smpl_info      XML : nom, MD5, longueur, niveau, vitesse
    Smpl_NNN.smpl_bin       PCM 16 bits mono brut, petit-boutiste
    Prog_NNN.prog_info      XML : nom du programme
    Prog_NNN.prog_bin       le pattern, format binaire

Les emplacements vides n'ont pas de .smpl_bin : seul le .smpl_info existe.

Les patterns different selon la machine :
    volca sample  : 2624 octets, 10 parties de 256   (volca.pattern)
    volca sample2 : 7936 octets, 10 parties de 768   (ici)
"""

import os
import re
import struct
import zipfile

from . import audio, project

# Frequence interne de la volca. Les .smpl_bin ne portent aucune en-tete :
# c'est du PCM brut, il faut donc connaitre le taux pour les relire.
TAUX_VOLCA = 31250

INFO_FICHIER = "FileInformation.xml"

# Disposition d'un programme volca sample2
PROG2_TAILLE = 7936
PROG2_DEBUT_PARTIES = 0x80
PROG2_TAILLE_PARTIE = 768
PROG2_NB_PARTIES = 10

MODELES_KORG = {"volca sample 2": "sample2", "volca sample": "sample"}


class FormatInvalide(ValueError):
    pass


# --------------------------------------------------------------------------
def _balise(xml, nom):
    m = re.search(r"<%s>(.*?)</%s>" % (nom, nom), xml, re.S)
    return m.group(1).strip() if m else ""


def _nom_sur(nom):
    ok = ("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
          "0123456789-_ ")
    net = "".join(c if c in ok else "_" for c in nom).strip()
    return (net[:40] or "sample").strip("_ ")


# --------------------------------------------------------------------------
def infos(chemin):
    """Fiche d'une sauvegarde, sans rien extraire."""
    with zipfile.ZipFile(chemin, "r") as z:
        if INFO_FICHIER not in z.namelist():
            raise FormatInvalide(
                "ce zip n'est pas une sauvegarde du librarian Korg "
                "(%s absent)" % INFO_FICHIER)
        xml = z.read(INFO_FICHIER).decode("utf-8", "replace")
        noms = z.namelist()

    produit = _balise(xml, "Product") or "?"
    m = re.search(r'NumProgramData="(\d+)"\s+NumSampleData="(\d+)"', xml)
    nb_prog, nb_smpl = (int(m.group(1)), int(m.group(2))) if m else (0, 0)
    return {
        "produit": produit,
        "modele": MODELES_KORG.get(produit.lower(), "sample2"),
        "programmes": nb_prog,
        "emplacements": nb_smpl,
        "sons": sum(1 for n in noms if n.endswith(".smpl_bin")),
    }


# --------------------------------------------------------------------------
def _pcm_vers_sample(brut, nom, taux=TAUX_VOLCA):
    """PCM 16 bits brut -> Sample, reechantillonne en 44,1 kHz."""
    n = len(brut) // 2
    if n == 0:
        return None
    vals = struct.unpack("<%dh" % n, brut[:n * 2])
    s = audio.Sample([v / 32768.0 for v in vals], taux, nom)
    if taux != audio.TARGET_RATE:
        s.data = audio.resample_linear(s.data, taux, audio.TARGET_RATE)
        s.rate = audio.TARGET_RATE
    return s


def importer(chemin, dossier_cible, taux=TAUX_VOLCA, progression=None):
    """Extrait les sons d'une sauvegarde et renvoie un Projet.

    Les WAV sont ecrits tels quels, sans traitement : c'est une
    restauration, pas une amelioration. Tu pourras traiter ensuite.
    """
    fiche = infos(chemin)
    base = os.path.join(dossier_cible,
                        _nom_sur(os.path.splitext(os.path.basename(chemin))[0]))
    os.makedirs(base, exist_ok=True)

    p = project.Projet(os.path.basename(base), fiche["modele"])
    rapport = []

    with zipfile.ZipFile(chemin, "r") as z:
        presents = set(z.namelist())
        bins = sorted(n for n in presents if n.endswith(".smpl_bin"))
        for compteur, interne in enumerate(bins, 1):
            num = int(re.search(r"Smpl_(\d+)", interne).group(1))
            nom = "slot %d" % num
            fiche_smpl = "Smpl_%03d.smpl_info" % num
            if fiche_smpl in presents:
                x = z.read(fiche_smpl).decode("utf-8", "replace")
                nom = _balise(x, "Name") or nom
            try:
                s = _pcm_vers_sample(z.read(interne), nom, taux)
                if s is None or not s.data:
                    raise FormatInvalide("donnees vides")
                cible = os.path.join(base, "%03d_%s.wav" % (num, _nom_sur(nom)))
                audio.write_wav(cible, s)
                if num < p.nb_slots:
                    p.assigner(num, cible, "doux", 0.0)
                    p.renommer(num, nom)
                rapport.append({"slot": num, "nom": nom,
                                "duree_ms": round(s.duration_ms, 1)})
            except Exception as e:  # noqa: BLE001
                rapport.append({"slot": num, "nom": nom, "erreur": str(e)})
            if progression:
                progression(compteur, len(bins), num, nom)

    p.sauver(os.path.join(base, "%s.volca.json" % _nom_sur(p.nom)))
    return p, rapport


# --------------------------------------------------------------------------
# Programmes (patterns)
# --------------------------------------------------------------------------
def lire_programme(brut, nom="programme"):
    """Decode un Prog_NNN.prog_bin de volca sample2.

    Renvoie un dictionnaire lisible. L'ecriture n'est pas geree : le SDK
    Korg embarque ne sait envoyer que les patterns de 2624 octets de la
    volca sample premiere generation.
    """
    if len(brut) != PROG2_TAILLE:
        raise FormatInvalide("programme de %d octets, attendu %d"
                             % (len(brut), PROG2_TAILLE))
    if brut[:4] != b"PTST":
        raise FormatInvalide("en-tete PTST absente")
    if brut[-4:] != b"PTED":
        raise FormatInvalide("pied PTED absent")

    interne = brut[0x10:0x30].split(b"\x00")[0].decode("ascii", "replace")
    parties = []
    for i in range(PROG2_NB_PARTIES):
        d = PROG2_DEBUT_PARTIES + i * PROG2_TAILLE_PARTIE
        num, pas, accent, _r = struct.unpack("<HHHH", brut[d:d + 8])
        func = brut[d + 20]
        parties.append({
            "partie": i + 1,
            "sample": num,
            "pas": pas,
            "liste_pas": [n + 1 for n in range(16) if pas & (1 << n)],
            "level": brut[d + 8],
            "func": func,
            "loop": bool(func & 0b10),
            "reverb": bool(func & 0b100),
            "reverse": bool(func & 0b1000),
            "mute": bool(func & 0b10000),
        })
    return {"nom": interne or nom,
            "parties": parties,
            "utilisees": [p for p in parties if p["pas"]]}


def programmes(chemin):
    """Liste les programmes d'une sauvegarde, decodes."""
    out = []
    with zipfile.ZipFile(chemin, "r") as z:
        presents = set(z.namelist())
        for interne in sorted(n for n in presents if n.endswith(".prog_bin")):
            num = int(re.search(r"Prog_(\d+)", interne).group(1))
            nom = "programme %d" % num
            fiche = "Prog_%03d.prog_info" % num
            if fiche in presents:
                x = z.read(fiche).decode("utf-8", "replace")
                nom = _balise(x, "Name") or nom
            try:
                d = lire_programme(z.read(interne), nom)
                d["index"] = num
                d["nom"] = nom
                out.append(d)
            except Exception as e:  # noqa: BLE001
                out.append({"index": num, "nom": nom, "erreur": str(e)})
    return out


def grille(prog):
    """Rendu texte d'un programme decode."""
    lignes = ["      " + "".join("%-2d" % (i + 1) for i in range(16))]
    for p in prog["parties"]:
        marques = "".join("X " if p["pas"] & (1 << i) else ". "
                          for i in range(16))
        lignes.append("P%-2d s%-4d %s" % (p["partie"], p["sample"], marques))
    return "\n".join(lignes)
