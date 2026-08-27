# MOC'TA BASS

Traitement du son, séquences **et** transfert direct pour la **Korg volca
sample** et la **volca sample2**. Sur Android et Windows. Le librarian Korg
devient inutile.

---

## Le problème

Le librarian officiel a un paramètre LEVEL qui plafonne à 100 % : il ne peut que
**baisser** le volume, jamais le monter. Un sample enregistré trop faible reste
trop faible, et rien dans l'application officielle ne permet de retravailler le
son.

MOC'TA BASS fait le traitement **avant** le transfert, puis envoie directement
par SYNC IN.

Sur un kick enregistré à -32,8 dB RMS : **+27 dB** récupérés, crête maîtrisée à
-0,2 dB, aucun écrêtage.

---

## Sept onglets

| Onglet | Rôle |
|---|---|
| **TRAIT.** | traitement par lot d'un dossier, écoute avant / après |
| **SLOTS** | les 100 ou 200 emplacements, envoi, kits, import Korg |
| **EDIT.** | forme d'onde, découpe, A/B, réglages fins |
| **PATT.** | les 10 patterns, 16 pas, motions |
| **MORC.** | enchaîner des patterns, écouter, exporter |
| **BIBLI.** | réserve illimitée de patterns et de sons |
| **TUTO** | 22 sections de documentation intégrée |

---

## Ce que ça fait

### Traitement du son

Une chaîne complète, réglable étage par étage :

- offset DC, passe-haut, coupe des silences
- **transient shaper** — accentue l'attaque indépendamment du volume
- **compresseur** — réduit l'écart crête/moyenne
- **saturation** — ajoute des harmoniques au lieu d'écrêter
- mise à niveau **RMS ou LUFS** (pondération K)
- **porte de bruit** — indispensable après +25 dB de gain
- fondus courts, **limiteur avec lookahead**
- conversion automatique en mono 16 bits 44,1 kHz

Six presets d'usine (`doux`, `punch`, `max`, `loop`, `sub`, `voix`), onze
réglages fins par curseur, et des presets personnalisés enregistrables.

### Éditeur

