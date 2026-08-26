"""
Morceau : un enchainement de patterns.

La volca n'a pas de mode morceau : elle joue un pattern a la fois, et
c'est toi qui changes en jouant. Ce module sert donc a COMPOSER et a
ECOUTER un arrangement sur le telephone, pas a le transferer.

Ce qu'on peut en faire :
  - enchainer des patterns avec un nombre de repetitions chacun
  - ecouter le resultat avec les sons places dans les slots
  - exporter le tout en WAV, pour l'utiliser ailleurs

Un morceau est autonome : les patterns y sont enregistres en entier, pas
sous forme de chemins. Le fichier .morceau.json survit donc au deplacement
des fichiers et se partage tel quel.
"""

import base64
import json
import os

from . import audio, pattern


class Section:
    """Un pattern, joue un certain nombre de fois."""

    def __init__(self, motif, repetitions=1, nom=None):
        self.motif = motif
        self.repetitions = max(1, int(repetitions))
        self.nom = nom or motif.nom

    @property
    def pas(self):
        return self.repetitions * pattern.NB_PAS

    def duree_s(self, bpm):
        return self.pas * pattern.duree_pas(bpm)

    def to_dict(self):
        return {"nom": self.nom,
                "repetitions": self.repetitions,
                "motif": base64.b64encode(self.motif.to_bytes()).decode()}

    @staticmethod
    def from_dict(d):
        brut = base64.b64decode(d["motif"])
        m = pattern.Motif.from_bytes(brut, d.get("nom", "pattern"))
        return Section(m, d.get("repetitions", 1), d.get("nom"))


