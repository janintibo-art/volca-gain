#!/usr/bin/env python3
"""
volca-gain en ligne de commande.

Le traitement audio n'a AUCUNE dependance (marche dans Termux tel quel).
L'envoi direct necessite la bibliotheque native (voir : python cli.py syro).

    python cli.py info samples/
    python cli.py traiter samples/ -o out/ -p punch
    python cli.py projet creer mon_kit --dossier out/
    python cli.py projet voir mon_kit.volca.json
    python cli.py envoyer mon_kit.volca.json --jouer
    python cli.py rapide 3 kick.wav --jouer
    python cli.py effacer 3,4,5 --jouer
    python cli.py syro
"""

import argparse
import os
import sys

from volca import __version__, audio, batch, project, syro


# ------------------------------------------------------------------ helpers
def _parse_slots(txt):
    """'0,3,7-9' -> [0,3,7,8,9]"""
    out = []
    for bloc in txt.split(","):
        bloc = bloc.strip()
        if not bloc:
            continue
        if "-" in bloc:
            a, b = bloc.split("-", 1)
            out.extend(range(int(a), int(b) + 1))
        else:
            out.append(int(bloc))
    return sorted(set(out))


def _apres_envoi(res, jouer):
    print("Flux genere : %s" % res["chemin"])
    print("Duree du transfert : %.1f s" % res["duree_s"])
    for s in res["slots"]:
        print("  slot %02d  %s" % (s["slot"], s["nom"]))
    print()
    print("Branche la sortie casque sur SYNC IN de la volca.")
    print("Volume a fond, aucun egaliseur, ne touche a rien pendant l'envoi.")
    if jouer:
        print("Lecture...")
        syro.jouer(res["chemin"], bloquant=True)
        print("Termine.")
    else:
        print("Joue ce fichier, ou relance avec --jouer.")


# ------------------------------------------------------------------ actions
def cmd_info(a):
    cibles = []
    for e in a.entree:
        cibles.extend(batch.list_wavs(e))
    if not cibles:
        print("Aucun WAV trouve.")
        return 1
    for p in cibles:
        try:
            i = audio.read_wav(p).info()
            drapeau = "  <- faible" if i["rms_db"] < -20 else ""
            print("%-30s %7.0f ms  crete %6.1f dB  RMS %6.1f dB%s" % (
                os.path.basename(p)[:30], i["duree_ms"],
                i["peak_db"], i["rms_db"], drapeau))
        except Exception as e:  # noqa: BLE001
            print("%-30s ERREUR : %s" % (os.path.basename(p)[:30], e))
    return 0


def cmd_presets(_a):
    for nom, cfg in audio.PRESETS.items():
        print("%-8s %s" % (nom, cfg["desc"]))
    return 0


def cmd_traiter(a):
    src = a.entree
    if os.path.isfile(src):
        out = a.sortie or os.path.splitext(src)[0] + "_volca.wav"
        if os.path.isdir(out):
            out = os.path.join(out, os.path.basename(src))
        s = audio.read_wav(src)
        s, rap = audio.process(s, a.preset, a.gain)
        audio.write_wav(out, s)
        print("%s -> %s" % (os.path.basename(src), out))
        print("  gain applique : %+.1f dB" % rap["gain_db"])
        print("  avant : crete %6.1f dB / RMS %6.1f dB" % (
            rap["avant"]["peak_db"], rap["avant"]["rms_db"]))
        print("  apres : crete %6.1f dB / RMS %6.1f dB" % (
            rap["apres"]["peak_db"], rap["apres"]["rms_db"]))
        return 0

    dst = a.sortie or os.path.join(src.rstrip("/\\"), "volca_out")

    def prog(i, n, rap):
        print("[%d/%d] %s %s" % (i, n, "ok " if rap.get("ok") else "ECHEC",
                                 rap["fichier"]))

    raps = batch.process_folder(src, dst, a.preset, a.gain, prog)
    print()
    print(batch.resume(raps))
    print()
    print("Sortie : %s" % os.path.abspath(dst))
    return 0


def cmd_projet(a):
    if a.action == "creer":
        p = project.Projet(a.nom, a.modele)
        if a.dossier:
            places = p.remplir_depuis_dossier(a.dossier, a.depart, a.preset)
            print("%d sample(s) place(s)." % len(places))
        chemin = p.sauver(a.nom if a.nom.endswith(".json")
                          else a.nom + ".volca.json")
        print(p.resume())
        print("\nProjet enregistre : %s" % chemin)
        return 0

    if a.action == "voir":
        p = project.Projet.charger(a.nom)
        print(p.resume())
        return 0

    if a.action == "ajouter":
        p = project.Projet.charger(a.nom)
        s = p.assigner(a.slot, a.wav, a.preset, a.gain)
        p.sauver()
        print("slot %02d <- %s (%.0f ms)" % (s.index, s.nom, s.duree_ms))
        return 0

    if a.action == "vider":
        p = project.Projet.charger(a.nom)
        for i in _parse_slots(str(a.slot)):
            p.vider(i)
        p.sauver()
        print("Slots vides dans le projet (utilise 'effacer' pour la volca).")
        return 0

    return 1


