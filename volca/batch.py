"""Traitement par lot d'un dossier de samples."""

import os

from . import audio

EXTS = (".wav", ".WAV")


def list_wavs(folder):
    if os.path.isfile(folder):
        return [folder]
    out = []
    for root, _dirs, files in os.walk(folder):
        for f in sorted(files):
            if f.endswith(EXTS):
                out.append(os.path.join(root, f))
    return out


def process_folder(src, dst, preset="punch", extra_gain_db=0.0,
                   progress=None):
    """Traite tous les WAV de src -> dst. Renvoie la liste des rapports."""
    os.makedirs(dst, exist_ok=True)
    files = list_wavs(src)
    rapports = []
    for i, path in enumerate(files):
        try:
            s = audio.read_wav(path)
            s, rap = audio.process(s, preset, extra_gain_db)
            out_path = os.path.join(dst, os.path.basename(path))
            audio.write_wav(out_path, s)
            rap["fichier"] = os.path.basename(path)
            rap["sortie"] = out_path
            rap["ok"] = True
        except Exception as e:  # noqa: BLE001
            rap = {"fichier": os.path.basename(path), "ok": False,
                   "erreur": str(e)}
        rapports.append(rap)
        if progress:
            progress(i + 1, len(files), rap)
    return rapports


def resume(rapports):
    ok = [r for r in rapports if r.get("ok")]
    ko = [r for r in rapports if not r.get("ok")]
    lignes = ["%d fichier(s) traite(s), %d erreur(s)" % (len(ok), len(ko))]
    for r in ok:
        lignes.append("  %-28s %+6.1f dB  ->  RMS %.1f dB / crete %.1f dB" % (
            r["fichier"][:28], r["gain_db"],
            r["apres"]["rms_db"], r["apres"]["peak_db"]))
    for r in ko:
        lignes.append("  %-28s ECHEC : %s" % (r["fichier"][:28], r["erreur"]))
    return "\n".join(lignes)
