[app]
title = Volca Gain
package.name = volcagain
package.domain = org.volcagain

source.dir = .
source.include_exts = py,png,jpg,kv,atlas,txt,md
source.include_patterns = volca/*.py
source.exclude_dirs = tests,packaging,.github,bin,.buildozer,native
version = 0.2.0

# Uniquement la stdlib + Kivy : pas de numpy, pas de recette a compiler.
requirements = python3,kivy==2.3.0

orientation = portrait
fullscreen = 0

android.permissions = READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE
android.api = 33
android.minapi = 24
android.ndk_api = 24
android.archs = arm64-v8a,armeabi-v7a
android.allow_backup = 1
android.accept_sdk_license = True

# Bibliotheque Syro compilee au prealable (voir native/README.md).
# Si les fichiers sont absents, l'APK se construit quand meme : l'application
# fonctionne, seul l'envoi direct est desactive.
android.add_libs_arm64_v8a = native/prebuilt/android/arm64-v8a/*.so
android.add_libs_armeabi_v7a = native/prebuilt/android/armeabi-v7a/*.so

# icone / splash : decommente quand tu auras les images
# icon.filename = %(source.dir)s/assets/icon.png
# presplash.filename = %(source.dir)s/assets/presplash.png

[buildozer]
log_level = 2
warn_on_root = 0