def cmd_envoyer(a):
    p = project.Projet.charger(a.projet)
    indices = _parse_slots(a.slots) if a.slots else None
    envoi = p.pour_envoi(indices)
    if not envoi:
        print("Rien a envoyer.")
        return 1
    if p.depassement():
        print("ATTENTION : memoire depassee (%.1f s pour %.0f s)."
              % (p.memoire_utilisee_s(), p.memoire_totale_s()))

    presets = {s.index: (s.preset, s.gain_db) for s in p.occupes()}
    sortie = a.sortie or "transfert.wav"

    # chaque slot peut avoir son propre preset -> on traite avant
    res = None
    tmp = []
    try:
        import tempfile
        d = tempfile.mkdtemp(prefix="volcagain_")
        prepares = []
        for idx, chemin in envoi:
            preset, gain = presets.get(idx, ("punch", 0.0))
            s = audio.read_wav(chemin)
            s, _ = audio.process(s, preset, gain)
            out = os.path.join(d, "%02d.wav" % idx)
            audio.write_wav(out, s)
            tmp.append(out)
            prepares.append((idx, out))
        res = syro.build_stream(prepares, sortie,
                                compress=not a.lineaire,
                                quality=a.qualite)
        noms = {s.index: s.nom for s in p.occupes()}
        for d in res["slots"]:
            d["nom"] = noms.get(d["slot"], d["nom"])
    except syro.SyroIndisponible as e:
        print("Envoi direct indisponible :\n%s" % e)
        print("\nReplie-toi sur le librarian Korg avec les WAV traites.")
        return 2

    _apres_envoi(res, a.jouer)
    return 0


def cmd_rapide(a):
    try:
        res = syro.build_stream([(a.slot, a.wav)], a.sortie or "transfert.wav",
                                compress=not a.lineaire, quality=a.qualite,
                                preset=a.preset, gain_db=a.gain)
    except syro.SyroIndisponible as e:
        print("Envoi direct indisponible :\n%s" % e)
        return 2
    _apres_envoi(res, a.jouer)
    return 0


def cmd_effacer(a):
    indices = _parse_slots(a.slots)
    print("Slots a effacer : %s" % ", ".join(str(i) for i in indices))
    if not a.oui:
        rep = input("Confirmer ? (o/N) ").strip().lower()
        if rep not in ("o", "oui", "y"):
            print("Annule.")
            return 1
    try:
        res = syro.erase_stream(indices, a.sortie or "effacement.wav")
    except syro.SyroIndisponible as e:
        print("Envoi direct indisponible :\n%s" % e)
        return 2
    _apres_envoi(res, a.jouer)
    return 0


def cmd_syro(_a):
    if syro.disponible():
        print("Envoi direct : DISPONIBLE (%s)" % syro.version())
        print("Tu n'as plus besoin du librarian Korg.")
        return 0
    print("Envoi direct : indisponible")
    print(syro.raison_indisponible())
    return 1


# ------------------------------------------------------------------ parseur
def build_parser():
    ap = argparse.ArgumentParser(
        prog="volca-gain",
        description="Traitement et transfert de samples pour Korg volca sample")
    ap.add_argument("--version", action="version",
                    version="volca-gain " + __version__)
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("info", help="afficher les niveaux")
    p.add_argument("entree", nargs="+")
    p.set_defaults(func=cmd_info)

    p = sub.add_parser("presets", help="lister les presets")
    p.set_defaults(func=cmd_presets)

    p = sub.add_parser("traiter", help="traiter un fichier ou un dossier")
    p.add_argument("entree")
    p.add_argument("-o", "--sortie")
    p.add_argument("-p", "--preset", default="punch",
                   choices=sorted(audio.PRESETS))
    p.add_argument("-g", "--gain", type=float, default=0.0)
    p.set_defaults(func=cmd_traiter)

    p = sub.add_parser("projet", help="gerer les 100 slots")
    p.add_argument("action", choices=["creer", "voir", "ajouter", "vider"])
    p.add_argument("nom")
    p.add_argument("slot", nargs="?", type=int)
    p.add_argument("wav", nargs="?")
    p.add_argument("--dossier")
    p.add_argument("--depart", type=int, default=0)
    p.add_argument("--modele", default="sample", choices=["sample", "sample2"])
    p.add_argument("-p", "--preset", default="punch",
                   choices=sorted(audio.PRESETS))
    p.add_argument("-g", "--gain", type=float, default=0.0)
    p.set_defaults(func=cmd_projet)

    p = sub.add_parser("envoyer", help="envoyer un projet a la volca")
    p.add_argument("projet")
    p.add_argument("--slots", help="ex: 0,3,7-9 (defaut: tous)")
    p.add_argument("-o", "--sortie")
    p.add_argument("--qualite", type=int, default=16)
    p.add_argument("--lineaire", action="store_true",
                   help="sans compression (transfert plus long)")
    p.add_argument("--jouer", action="store_true")
    p.set_defaults(func=cmd_envoyer)

    p = sub.add_parser("rapide", help="envoyer un seul WAV dans un slot")
    p.add_argument("slot", type=int)
    p.add_argument("wav")
    p.add_argument("-o", "--sortie")
    p.add_argument("-p", "--preset", default="punch",
                   choices=sorted(audio.PRESETS))
    p.add_argument("-g", "--gain", type=float, default=0.0)
    p.add_argument("--qualite", type=int, default=16)
    p.add_argument("--lineaire", action="store_true")
    p.add_argument("--jouer", action="store_true")
    p.set_defaults(func=cmd_rapide)

    p = sub.add_parser("effacer", help="effacer des slots de la volca")
    p.add_argument("slots")
    p.add_argument("-o", "--sortie")
    p.add_argument("--jouer", action="store_true")
    p.add_argument("--oui", action="store_true", help="sans confirmation")
    p.set_defaults(func=cmd_effacer)

    p = sub.add_parser("syro", help="tester l'envoi direct")
    p.set_defaults(func=cmd_syro)

    return ap


def main(argv=None):
    ap = build_parser()
    a = ap.parse_args(argv)
    if not getattr(a, "cmd", None):
        ap.print_help()
        return 1
    return a.func(a)


if __name__ == "__main__":
    sys.exit(main())