Forme d'onde avec poignées de découpe, calage sur les passages par zéro,
comparaison **A/B** entre l'original et le traité, tête de lecture, annulation
sur douze niveaux. Choix du canal source sur un stéréo (gauche, droite,
moyenne, ou **side** qui isole ce qui n'est pas au centre).

### Gestion des slots

100 emplacements sur volca sample, **200 sur sample2**. Preset et gain par
slot, renommage, déplacement, échange, duplication.

- **Remplissage automatique** — un dossier entier trouve sa place dans les
  slots libres, à partir du numéro voulu, avec le preset choisi.
- **Envoi groupé** — plusieurs slots dans un seul flux, avec compte à rebours.
- **Optimiser** — détecte les samples sans aigu et réduit leur taux
  d'échantillonnage. Jusqu'à 64 % de mémoire libérée sur un son sombre.
- **Égaliser le kit** — aligne le niveau perçu de tous les slots pour que les
  pads répondent pareil. Écart ramené sous 0,3 dB.
- **Jauge mémoire** — 65 s sur sample, 130 s sur sample2.

### Patterns

Les 10 patterns de la machine, 10 parties × 16 pas. Numéro de sample, niveau,
et les fonctions Loop / Reverb / Reverse / Mute par partie. Format Korg
respecté à l'octet près : les patterns d'usine du SDK s'ouvrent tels quels.

- **Motions** — les potards automatisés pas par pas, sur quatorze pistes.
- **Écoute fidèle** — le rendu reproduit l'effet réel des potards de chaque
  partie, motions comprises, au lieu de jouer les sons bruts.
- **Swing** à l'écoute, réglable. Il n'est pas transféré : la machine a son
  propre réglage.

Les patterns de la **sample2** (7936 octets) sont lus et affichés. Ils ne sont
pas envoyables : le SDK Korg embarqué ne gère que le format de première
génération.

### Morceau

Enchaîner des patterns en sections répétées, écouter le tout, et exporter :

- **export en un seul WAV** du morceau complet ;
- **export en pistes** — un fichier par partie, équilibre relatif conservé, de
  quoi finir le mixage ailleurs ;
- **plan d'envoi** — ce qu'il faut transférer, patterns et samples manquants
  compris.

### Bibliothèque

Une réserve sans limite de patterns et de sons, hors des 100 slots. On y range,
on y cherche, on renomme, et on repioche dans un projet.

### Import des sauvegardes Korg

Les fichiers `.vlcspllib` et `.vlcsplpatt` du librarian officiel s'ouvrent
directement : sons et patterns récupérés, avec leurs noms.

### Envoi direct

Génération du flux Syro et lecture par la sortie casque. Jack vers SYNC IN,
et c'est parti. Envoi partiel possible, avec compte à rebours pendant le
transfert.

### Kit portable

Un zip contenant les sons traités **et** leur placement dans les slots. De quoi
changer de téléphone ou partager un kit complet.

### Trouver ses fichiers

Le sélecteur a une barre de raccourcis : Téléchargements, Musique, **Carte SD**,
Documents, Stockage interne. Un raccourci grisé signale un dossier qu'Android
refuse ; le bouton **Diagnostic** dit alors ce qui bloque. En dernier recours,
le chemin complet se tape à la main.

---

## Installation

**Android** — télécharge le `.apk` depuis la page
[Releases](../../releases/latest) et installe-le (autorise les sources
inconnues à la première installation).

**Windows** — télécharge le `.zip`, décompresse, lance `MOC'TA BASS.exe`.

---

## Ligne de commande

Tout le cœur est aussi disponible en console, **sans aucune dépendance** :

```bash
python cli.py info samples/                      # repérer les sons faibles
python cli.py presets
python cli.py traiter samples/ -o out/ -p punch
python cli.py projet creer mon_kit --dossier out/
python cli.py projet egaliser mon_kit.volca.json
python cli.py projet optimiser mon_kit.volca.json
python cli.py memoire mon_kit.volca.json
python cli.py envoyer mon_kit.volca.json --jouer
python cli.py rapide kick.wav 0 --jouer
python cli.py effacer 0-9
python cli.py pattern infos preset_pattern_01.dat
python cli.py librairie sauvegarde.vlcspllib
python cli.py kit exporter mon_kit.volca.json
python cli.py syro                               # envoi direct disponible ?
python cli.py tuto
```

---

## Brancher la volca

1. Câble jack 3,5 mm : sortie casque vers **SYNC IN**
2. Volume **à fond**
3. Bluetooth **coupé**, aucun égaliseur, pas de Dolby ni d'Adapt Sound
4. Lancer et ne toucher à rien jusqu'à la fin

L'envoi **écrase** le slot de destination sans confirmation.

---

## Construire soi-même

L'envoi direct s'appuie sur le [Syro SDK de
Korg](https://github.com/korginc/volcasample), ajouté en sous-module :

```bash
git clone --recursive https://github.com/janintibo-art/volca-gain
cd volca-gain
cmake -S native -B native/build && cmake --build native/build
python cli.py syro          # doit répondre DISPONIBLE
python -m unittest discover -s . -p "test_*.py"
```

L'APK et le `.exe` sont construits par GitHub Actions à chaque push, et publiés
en release à chaque tag de version.

Sans la bibliothèque native, tout le reste fonctionne : seul l'envoi direct est
désactivé.

---

## Architecture

```
volca/              logique métier, Python standard sans aucune dépendance
├── audio.py        moteur DSP (filtres, compresseur, limiteur, LUFS)
├── project.py      les 100 ou 200 slots, appariement de fichiers
├── pattern.py      format Korg des patterns, motions, rendu audio
├── morceau.py      enchaînement de patterns, export, plan d'envoi
├── bibliotheque.py réserve de patterns et de sons
├── kit.py          kits portables (zip autonome)
├── librarian.py    import des sauvegardes .vlcspllib et .vlcsplpatt
├── syro.py         envoi direct via ctypes
├── reglages.py     presets personnalisés
├── etat.py         dernier projet ouvert
├── batch.py        traitement par lot
└── tips.py         contenu du tutoriel

native/             couche C au-dessus du SDK Korg (+ un faux SDK pour les tests)
main.py             interface Kivy
cli.py              interface console
tests/              274 tests
```

Le cœur ne dépend de rien : il tourne dans Termux tel quel. Kivy sert
uniquement à l'affichage.

---

## Limites connues

- Les patterns **sample2** sont lisibles mais pas envoyables.
- L'écoute est **mono** : le panoramique n'est pas simulé.

---

## Licence

MIT pour ce dépôt. Le Syro SDK reste soumis à la licence Korg et n'est pas
redistribué ici.
