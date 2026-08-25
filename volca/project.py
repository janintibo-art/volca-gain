"""
Gestion des 100 slots de la volca sample : l'equivalent de la liste de
samples du librarian Korg, mais sauvegardable dans un fichier projet.

Un projet = un fichier JSON qui associe des WAV a des numeros de slot, avec
le preset et le gain a appliquer a chacun. On peut donc retrouver exactement
sa configuration, la re-envoyer, la partager, la versionner dans git.
"""

import json
import os

from . import audio

NB_SLOTS = 100

# Memoire interne de l'instrument, en secondes de son.
# volca sample (2014)  : environ 65 s
# volca sample2 (2020) : environ 130 s
MEMOIRE = {"sample": 65.0, "sample2": 130.0}


class Slot:
    def __init__(self, index, chemin=None, preset="punch", gain_db=0.0,
                 nom=None, duree_ms=0.0, taux=None):
        self.index = index
        self.chemin = chemin
        self.preset = preset
        self.gain_db = gain_db
        self.nom = nom or (os.path.splitext(os.path.basename(chemin))[0]
                           if chemin else "")
        self.duree_ms = duree_ms
        # taux d'echantillonnage force (None = taux d'origine).
        # Baisser le taux divise d'autant le cout en memoire volca.
        self.taux = taux

    @property
    def vide(self):
        return not self.chemin

    def cout_s(self):
        """Cout reel en secondes de memoire volca."""
        base = self.duree_ms / 1000.0
        if self.taux:
            return base * (self.taux / float(audio.TARGET_RATE))
        return base

    def analyser(self):
        """Lit le WAV et met a jour nom / duree. Renvoie les infos."""
        if self.vide:
            return None
        s = audio.read_wav(self.chemin)
        self.nom = s.name
        self.duree_ms = s.duration_ms
        return s.info()

    def to_dict(self):
        return {"index": self.index, "chemin": self.chemin,
                "preset": self.preset, "gain_db": self.gain_db,
                "nom": self.nom, "duree_ms": self.duree_ms,
                "taux": self.taux}

    @staticmethod
    def from_dict(d):
        return Slot(d["index"], d.get("chemin"), d.get("preset", "punch"),
                    d.get("gain_db", 0.0), d.get("nom"),
                    d.get("duree_ms", 0.0), d.get("taux"))


class Projet:
    def __init__(self, nom="projet", modele="sample"):
        self.nom = nom
        self.modele = modele if modele in MEMOIRE else "sample"
        self.slots = [Slot(i) for i in range(NB_SLOTS)]
        self.chemin_fichier = None

    # ------------------------------------------------------------ edition
    def assigner(self, index, chemin, preset="punch", gain_db=0.0):
        if not 0 <= index < NB_SLOTS:
            raise ValueError("slot hors limites : %d" % index)
        s = Slot(index, chemin, preset, gain_db)
        s.analyser()
        self.slots[index] = s
        return s

    def vider(self, index):
        self.slots[index] = Slot(index)

    def remplir_depuis_dossier(self, dossier, depart=0, preset="punch"):
        """Range tous les WAV d'un dossier a partir du slot `depart`."""
        from . import batch
        fichiers = batch.list_wavs(dossier)
        places = []
        i = depart
        for f in fichiers:
            while i < NB_SLOTS and not self.slots[i].vide:
                i += 1
            if i >= NB_SLOTS:
                break
            places.append(self.assigner(i, f, preset))
            i += 1
        return places

    # ------------------------------------------------------------ etat
    def occupes(self):
        return [s for s in self.slots if not s.vide]

    def memoire_utilisee_s(self):
        return sum(s.cout_s() for s in self.occupes())

    def optimiser(self, progression=None):
        """Baisse le taux des samples qui n'ont pas besoin de leur aigu.

        Le Syro accepte n'importe quel Fs : une nappe sombre a 22 kHz sonne
        pareil et coute moitie moins cher en memoire.
        Renvoie (rapport, secondes_gagnees).
        """
        rapport = []
        gagne = 0.0
        occ = self.occupes()
        for n, slot in enumerate(occ, 1):
            try:
                s = audio.read_wav(slot.chemin)
            except Exception as e:  # noqa: BLE001
                rapport.append({"slot": slot.index, "nom": slot.nom,
                                "erreur": str(e)})
                continue
            avant = slot.cout_s()
            taux = audio.taux_conseille(s)
            if taux < audio.TARGET_RATE:
                slot.taux = taux
                eco = avant - slot.cout_s()
                gagne += eco
                rapport.append({"slot": slot.index, "nom": slot.nom,
                                "taux": taux, "eco_s": round(eco, 3)})
            if progression:
                progression(n, len(occ), slot)
        return rapport, round(gagne, 2)

    def reinitialiser_taux(self):
        for s in self.occupes():
            s.taux = None

    def memoire_totale_s(self):
        return MEMOIRE[self.modele]

    def memoire_pct(self):
        return 100.0 * self.memoire_utilisee_s() / self.memoire_totale_s()

    def depassement(self):
        return self.memoire_utilisee_s() > self.memoire_totale_s()

    def resume(self):
        lignes = ["Projet '%s' (%s) - %d/%d slots - memoire %.1f/%.0f s (%.0f %%)"
                  % (self.nom, self.modele, len(self.occupes()), NB_SLOTS,
                     self.memoire_utilisee_s(), self.memoire_totale_s(),
                     self.memoire_pct())]
        if self.depassement():
            lignes.append("  ATTENTION : memoire depassee, raccourcis des samples")
        for s in self.occupes():
            taux = ("  %d Hz" % s.taux) if s.taux else ""
            lignes.append("  %02d  %-22s %6.0f ms  %-6s %+.1f dB%s" % (
                s.index, s.nom[:22], s.duree_ms, s.preset, s.gain_db, taux))
        return "\n".join(lignes)

    # ------------------------------------------------------------ envoi
    def pour_envoi(self, indices=None):
        """Renvoie [(index, chemin)] pret pour volca.syro.build_stream()."""
        cibles = self.occupes()
        if indices is not None:
            wanted = set(indices)
            cibles = [s for s in cibles if s.index in wanted]
        return [(s.index, s.chemin) for s in cibles]

    # ------------------------------------------------------------ fichier
    def sauver(self, chemin=None):
        chemin = chemin or self.chemin_fichier or (self.nom + ".volca.json")
        data = {"format": 1, "nom": self.nom, "modele": self.modele,
                "slots": [s.to_dict() for s in self.slots if not s.vide]}
        with open(chemin, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        self.chemin_fichier = chemin
        return chemin

    @staticmethod
    def charger(chemin):
        with open(chemin, "r", encoding="utf-8") as f:
            data = json.load(f)
        p = Projet(data.get("nom", "projet"), data.get("modele", "sample"))
        for d in data.get("slots", []):
            p.slots[d["index"]] = Slot.from_dict(d)
        p.chemin_fichier = chemin
        return p
