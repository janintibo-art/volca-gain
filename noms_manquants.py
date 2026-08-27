#!/usr/bin/env python3
"""Cherche les noms utilises et jamais definis dans un fichier Python.

Ne demande aucune dependance et n'importe pas le fichier : il analyse
l'arbre syntaxique. Utile sur main.py, que Termux ne peut pas importer
faute de Kivy — donc qu'aucun test ne couvre.

    python noms_manquants.py main.py

Sortie vide = rien a signaler. Code de retour 1 s'il manque quelque chose.
"""
import ast
import builtins
import sys

# ast.Name ne voit pas les noms implicites du module.
IMPLICITES = {"__file__", "__name__", "__doc__", "__package__",
              "__spec__", "__loader__", "__builtins__"}


def definis(arbre):
    """Tous les noms qu'un module rend disponibles, portees confondues.

    Volontairement large : on cherche les oublis francs, pas les erreurs
    de portee. Un faux negatif vaut mieux qu'une alerte pour rien.
    """
    out = set(dir(builtins)) | IMPLICITES
    for n in ast.walk(arbre):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef,
                          ast.ClassDef)):
            out.add(n.name)
        elif isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
            out.add(n.id)
        elif isinstance(n, ast.arg):
            out.add(n.arg)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            for a in n.names:
                out.add((a.asname or a.name).split(".")[0])
        elif isinstance(n, ast.ExceptHandler) and n.name:
            out.add(n.name)
        elif isinstance(n, ast.Global):
            out.update(n.names)
    return out


def manquants(chemin):
    with open(chemin, "r", encoding="utf-8") as f:
        arbre = ast.parse(f.read(), filename=chemin)
    connus = definis(arbre)
    vus = {}
    for n in ast.walk(arbre):
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
            if n.id not in connus:
                vus.setdefault(n.id, n.lineno)
    return sorted(vus.items(), key=lambda x: x[1])


def main(args):
    if not args:
        print(__doc__)
        return 2
    total = 0
    for chemin in args:
        for nom, ligne in manquants(chemin):
            print("%s:%d: %s n'est defini nulle part" % (chemin, ligne, nom))
            total += 1
    if total:
        print("--- %d nom(s) manquant(s)" % total)
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
