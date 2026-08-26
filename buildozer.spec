[app]
title = MOC’TA BASS
package.name = moctabass
package.domain = org.moctek

source.dir = .
source.include_exts = py,png,jpg,kv,atlas,txt,md
source.include_patterns = volca/*.py,assets/*.png
source.exclude_dirs = tests,packaging,.github,bin,.buildozer,native
version = 1.3.4

# Uniquement la stdlib + Kivy : pas de numpy, pas de recette a compiler.
requirements = python3,kivy==2.3.0

orientation = portrait
fullscreen = 0

android.permissions = READ_EXTERNAL_STORAGE,WRITE_EXTERNAL_STORAGE,READ_MEDIA_AUDIO,MANAGE_EXTERNAL_STORAGE
android.api = 33
android.ndk = 25b
android.minapi = 24
android.ndk_api = 24
android.archs = arm64-v8a
android.allow_backup = 1
android.accept_sdk_license = True
android.extra_manifest_application_arguments = ./src/android/extra_manifest_application_arguments.xml
p4a.branch = v2024.01.21

# Bibliotheque Syro compilee au prealable (voir native/README.md).
# Si les fichiers sont absents, l'APK se construit quand meme : l'application
# fonctionne, seul l'envoi direct est desactive.
android.add_libs_arm64_v8a = native/prebuilt/android/arm64-v8a/*.so
android.add_libs_armeabi_v7a = native/prebuilt/android/armeabi-v7a/*.so

# icone / splash : decommente quand tu auras les images
icon.filename = %(source.dir)s/assets/icon.png
presplash.filename = %(source.dir)s/assets/presplash.png
android.presplash_color = #0e0e12

[buildozer]
log_level = 2
warn_on_root = 0

