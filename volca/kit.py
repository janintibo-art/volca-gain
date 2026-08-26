"""
Kit portable : un seul fichier zip contenant les sons ET leur agencement.

Un fichier projet ne contient que des chemins. Il ne survit donc pas a un
changement de telephone, ni a un envoi a quelqu'un d'autre. Un kit, si :
il embarque les WAV deja traites, le placement dans les 100 slots, et les
reglages de chaque slot.

Contenu du zip :
    kit.volca.json     le projet, avec des chemins relatifs
    samples/NN_nom.wav un fichier par slot occupe
    LISEZMOI.txt       de quoi s'y retrouver sans l'application
"""

import json
import os
import zipfile

from . import audio, project

NOM_PROJET = "kit.volca.json"
DOSSIER_SONS = "samples"


def _nom_sur(nom):
    """Nom de fichier sans caractere problematique."""
    ok = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_"
    net = "".join(c if c in ok else "_" for c in nom).strip("_")
    return net[:40] or "sample"


def exporter(projet, chemin_zip, traiter=True, progression=None):
    """Ecrit un kit portable.

    traiter=True : les WAV sont ecrits deja traites (preset et gain
    appliques). A l'import, les slots passent donc en preset doux pour ne
    pas traiter le son une deuxieme fois.

    Le taux reduit eventuel n'est PAS applique au fichier : il reste dans
    le projet et sera applique a l'envoi. Sinon l'import, qui relit tout
    en 44,1 kHz, annulerait le gain de memoire.
    """
    occ = projet.occupes()
    if not occ:
        raise ValueError("aucun slot rempli")

    export = project.Projet(projet.nom, projet.modele)
    rapport = []

    with zipfile.ZipFile(chemin_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for n, slot in enumerate(occ, 1):
            try:
                s = audio.read_wav(slot.chemin)
                preset = slot.preset
                if traiter:
                    s, _ = audio.process(s, slot.preset, slot.gain_db)
                    preset = "doux"
                interne = "%s/%02d_%s.wav" % (DOSSIER_SONS, slot.index,
                                              _nom_sur(slot.nom))
                tmp = chemin_zip + ".tmp.wav"
                audio.write_wav(tmp, s)
                z.write(tmp, interne)
                os.remove(tmp)

                copie = project.Slot(
                    slot.index, interne, preset,
                    0.0 if traiter else slot.gain_db,
                    slot.nom, s.duration_ms, slot.taux)
                export.slots[slot.index] = copie
                rapport.append({"slot": slot.index, "nom": slot.nom,
                                "fichier": interne})
            except Exception as e:  # noqa: BLE001
                rapport.append({"slot": slot.index, "nom": slot.nom,
                                "erreur": str(e)})
            if progression:
                progression(n, len(occ), slot)

        data = {"format": 1, "nom": export.nom, "modele": export.modele,
                "slots": [s.to_dict() for s in export.slots if not s.vide],
                "traite": bool(traiter)}
        z.writestr(NOM_PROJET, json.dumps(data, indent=2, ensure_ascii=False))
        z.writestr("LISEZMOI.txt", _lisezmoi(export, traiter))

    return rapport


def _lisezmoi(projet, traite):
    lignes = [
        "KIT MOC'TA BASS pour Korg volca sample",
        "",
        "Ouvre ce zip avec l'application : onglet SLOTS > Kit > Importer.",
        "",
        "Nom      : %s" % projet.nom,
        "Modele   : %s" % projet.modele,
        "Slots    : %d" % len(projet.occupes()),
        "Memoire  : %.1f s sur %.0f s" % (projet.memoire_utilisee_s(),
                                          projet.memoire_totale_s()),
        "Sons     : %s" % ("deja traites" if traite else "bruts"),
        "",
        "Contenu :",
    ]
    for s in projet.occupes():
        taux = ("  %d Hz" % s.taux) if s.taux else ""
        lignes.append("  slot %02d  %-24s %6.0f ms%s" % (
            s.index, s.nom[:24], s.duree_ms, taux))
    lignes += [
        "",
        "Les WAV sont dans samples/. Ce sont des fichiers normaux : tu peux",
        "les utiliser ailleurs. Le placement dans les slots est decrit par",
        "kit.volca.json.",
    ]
    return "\n".join(lignes)


def infos(chemin_zip):
    """Lit la fiche d'un kit sans rien extraire."""
    with zipfile.ZipFile(chemin_zip, "r") as z:
        if NOM_PROJET not in z.namelist():
            raise ValueError("ce zip n'est pas un kit (kit.volca.json absent)")
        data = json.loads(z.read(NOM_PROJET).decode("utf-8"))
    return {"nom": data.get("nom", "?"),
            "modele": data.get("modele", "sample"),
            "slots": len(data.get("slots", [])),
            "traite": data.get("traite", False)}


def importer(chemin_zip, dossier_cible, progression=None):
    """Extrait un kit et renvoie un Projet pret a l'emploi."""
    with zipfile.ZipFile(chemin_zip, "r") as z:
        noms = z.namelist()
        if NOM_PROJET not in noms:
            raise ValueError("ce zip n'est pas un kit (kit.volca.json absent)")
        data = json.loads(z.read(NOM_PROJET).decode("utf-8"))

        base = os.path.join(dossier_cible, _nom_sur(data.get("nom", "kit")))
        os.makedirs(base, exist_ok=True)

        sons = [n for n in noms if n.startswith(DOSSIER_SONS + "/")
                and n.lower().endswith(".wav")]
        for n, interne in enumerate(sons, 1):
            cible = os.path.join(base, os.path.basename(interne))
            with z.open(interne) as src, open(cible, "wb") as dst:
                dst.write(src.read())
            if progression:
                progression(n, len(sons), interne)

    p = project.Projet(data.get("nom", "kit"), data.get("modele", "sample"))
    for d in data.get("slots", []):
        rel = d.get("chemin") or ""
        d = dict(d)
        d["chemin"] = os.path.join(base, os.path.basename(rel))
        p.slots[d["index"]] = project.Slot.from_dict(d)
    chemin = os.path.join(base, "%s.volca.json" % _nom_sur(p.nom))
    p.sauver(chemin)
    return p
