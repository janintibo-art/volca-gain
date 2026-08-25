# Couche native : envoi direct vers la volca

C'est ce qui remplace le librarian Korg. Sans elle, l'application traite le
son mais ne peut pas envoyer : il faut alors passer par le librarian.

## Pourquoi du C

La volca ne recoit pas de fichiers, elle recoit du **son** par la prise
SYNC IN. Le format de ce son (le "Syro") est fourni par Korg sous forme de
code C dans le depot `korginc/volcasample`. Ce code n'est pas redistribue ici
(licence Korg) : on l'ajoute en sous-module git.

`syro_wrap.c` est notre couche par-dessus. Le SDK rend une trame audio par
appel ; boucler la-dessus depuis Python ferait des millions d'appels ctypes
(plusieurs minutes sur telephone). Notre wrapper boucle en C et rend le flux
complet en un appel.

## Ajouter le SDK Korg

```bash
git submodule add https://github.com/korginc/volcasample native/volcasample
git submodule update --init --recursive
```

## Compiler

Linux / macOS / Termux :

```bash
cmake -S native -B native/build
cmake --build native/build
```

Windows (Visual Studio ou MinGW) :

```bash
cmake -S native -B native\build
cmake --build native\build --config Release
```

Le resultat (`libsyro.so` / `syro.dll`) est trouve automatiquement par
`volca/syro.py`. Verifier avec :

```bash
python cli.py syro
```

## Android

Les `.so` par architecture sont compiles avec le NDK et deposes dans
`native/prebuilt/android/<abi>/libsyro.so`. Buildozer les embarque via
`android.add_libs_*` dans `buildozer.spec`. La CI GitHub fait ca toute seule.

Compilation manuelle avec le NDK :

```bash
cmake -S native -B build-arm64 \
  -DCMAKE_TOOLCHAIN_FILE=$ANDROID_NDK/build/cmake/android.toolchain.cmake \
  -DANDROID_ABI=arm64-v8a -DANDROID_PLATFORM=android-24
cmake --build build-arm64
```

## Tester sans le SDK Korg

`fake_sdk/` reproduit l'API publique pour valider la disposition des
structures, les appels et la gestion memoire. `tests/test_syro.py` s'en sert.
Le son produit ne programme aucune volca : c'est un test, pas un vrai flux.

## Branchement

1. Cable jack 3,5 mm de la sortie casque vers **SYNC IN** de la volca
2. Volume de l'appareil a fond
3. Aucun egaliseur, aucune normalisation, aucun Bluetooth
4. Lancer la lecture et ne toucher a rien jusqu'a la fin
5. La volca affiche sa progression ; elle redemarre a la fin
