# Faux SDK (tests uniquement)

Reproduit l'API publique du Syro SDK de Korg pour pouvoir tester
`syro_wrap.c` et le wrapper ctypes **sans** le code de Korg :
disposition des structures, convention d'appel, gestion memoire,
ecriture du WAV de sortie.

Il ne genere PAS un vrai flux Syro : le son produit ne programmera
aucune volca. Il sert seulement a `tests/test_syro.py`.
