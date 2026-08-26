"""
Bibliotheque : une reserve de patterns et de sons, sans limite de nombre.

A ne pas confondre avec les slots de la machine. La volca a 10 patterns
et 100 ou 200 emplacements de sons ; la bibliotheque, elle, garde tout ce
que tu veux, avec un nom, pour piocher dedans au moment de monter un kit
ou un morceau.

Elle est AUTONOME : les sons y sont copies, pas references. Deplacer ou
supprimer les fichiers d'origine ne casse rien.

Sur le disque :

    bibliotheque/
        index.json          les noms, dates et mesures
        patterns/xxx.dat    un fichier par pattern, format Korg
        sons/xxx.wav        un fichier par son, mono 16 bits 44,1 kHz
"""

import json
import os
import time

from . import audio, pattern

DOSSIER = "bibliotheque"
INDEX = "index.json"


def _nom_sur(nom):
    ok = ("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
          "0123456789-_")
    net = "".join(c if c in ok else "_" for c in nom).strip("_")
    return net[:40].lower() or "sans_nom"


def _cle(txt):
    return "".join(c for c in txt.lower() if c.isalnum())


class Bibliotheque:
    def __init__(self, dossier):
        self.dossier = dossier
        self.d_patterns = os.path.join(dossier, "patterns")
        self.d_sons = os.path.join(dossier, "sons")
        self.chemin_index = os.path.join(dossier, INDEX)
        self.entrees = {"patterns": [], "sons": []}
        self.charger()

    # ------------------------------------------------------------ index
    def charger(self):
        if not os.path.isfile(self.chemin_index):
            return self
        try:
            with open(self.chemin_index, "r", encoding="utf-8") as f:
                data = json.load(f)
            for genre in ("patterns", "sons"):
                self.entrees[genre] = [
                    e for e in data.get(genre, [])
                    if os.path.isfile(self._chemin(genre, e))]
        except Exception:  # noqa: BLE001
            pass
        return self

    def sauver(self):
        os.makedirs(self.dossier, exist_ok=True)
        data = {"format": 1, "patterns": self.entrees["patterns"],
                "sons": self.entrees["sons"]}
        with open(self.chemin_index, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return self.chemin_index

    def _chemin(self, genre, entree):
        base = self.d_patterns if genre == "patterns" else self.d_sons
        return os.path.join(base, entree["fichier"])

    def _identifiant(self, genre, nom):
        """Un nom de fichier libre, meme si le nom est deja pris."""
        base = _nom_sur(nom)
        ext = ".dat" if genre == "patterns" else ".wav"
        pris = {e["fichier"] for e in self.entrees[genre]}
        candidat = base + ext
        n = 2
        while candidat in pris:
            candidat = "%s_%d%s" % (base, n, ext)
            n += 1
        return candidat

    # ------------------------------------------------------------ ajout
    def ajouter_pattern(self, motif, nom=None):
        nom = (nom or motif.nom or "pattern").strip()
        os.makedirs(self.d_patterns, exist_ok=True)
        fichier = self._identifiant("patterns", nom)
        with open(os.path.join(self.d_patterns, fichier), "wb") as f:
            f.write(motif.to_bytes())
        utilisees = motif.parties_utilisees()
        entree = {
            "nom": nom,
            "fichier": fichier,
            "date": int(time.time()),
            "parties": len(utilisees),
            "samples": sorted({p.sample_num for p in utilisees}),
            "motions": sorted({m for p in utilisees
                               for m in p.params_motion()}),
        }
        self.entrees["patterns"].append(entree)
        self.sauver()
        return entree

    def ajouter_son(self, source, nom=None, traiter=None):
        """source : un chemin de WAV, ou un audio.Sample deja en memoire."""
        if isinstance(source, str):
            s = audio.read_wav(source)
            nom = nom or os.path.splitext(os.path.basename(source))[0]
        else:
            s = source
            nom = nom or getattr(s, "name", "son")
        nom = nom.strip()
        if traiter:
            s, _ = audio.process(s, traiter)

        os.makedirs(self.d_sons, exist_ok=True)
        fichier = self._identifiant("sons", nom)
        audio.write_wav(os.path.join(self.d_sons, fichier), s)
        entree = {
            "nom": nom,
            "fichier": fichier,
            "date": int(time.time()),
            "duree_ms": round(s.duration_ms, 1),
            "rms_db": round(s.rms_db(), 1),
            "lufs": round(audio.loudness_lufs(s), 1),
            "taux_conseille": audio.taux_conseille(s),
        }
        self.entrees["sons"].append(entree)
        self.sauver()
        return entree

    # ------------------------------------------------------------ lecture
    def lister(self, genre, filtre=None, tri="nom"):
        out = list(self.entrees.get(genre, []))
        if filtre:
            f = _cle(filtre)
            out = [e for e in out if f in _cle(e["nom"])]
        if tri == "date":
            out.sort(key=lambda e: e.get("date", 0), reverse=True)
        else:
            out.sort(key=lambda e: _cle(e["nom"]))
        return out

    def motif(self, entree):
        m = pattern.Motif.charger(self._chemin("patterns", entree))
        m.nom = entree["nom"]
        return m

    def son(self, entree):
        s = audio.read_wav(self._chemin("sons", entree))
        s.name = entree["nom"]
        return s

    def chemin_son(self, entree):
        return self._chemin("sons", entree)

    # ------------------------------------------------------------ gestion
    def renommer(self, genre, entree, nom):
        nom = (nom or "").strip()
        if not nom:
            raise ValueError("nom vide")
        entree["nom"] = nom[:60]
        self.sauver()
        return entree

    def supprimer(self, genre, entree):
        try:
            os.remove(self._chemin(genre, entree))
        except Exception:  # noqa: BLE001
            pass
        if entree in self.entrees[genre]:
            self.entrees[genre].remove(entree)
        self.sauver()
        return True

    # ------------------------------------------------------------ etat
    def compte(self):
        return {g: len(v) for g, v in self.entrees.items()}

    def taille_octets(self):
        total = 0
        for genre in ("patterns", "sons"):
            for e in self.entrees[genre]:
                try:
                    total += os.path.getsize(self._chemin(genre, e))
                except Exception:  # noqa: BLE001
                    pass
        return total

    def resume(self):
        c = self.compte()
        mo = self.taille_octets() / 1048576.0
        lignes = ["Bibliotheque : %d pattern(s), %d son(s), %.1f Mo"
                  % (c["patterns"], c["sons"], mo)]
        for e in self.lister("patterns")[:20]:
            lignes.append("  P  %-26s %d partie(s)" % (e["nom"][:26],
                                                       e["parties"]))
        for e in self.lister("sons")[:20]:
            lignes.append("  S  %-26s %6.0f ms  RMS %5.1f" % (
                e["nom"][:26], e["duree_ms"], e["rms_db"]))
        return "\n".join(lignes)


def ouvrir(dossier_parent):
    """Ouvre, ou cree, la bibliotheque rangee dans ce dossier."""
    return Bibliotheque(os.path.join(dossier_parent, DOSSIER))
