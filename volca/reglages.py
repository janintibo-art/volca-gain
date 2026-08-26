"""
Presets personnalises.

Les presets d'usine de volca.audio couvrent les cas courants. Ce module
permet d'en creer d'autres, de les enregistrer dans un fichier JSON et de
les retrouver au lancement suivant, dans l'application comme en ligne de
commande.

Un preset personnalise part toujours d'un preset d'usine : on ne modifie
que les reglages qu'on veut changer.
"""

import json
import os

from . import audio

FICHIER = "presets.volca.json"

# Reglages exposes a l'utilisateur, avec bornes et libelle.
# (cle, libelle, mini, maxi, pas, unite)
REGLAGES = [
    ("hp", "Passe-haut", 0.0, 250.0, 5.0, "Hz"),
    ("sat_drive", "Saturation force", 0.0, 4.0, 0.1, ""),
    ("sat_mix", "Saturation dosage", 0.0, 1.0, 0.05, ""),
    ("comp_threshold", "Compression seuil", -40.0, 0.0, 1.0, "dB"),
    ("comp_ratio", "Compression taux", 1.0, 10.0, 0.5, ":1"),
    ("tr_attack", "Transitoire attaque", -6.0, 6.0, 0.5, "dB"),
    ("tr_sustain", "Transitoire tenue", -6.0, 6.0, 0.5, "dB"),
    ("porte", "Porte de bruit", -80.0, -20.0, 1.0, "dB"),
    ("cible", "Niveau vise", -24.0, -6.0, 0.5, "dB"),
    ("ceiling", "Plafond", -3.0, -0.1, 0.1, "dB"),
    ("xfade", "Raccord de boucle", 0.0, 60.0, 1.0, "ms"),
]


def chemin_defaut(dossier=None):
    if dossier is None:
        dossier = os.environ.get("ANDROID_PRIVATE") or os.getcwd()
    return os.path.join(dossier, FICHIER)


# --------------------------------------------------------------------------
# Conversion : reglages a plat <-> configuration interne
# --------------------------------------------------------------------------
def a_plat(cfg):
    """Configuration interne -> dictionnaire de reglages simples."""
    r = {
        "hp": cfg.get("hp") or 0.0,
        "ceiling": cfg.get("ceiling", -0.3),
        "xfade": cfg.get("xfade") or 0.0,
    }
    sat = cfg.get("sat") or {}
    r["sat_drive"] = sat.get("drive", 0.0)
    r["sat_mix"] = sat.get("mix", 0.0)
    comp = cfg.get("compress") or {}
    r["comp_threshold"] = comp.get("threshold_db", 0.0)
    r["comp_ratio"] = comp.get("ratio", 1.0)
    tr = cfg.get("transient") or {}
    r["tr_attack"] = tr.get("attack_db", 0.0)
    r["tr_sustain"] = tr.get("sustain_db", 0.0)
    pt = cfg.get("porte") or {}
    r["porte"] = pt.get("seuil_db", -80.0)
    if cfg.get("lufs") is not None:
        r["cible"] = cfg["lufs"]
    elif cfg.get("rms") is not None:
        r["cible"] = cfg["rms"]
    else:
        r["cible"] = -24.0
    return r


def depuis_plat(base, r, mode_cible="rms"):
    """Reglages simples -> configuration interne, a partir d'une base."""
    cfg = dict(base)
    cfg["hp"] = r["hp"] if r["hp"] > 0 else None
    cfg["ceiling"] = r["ceiling"]
    cfg["xfade"] = r["xfade"] if r["xfade"] > 0 else None

    if r["sat_mix"] > 0 and r["sat_drive"] > 0:
        cfg["sat"] = {"drive": r["sat_drive"], "mix": r["sat_mix"]}
    else:
        cfg["sat"] = None

    if r["comp_ratio"] > 1.0:
        comp = dict(base.get("compress") or {})
        comp["threshold_db"] = r["comp_threshold"]
        comp["ratio"] = r["comp_ratio"]
        comp.setdefault("attack_ms", 8.0)
        comp.setdefault("release_ms", 90.0)
        cfg["compress"] = comp
    else:
        cfg["compress"] = None

    if r["tr_attack"] or r["tr_sustain"]:
        cfg["transient"] = {"attack_db": r["tr_attack"],
                            "sustain_db": r["tr_sustain"]}
    else:
        cfg["transient"] = None

    cfg["porte"] = {"seuil_db": r["porte"]} if r["porte"] > -79.0 else None

    if mode_cible == "lufs":
        cfg["lufs"] = r["cible"]
        cfg["rms"] = None
    else:
        cfg["rms"] = r["cible"]
        cfg["lufs"] = None
    return cfg


# --------------------------------------------------------------------------
# Fichier
# --------------------------------------------------------------------------
def charger(chemin=None):
    """Lit les presets personnalises et les ajoute a audio.PRESETS."""
    chemin = chemin or chemin_defaut()
    if not os.path.isfile(chemin):
        return {}
    try:
        with open(chemin, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:  # noqa: BLE001
        return {}
    perso = data.get("presets", {})
    for nom, cfg in perso.items():
        cfg["perso"] = True
        audio.PRESETS[nom] = cfg
    return perso


def sauver(nom, cfg, chemin=None):
    """Enregistre un preset personnalise et l'active immediatement."""
    nom = nom.strip()
    if not nom:
        raise ValueError("nom vide")
    if nom in audio.PRESETS and not audio.PRESETS[nom].get("perso"):
        raise ValueError("'%s' est un preset d'usine, choisis un autre nom"
                         % nom)
    chemin = chemin or chemin_defaut()
    data = {"format": 1, "presets": {}}
    if os.path.isfile(chemin):
        try:
            with open(chemin, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:  # noqa: BLE001
            pass
    cfg = dict(cfg)
    cfg["perso"] = True
    cfg.setdefault("desc", "Preset personnalise")
    data.setdefault("presets", {})[nom] = cfg
    with open(chemin, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    audio.PRESETS[nom] = cfg
    return chemin


def supprimer(nom, chemin=None):
    chemin = chemin or chemin_defaut()
    if not os.path.isfile(chemin):
        return False
    with open(chemin, "r", encoding="utf-8") as f:
        data = json.load(f)
    if nom not in data.get("presets", {}):
        return False
    del data["presets"][nom]
    with open(chemin, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    if audio.PRESETS.get(nom, {}).get("perso"):
        del audio.PRESETS[nom]
    return True


def persos():
    return sorted(n for n, c in audio.PRESETS.items() if c.get("perso"))


def usine():
    return sorted(n for n, c in audio.PRESETS.items() if not c.get("perso"))
