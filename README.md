# Volca Gain

Une seule application pour la **Korg volca sample** : traiter le son *et*
l'envoyer. Plus besoin du librarian Korg.

## Le probleme

Le librarian officiel a un parametre LEVEL qui plafonne a 100 % : il ne peut
que **baisser** le volume, jamais le monter. Un sample enregistre trop faible
reste trop faible, et rien dans l'application ne permet de retravailler le son.

## Ce que fait Volca Gain

**Traitement du son** (ce qui manque au librarian)

- suppression de l'offset DC
- coupe du silence en debut / fin
- compression : reduit l'ecart crete / moyenne
- mise a niveau RMS : c'est ca qui rend un son "fort" a l'oreille
- fondus courts pour eviter les clics
- limiteur avec lookahead : plafonne sans distordre
- conversion automatique en mono 16 bits 44,1 kHz

Bonus : la volca compresse les samples en interne, donc un signal bien chaud
au depart = moins de bruit de quantification.

**Gestion des slots** (comme le librarian)

- les 100 slots, avec preset et gain par slot
- jauge de memoire (65 s sur volca sample, 130 s sur sample2)
- projets sauvegardables en JSON : on retrouve son kit, on le re-envoie,
  on le versionne dans git
- effacement de slots

**Envoi direct** (ce qui remplace le librarian)

- generation du flux Syro et lecture par la sortie casque
- cable jack vers SYNC IN, et c'est parti

## Etat du projet

| Element | Etat |
|---|---|
| Moteur audio (`volca/audio.py`) | fonctionnel, teste |
| Traitement par lot | fonctionnel |
| Gestion des 100 slots (`volca/project.py`) | fonctionnel, teste |
| Interface console (`cli.py`) | fonctionnel, zero dependance |
| Interface graphique (`main.py`) | fonctionnel (Kivy) |
| Couche Syro (`native/` + `volca/syro.py`) | fonctionnelle, testee via faux SDK |
| .exe Windows / APK Android | via GitHub Actions |

L'envoi direct a besoin du SDK Korg en sous-module (voir `native/README.md`).
Sans lui, tout le reste fonctionne : on exporte les WAV traites et on passe
par le librarian.

## Presets

| Nom | Usage |
|---|---|
| `doux` | normalisation crete seule, garde toute la dynamique |
| `punch` | compression douce + RMS -13 dB (bon defaut) |
| `max` | le plus fort possible : kicks, claps, one-shots |
| `loop` | boucles : fondus minuscules pour ne pas casser le raccord |

## Console

```bash
python cli.py info samples/                    # reperer les sons trop faibles
python cli.py traiter samples/ -o out/ -p punch
python cli.py projet creer mon_kit --dossier out/
python cli.py projet voir mon_kit.volca.json
python cli.py envoyer mon_kit.volca.json --jouer
python cli.py rapide 3 kick.wav --jouer        # un seul son dans le slot 3
python cli.py effacer 3,7-9 --jouer
python cli.py syro                             # envoi direct dispo ?
python cli.py presets
```

Un RMS sous -20 dB = sample trop faible, c'est celui-la qu'il faut traiter.

## Graphique

```bash
pip install kivy
python main.py
```

Deux onglets : TRAITEMENT (analyse et traitement d'un dossier) et SLOTS
(grille des 100 slots, jauge memoire, envoi).

## Envoi : branchement

1. Cable jack 3,5 mm : sortie casque -> **SYNC IN** de la volca
2. Volume a fond
3. Aucun egaliseur, aucune reduction de volume, pas de Bluetooth
4. Lancer la lecture et ne toucher a rien jusqu'a la fin

## Builds automatiques

A chaque `git push` sur `main`, GitHub Actions lance les tests puis construit
le .exe et l'APK. Onglet **Actions** > dernier run > **Artifacts** en bas.

## Arborescence

```
volca-gain/
├── main.py                     interface graphique Kivy
├── cli.py                      interface console (zero dependance)
├── volca/
│   ├── audio.py                moteur DSP
│   ├── batch.py                traitement par lot
│   ├── project.py              les 100 slots, fichiers projet
│   └── syro.py                 envoi direct (ctypes)
├── native/
│   ├── syro_wrap.c             couche C au-dessus du SDK Korg
│   ├── CMakeLists.txt
│   ├── fake_sdk/               faux SDK pour les tests
│   └── README.md               comment ajouter et compiler le SDK
├── tests/
├── packaging/volca_gain.spec   PyInstaller
├── buildozer.spec              APK
└── .github/workflows/build.yml CI
```

## Suite

1. Editeur par sample : trim manuel, choix du point de depart
2. Transfert des patterns (le SDK le permet, `DataType_Pattern`)
3. Enregistrement direct depuis le micro vers un slot

## Licence

MIT pour ce depot. Le SDK Syro reste soumis a la licence Korg et n'est pas
redistribue ici.
