"""
Petit etat persistant : ce que l'application doit retrouver au lancement.

Pour l'instant : le dernier projet ouvert, pour ne pas avoir a le rouvrir
a chaque demarrage. Volontairement separe des presets et des projets, qui
sont des donnees que l'utilisateur manipule ; ici c'est de la commodite.
"""

import json
import os

FICHIER = "etat.volca.json"


def chemin_defaut(dossier=None):
    if dossier is None:
        dossier = os.environ.get("ANDROID_PRIVATE") or os.getcwd()
    return os.path.join(dossier, FICHIER)


def _lire(chemin):
    if not os.path.isfile(chemin):
        return {}
    try:
        with open(chemin, "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _ecrire(chemin, data):
    try:
        with open(chemin, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception:  # noqa: BLE001
        return False


def memoriser_projet(chemin_projet, chemin=None):
    chemin = chemin or chemin_defaut()
    d = _lire(chemin)
    d["dernier_projet"] = chemin_projet
    return _ecrire(chemin, d)


def dernier_projet(chemin=None):
    """Renvoie le chemin du dernier projet, s'il existe encore."""
    p = _lire(chemin or chemin_defaut()).get("dernier_projet")
    return p if p and os.path.isfile(p) else None


def oublier(chemin=None):
    chemin = chemin or chemin_defaut()
    d = _lire(chemin)
    d.pop("dernier_projet", None)
    return _ecrire(chemin, d)