class Morceau:
    def __init__(self, nom="morceau", bpm=120.0, swing=0.5):
        self.nom = nom
        self.bpm = float(bpm)
        # 0,50 = pas reguliers ; au-dela, un pas sur deux est retarde
        self.swing = float(swing)
        self.sections = []
        self.chemin_fichier = None

    # ------------------------------------------------------------ edition
    def ajouter(self, motif, repetitions=1, nom=None, position=None):
        s = Section(motif, repetitions, nom)
        if position is None:
            self.sections.append(s)
        else:
            self.sections.insert(max(0, min(position, len(self.sections))), s)
        return s

    def supprimer(self, index):
        self._verifier(index)
        return self.sections.pop(index)

    def deplacer(self, index, delta):
        """Monte ou descend une section dans l'ordre."""
        self._verifier(index)
        cible = index + delta
        if not 0 <= cible < len(self.sections):
            return False
        self.sections[index], self.sections[cible] = \
            self.sections[cible], self.sections[index]
        return True

    def dupliquer(self, index):
        self._verifier(index)
        s = self.sections[index]
        copie = Section(pattern.Motif.from_bytes(s.motif.to_bytes()),
                        s.repetitions, s.nom)
        self.sections.insert(index + 1, copie)
        return copie

    def repeter(self, index, repetitions):
        self._verifier(index)
        self.sections[index].repetitions = max(1, int(repetitions))
        return self.sections[index]

    def _verifier(self, index):
        if not 0 <= index < len(self.sections):
            raise ValueError("section hors limites : %d" % index)

    # ------------------------------------------------------------ etat
    @property
    def pas(self):
        return sum(s.pas for s in self.sections)

    def duree_s(self):
        return self.pas * pattern.duree_pas(self.bpm)

    def samples_utilises(self):
        out = set()
        for s in self.sections:
            for p in s.motif.parties_utilisees():
                if not p.actif("mute"):
                    out.add(p.sample_num)
        return sorted(out)

    def resume(self):
        sw = "" if abs(self.swing - 0.5) < 0.01 else \
            "  swing %.0f %%" % (self.swing * 100)
        lignes = ["Morceau '%s' - %d section(s), %d mesure(s), %.1f s a %.0f bpm%s"
                  % (self.nom, len(self.sections), self.pas // pattern.NB_PAS,
                     self.duree_s(), self.bpm, sw)]
        for i, s in enumerate(self.sections):
            lignes.append("  %2d  %-20s x%-3d  %5.1f s  (%d partie(s))" % (
                i + 1, s.nom[:20], s.repetitions, s.duree_s(self.bpm),
                len(s.motif.parties_utilisees())))
        if not self.sections:
            lignes.append("  (vide)")
        return "\n".join(lignes)

    # ------------------------------------------------------------ audio
    def rendu(self, sons, progression=None, parties=None, normaliser=True):
        """Fabrique l'audio du morceau.

        parties : ensemble de numeros de partie (1 a 10) a inclure.
                  None = toutes.
        """
        rate = audio.TARGET_RATE
        par_pas = pattern.duree_pas(self.bpm)
        total = int(rate * par_pas * self.pas)
        if total <= 0:
            return audio.Sample([], rate, self.nom)

        melange = [0.0] * (total + pattern.queue_max(sons) * 2)
        offset = 0
        n = 0
        for s in self.sections:
            for _ in range(s.repetitions):
                pattern.poser(melange, s.motif, sons, rate, par_pas, offset,
                              self.swing, True, parties)
                offset += pattern.NB_PAS
                n += 1
                if progression:
                    progression(n, self.pas // pattern.NB_PAS, s.nom)

        out = audio.Sample(melange, rate, self.nom)
        if normaliser:
            crete = out.peak()
            if crete > 0:
                audio.apply_gain(out, min(0.0, -1.0 - audio.lin_to_db(crete)))
        return out

    def parties_actives(self):
        """Numeros de partie qui jouent vraiment quelque part."""
        out = set()
        for s in self.sections:
            for p in s.motif.parties_utilisees():
                if not p.actif("mute"):
                    out.add(p.numero + 1)
        return sorted(out)

    def nom_partie(self, numero, projet=None):
        """Un libelle parlant : le nom du sample si on le connait."""
        for s in self.sections:
            p = s.motif.partie(numero)
            if p.pas and not p.actif("mute"):
                if projet is not None and p.sample_num < projet.nb_slots:
                    slot = projet.slots[p.sample_num]
                    if not slot.vide and slot.nom:
                        return slot.nom
                return "sample %d" % p.sample_num
        return "partie %d" % numero

    # ------------------------------------------------------------ fichier
    def sauver(self, chemin=None):
        chemin = chemin or self.chemin_fichier or (self.nom + ".morceau.json")
        data = {"format": 1, "nom": self.nom, "bpm": self.bpm,
                "swing": self.swing,
                "sections": [s.to_dict() for s in self.sections]}
        with open(chemin, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        self.chemin_fichier = chemin
        return chemin

    @staticmethod
    def charger(chemin):
        with open(chemin, "r", encoding="utf-8") as f:
            data = json.load(f)
        m = Morceau(data.get("nom", "morceau"), data.get("bpm", 120.0),
                    data.get("swing", 0.5))
        for d in data.get("sections", []):
            m.sections.append(Section.from_dict(d))
        m.chemin_fichier = chemin
        return m


def plan_envoi(morceau, projet=None, avec_samples=True, max_patterns=10):
    """Prepare tout ce qu'il faut envoyer pour jouer ce morceau.

    Les patterns identiques ne sont envoyes qu'une fois : deux sections
    qui reprennent le meme motif partagent le meme emplacement machine.

    Renvoie un dictionnaire :
        patterns      [(emplacement, Motif, nom)]
        samples       [(slot, chemin, nom)]
        ordre         la suite des emplacements a jouer, dans l'ordre
        avertissements
    """
    vus = {}
    patterns = []
    ordre = []
    avertissements = []

    for sec in morceau.sections:
        cle = sec.motif.to_bytes()
        if cle not in vus:
            if len(patterns) >= max_patterns:
                avertissements.append(
                    "Plus de %d patterns differents : '%s' et la suite "
                    "ne seront pas envoyes." % (max_patterns, sec.nom))
                break
            vus[cle] = len(patterns)
            patterns.append((len(patterns), sec.motif, sec.nom))
        ordre.extend([vus[cle]] * sec.repetitions)

    samples = []
    if avec_samples and projet is not None:
        for num in morceau.samples_utilises():
            slot = projet.slots[num] if num < projet.nb_slots else None
            if slot is None or slot.vide:
                avertissements.append("Slot %d vide : le son manquera." % num)
                continue
            samples.append((num, slot.chemin, slot.nom))

    return {"patterns": patterns, "samples": samples, "ordre": ordre,
            "avertissements": avertissements}


def slots_manquants(morceau, projet):
    """Numeros de sample utilises par le morceau mais dont le slot est vide."""
    out = []
    for num in morceau.samples_utilises():
        slot = projet.slots[num] if num < projet.nb_slots else None
        if slot is None or slot.vide:
            out.append(num)
    return out


def resume_plan(plan):
    lignes = ["%d pattern(s), %d son(s)" % (len(plan["patterns"]),
                                            len(plan["samples"]))]
    for emplacement, _m, nom in plan["patterns"]:
        lignes.append("  pattern %d  <-  %s" % (emplacement, nom[:24]))
    for slot, _c, nom in plan["samples"]:
        lignes.append("  slot %3d   <-  %s" % (slot, nom[:24]))
    if plan["ordre"]:
        suite = " ".join(str(n) for n in plan["ordre"][:24])
        if len(plan["ordre"]) > 24:
            suite += " ..."
        lignes.append("")
        lignes.append("Ordre de jeu : %s" % suite)
    for a in plan["avertissements"]:
        lignes.append("  ! " + a)
    return "\n".join(lignes)


def infos(chemin):
    m = Morceau.charger(chemin)
    return {"nom": m.nom, "bpm": m.bpm, "swing": m.swing,
            "sections": len(m.sections),
            "duree_s": round(m.duree_s(), 1),
            "samples": m.samples_utilises()}


def exporter_pistes(morceau, sons, dossier, projet=None, progression=None):
    """Ecrit une piste WAV par partie, plus le melange complet.

    Le gain est calcule UNE FOIS sur le melange et applique a toutes les
    pistes : leur equilibre relatif est ainsi conserve. Si on normalisait
    chaque piste separement, un charley discret deviendrait aussi fort
    qu'un kick, et le remixage serait fausse.
    """
    os.makedirs(dossier, exist_ok=True)
    actives = morceau.parties_actives()
    if not actives:
        raise ValueError("aucune partie a exporter")

    total = len(actives) + 1
    if progression:
        progression(1, total, "melange")

    melange = morceau.rendu(sons, normaliser=False)
    crete = melange.peak()
    gain = min(0.0, -1.0 - audio.lin_to_db(crete)) if crete > 0 else 0.0

    ecrits = []
    audio.apply_gain(melange, gain)
    chemin = os.path.join(dossier, "00_melange.wav")
    audio.write_wav(chemin, melange)
    ecrits.append({"partie": 0, "nom": "melange", "chemin": chemin})

    for n, numero in enumerate(actives, 2):
        if progression:
            progression(n, total, "partie %d" % numero)
        piste = morceau.rendu(sons, parties={numero}, normaliser=False)
        audio.apply_gain(piste, gain)
        nom = _nom_sur(morceau.nom_partie(numero, projet))
        chemin = os.path.join(dossier, "%02d_%s.wav" % (numero, nom))
        audio.write_wav(chemin, piste)
        ecrits.append({"partie": numero, "nom": nom, "chemin": chemin,
                       "crete_db": round(piste.peak_db(), 1)})

    return ecrits


def _nom_sur(nom):
    ok = ("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
          "0123456789-_")
    net = "".join(c if c in ok else "_" for c in nom).strip("_")
    return net[:30] or "piste"


def exporter_wav(morceau, sons, chemin, progression=None):
    son = morceau.rendu(sons, progression)
    audio.write_wav(chemin, son)
    return {"chemin": chemin, "duree_s": round(son.duration_ms / 1000.0, 1),
            "octets": os.path.getsize(chemin)}
