#!/usr/bin/env python3
"""
Volca Gain - interface graphique (Kivy).
Meme code pour le .exe Windows et l'APK Android.

Quatre ecrans :
  TRAITEMENT : analyse et traitement d'un dossier
  SLOTS      : les 100 slots de la volca + envoi direct
  EDITEUR    : forme d'onde, decoupe, ecoute avant/apres
  TUTO       : conseils de reglages et infos utiles

Sans Kivy : utiliser cli.py (aucune dependance).
"""

import os
import sys
import tempfile
import threading

try:
    import kivy  # noqa: F401
except ImportError:  # pragma: no cover
    raise SystemExit(
        "Kivy n'est pas installe.\n"
        "  pip install kivy\n"
        "Sinon utilise la version console : python cli.py --help"
    )

from kivy.app import App
from kivy.clock import Clock, mainthread
from kivy.core.window import Window
from kivy.graphics import Color, Line, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.gridlayout import GridLayout
from kivy.uix.image import Image as KivyImage
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.progressbar import ProgressBar
from kivy.uix.scrollview import ScrollView
from kivy.uix.slider import Slider
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget

from volca import (__version__, audio, batch, etat, kit, pattern,
                   project, reglages, syro, tips)

# ---------------------------------------------------------------- palette
FOND = (0.055, 0.055, 0.07, 1)
PANNEAU = (0.10, 0.10, 0.13, 1)
ORANGE = (0.92, 0.33, 0.09, 1)
ORANGE_S = (0.55, 0.20, 0.05, 1)
GRIS = (0.19, 0.19, 0.23, 1)
VERT = (0.16, 0.62, 0.35, 1)
BLEU = (0.24, 0.52, 0.78, 1)
CYAN = (0.16, 0.80, 0.86, 1)   # le neon du logo
TEXTE = (0.90, 0.90, 0.92, 1)
TEXTE_2 = (0.62, 0.62, 0.68, 1)

IS_ANDROID = "ANDROID_ARGUMENT" in os.environ
TMP = tempfile.mkdtemp(prefix="volcagain_ui_")


VERT_CRASH = (0.45, 1.0, 0.45, 1)


def _dossiers_journal():
    d = ["/sdcard/Download", "/storage/emulated/0/Download"]
    try:
        d.append(dossier_travail())
    except Exception:  # noqa: BLE001
        pass
    d += ["/sdcard", os.getcwd(), tempfile.gettempdir()]
    return d


def journal_crash(texte):
    """Ecrit la trace sur le disque. Renvoie le chemin, ou None.

    Volontairement blinde : si le mouchard plante a son tour, on n'a
    plus rien du tout.
    """
    for dossier in _dossiers_journal():
        try:
            if not dossier or not os.path.isdir(dossier):
                continue
            chemin = os.path.join(dossier, "moctabass_crash.txt")
            with open(chemin, "w", encoding="utf-8") as f:
                f.write(texte)
            return chemin
        except Exception:  # noqa: BLE001
            continue
    return None


def trace_complete(e=None):
    import traceback as tb
    import platform as pf
    lignes = ["MOC'TA BASS v%s - trace de plantage" % __version__, ""]
    try:
        lignes += ["python  : %s" % sys.version.split()[0],
                   "systeme : %s" % pf.platform(),
                   "android : %s" % IS_ANDROID,
                   "dossier : %s" % dossier_travail(), ""]
    except Exception:  # noqa: BLE001
        pass
    lignes.append(tb.format_exc() if e is None else "".join(
        tb.format_exception(type(e), e, e.__traceback__)))
    return "\n".join(lignes)


class EcranErreur(BoxLayout):
    """Affiche la trace au lieu de disparaitre."""

    def __init__(self, texte, titre="PLANTAGE", **kw):
        super().__init__(orientation="vertical", spacing=dp(6),
                         padding=dp(10), **kw)
        self.texte = texte
        self.chemin = journal_crash(texte)

        self.add_widget(Label(
            text="[b]%s[/b]" % titre, markup=True, size_hint_y=None,
            height=dp(30), color=(1, 0.45, 0.3, 1)))
        self.add_widget(Label(
            text=("Trace enregistree :\n%s" % self.chemin) if self.chemin
                 else "Trace non enregistrable, recopie l'ecran",
            size_hint_y=None, height=dp(40), font_size=dp(10),
            color=TEXTE_2, halign="center"))

        sv = ScrollView()
        lbl = Label(text=texte, size_hint_y=None, halign="left",
                    valign="top", font_size=dp(10), color=VERT_CRASH)
        try:
            lbl.font_name = "RobotoMono-Regular"
        except Exception:  # noqa: BLE001
            pass
        lbl.bind(texture_size=lambda i, v: setattr(i, "height", v[1]),
                 width=lambda i, v: setattr(i, "text_size", (v, None)))
        sv.add_widget(lbl)
        self.add_widget(sv)

        r = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(6))
        b_c = Bouton(text="Copier", couleur=CYAN)
        b_c.bind(on_release=self._copier)
        r.add_widget(b_c)
        self.lbl_ok = Label(text="", size_hint_x=0.6, font_size=dp(11),
                            color=TEXTE_2)
        r.add_widget(self.lbl_ok)
        self.add_widget(r)

    def _copier(self, *_):
        try:
            from kivy.core.clipboard import Clipboard
            Clipboard.copy(self.texte)
            self.lbl_ok.text = "copie dans le presse-papier"
        except Exception as e:  # noqa: BLE001
            self.lbl_ok.text = "copie impossible : %s" % e


def chemin_asset(nom):
    """Trouve une image, y compris dans un .exe PyInstaller."""
    bases = [os.path.dirname(os.path.abspath(__file__))]
    if hasattr(sys, "_MEIPASS"):
        bases.insert(0, sys._MEIPASS)
    for b in bases:
        for p in (os.path.join(b, "assets", nom), os.path.join(b, nom)):
            if os.path.isfile(p):
                return p
    return None


def default_dir():
    if IS_ANDROID:
        for p in ("/storage/emulated/0/Download", "/sdcard/Download", "/sdcard"):
            if os.path.isdir(p):
                return p
    return os.path.expanduser("~")


def dossier_travail():
    if IS_ANDROID:
        return os.environ.get("ANDROID_PRIVATE") or default_dir()
    return os.getcwd()


def mmss(secondes):
    if secondes < 0:
        secondes = 0
    return "%d:%06.3f" % (int(secondes // 60), secondes % 60)


# --------------------------------------------------------------------------
# Widgets stylises
# --------------------------------------------------------------------------
class Bouton(Button):
    """Bouton a coins arrondis, sans la texture grise de Kivy."""

    def __init__(self, couleur=GRIS, rayon=8, **kw):
        kw.setdefault("background_normal", "")
        kw.setdefault("background_color", (0, 0, 0, 0))
        kw.setdefault("color", TEXTE)
        super().__init__(**kw)
        self.couleur = couleur
        self.rayon = rayon
        with self.canvas.before:
            self._c = Color(*couleur)
            self._r = RoundedRectangle(radius=[rayon])
        self.bind(pos=self._maj, size=self._maj, state=self._maj)
        self._maj()

    def _maj(self, *_a):
        self._r.pos = self.pos
        self._r.size = self.size
        c = self.couleur
        if self.state == "down":
            c = tuple(min(1.0, v * 1.35) for v in c[:3]) + (c[3],)
        elif self.disabled:
            c = tuple(v * 0.45 for v in c[:3]) + (c[3],)
        self._c.rgba = c

    def set_couleur(self, couleur):
        self.couleur = couleur
        self._maj()


class SlotBouton(Bouton):
    """Bouton de slot affichant une mini forme d'onde."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self._apercu = None
        self.bind(pos=self._dessiner, size=self._dessiner)

    def set_apercu(self, peaks):
        self._apercu = peaks
        self._dessiner()

    def _dessiner(self, *_a):
        self.canvas.after.clear()
        if not self._apercu or self.width < 8:
            return
        n = len(self._apercu)
        w = self.width - dp(4)
        h = self.height * 0.42
        x0 = self.x + dp(2)
        mid = self.y + h / 2.0 + dp(2)
        demi = h / 2.0
        with self.canvas.after:
            Color(1, 1, 1, 0.55)
            for i, (mn, mx) in enumerate(self._apercu):
                x = x0 + (i + 0.5) * w / n
                a = mid + max(mn, -1.0) * demi
                b = mid + min(mx, 1.0) * demi
                if b - a < 1:
                    b = a + 1
                Line(points=[x, a, x, b], width=1)


class Panneau(BoxLayout):
    """Conteneur avec fond arrondi, pour donner du relief."""

    def __init__(self, fond=PANNEAU, rayon=10, **kw):
        super().__init__(**kw)
        with self.canvas.before:
            Color(*fond)
            self._r = RoundedRectangle(radius=[rayon])
        self.bind(pos=self._maj, size=self._maj)

    def _maj(self, *_a):
        self._r.pos = self.pos
        self._r.size = self.size


class Onde(Widget):
    """Forme d'onde avec poignees de decoupe et tete de lecture."""

    def __init__(self, on_change=None, **kw):
        super().__init__(**kw)
        self.sample = None
        self._peaks = []
        self.debut = 0.0          # fraction 0..1
        self.fin = 1.0
        self.tete = None          # fraction ou None
        self.on_change = on_change
        self._drag = None
        self.bind(pos=self.redraw, size=self.redraw)

    # ------------------------------------------------------------ donnees
    def charger(self, sample):
        self.sample = sample
        self.debut, self.fin, self.tete = 0.0, 1.0, None
        self._recalc()
        self.redraw()

    def _recalc(self):
        if self.sample is None:
            self._peaks = []
            return
        n = max(60, int(self.width / dp(1.5)) or 300)
        self._peaks = audio.peaks(self.sample, n)

    def bornes_ms(self):
        if self.sample is None:
            return 0.0, 0.0
        d = self.sample.duration_ms
        return self.debut * d, self.fin * d

    # ------------------------------------------------------------ dessin
    def redraw(self, *_a):
        self.canvas.clear()
        if not self._peaks or self.width < 10:
            if self.width > 10:
                self._recalc()
            if not self._peaks:
                return

        if len(self._peaks) < self.width / dp(3):
            self._recalc()

        x0, y0 = self.x, self.y
        w, h = self.width, self.height
        mid = y0 + h / 2.0
        demi = h / 2.0 - dp(4)
        n = len(self._peaks)

        with self.canvas:
            Color(0.08, 0.08, 0.10, 1)
            RoundedRectangle(pos=(x0, y0), size=(w, h), radius=[8])

            # zone selectionnee
            xa = x0 + self.debut * w
            xb = x0 + self.fin * w
            Color(0.92, 0.33, 0.09, 0.13)
            RoundedRectangle(pos=(xa, y0), size=(max(xb - xa, 1), h),
                             radius=[4])

            # axe zero
            Color(0.30, 0.30, 0.34, 1)
            Line(points=[x0, mid, x0 + w, mid], width=1)

            # onde
            for i, (mn, mx) in enumerate(self._peaks):
                x = x0 + (i + 0.5) * w / n
                dans = self.debut <= (i / float(n)) <= self.fin
                if dans:
                    Color(0.92, 0.45, 0.20, 1)
                else:
                    Color(0.35, 0.35, 0.40, 1)
                ymin = mid + max(mn, -1.0) * demi
                ymax = mid + min(mx, 1.0) * demi
                if ymax - ymin < 1:
                    ymax = ymin + 1
                Line(points=[x, ymin, x, ymax], width=1)

            # poignees
            for xh, col in ((xa, ORANGE), (xb, ORANGE)):
                Color(*col)
                Line(points=[xh, y0, xh, y0 + h], width=dp(2))
                RoundedRectangle(pos=(xh - dp(6), y0 + h - dp(14)),
                                 size=(dp(12), dp(14)), radius=[3])
                RoundedRectangle(pos=(xh - dp(6), y0),
                                 size=(dp(12), dp(14)), radius=[3])

            # tete de lecture
            if self.tete is not None:
                Color(0.35, 0.85, 1.0, 1)
                xt = x0 + self.tete * w
                Line(points=[xt, y0, xt, y0 + h], width=dp(1.5))

    # ------------------------------------------------------------ touches
    def _frac(self, x):
        return max(0.0, min(1.0, (x - self.x) / float(self.width or 1)))

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos) or self.sample is None:
            return False
        f = self._frac(touch.x)
        self._drag = "debut" if abs(f - self.debut) <= abs(f - self.fin) \
            else "fin"
        self._appliquer(f)
        return True

    def on_touch_move(self, touch):
        if self._drag is None:
            return False
        self._appliquer(self._frac(touch.x))
        return True

    def on_touch_up(self, touch):
        if self._drag is None:
            return False
        self._drag = None
        return True

    def _appliquer(self, f):
        mini = 0.005
        if self._drag == "debut":
            self.debut = min(f, self.fin - mini)
        else:
            self.fin = max(f, self.debut + mini)
        self.debut = max(0.0, self.debut)
        self.fin = min(1.0, self.fin)
        self.redraw()
        if self.on_change:
            self.on_change()


# --------------------------------------------------------------------------
class NomPopup(Popup):
    """Petite saisie de texte."""

    def __init__(self, titre, defaut, callback, **kw):
        super().__init__(title=titre, size_hint=(0.9, None), height=dp(190),
                         **kw)
        self.callback = callback
        box = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(10))
        self.champ = TextInput(text=defaut, multiline=False,
                               size_hint_y=None, height=dp(44),
                               font_size=dp(16))
        box.add_widget(self.champ)
        r = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6))
        b_no = Bouton(text="Annuler")
        b_no.bind(on_release=lambda *_: self.dismiss())
        r.add_widget(b_no)
        b_ok = Bouton(text="Valider", couleur=VERT)
        b_ok.bind(on_release=self._ok)
        r.add_widget(b_ok)
        box.add_widget(r)
        self.add_widget(box)

    def _ok(self, *_):
        txt = self.champ.text.strip()
        self.dismiss()
        if txt:
            self.callback(txt)


class ReglagesPopup(Popup):
    """Tous les reglages de la chaine, un curseur par parametre."""

    def __init__(self, base_nom, valeurs, on_apercu, on_valider, **kw):
        super().__init__(title="Reglages fins  (base : %s)" % base_nom,
                         size_hint=(0.96, 0.92), **kw)
        self.base_nom = base_nom
        self.on_apercu = on_apercu
        self.on_valider = on_valider
        self.curseurs = {}

        box = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(8))
        sv = ScrollView()
        grille = BoxLayout(orientation="vertical", spacing=dp(4),
                           size_hint_y=None)
        grille.bind(minimum_height=grille.setter("height"))

        for cle, libelle, mini, maxi, pas, unite in reglages.REGLAGES:
            ligne = BoxLayout(orientation="vertical", size_hint_y=None,
                              height=dp(56))
            lbl = Label(text="", size_hint_y=None, height=dp(22),
                        font_size=dp(12), color=TEXTE, halign="left")
            lbl.bind(width=lambda i, v: setattr(i, "text_size", (v, None)))
            sl = Slider(min=mini, max=maxi, step=pas,
                        value=max(mini, min(maxi, valeurs.get(cle, mini))),
                        size_hint_y=None, height=dp(32))

            def maj(_i, v, l=lbl, t=libelle, u=unite):
                l.text = "%s : %.2f %s" % (t, v, u)

            sl.bind(value=maj)
            maj(None, sl.value)
            ligne.add_widget(lbl)
            ligne.add_widget(sl)
            grille.add_widget(ligne)
            self.curseurs[cle] = sl

        sv.add_widget(grille)
        box.add_widget(sv)

        r0 = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        r0.add_widget(Label(text="Niveau", size_hint_x=0.3, color=TEXTE,
                            font_size=dp(12)))
        self.spin_mode = Spinner(text="rms", values=["rms", "lufs"])
        r0.add_widget(self.spin_mode)
        box.add_widget(r0)

        r1 = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(6))
        b_ec = Bouton(text="Ecouter", couleur=VERT)
        b_ec.bind(on_release=lambda *_: self.on_apercu(self.config()))
        r1.add_widget(b_ec)
        b_sv = Bouton(text="Enregistrer", couleur=CYAN)
        b_sv.bind(on_release=lambda *_: self._enregistrer())
        r1.add_widget(b_sv)
        b_ok = Bouton(text="Appliquer", couleur=ORANGE)
        b_ok.bind(on_release=self._valider)
        r1.add_widget(b_ok)
        box.add_widget(r1)
        self.add_widget(box)

    def valeurs(self):
        return {k: sl.value for k, sl in self.curseurs.items()}

    def config(self):
        base = audio.PRESETS[self.base_nom]
        return reglages.depuis_plat(base, self.valeurs(), self.spin_mode.text)

    def _valider(self, *_):
        cfg = self.config()
        self.dismiss()
        self.on_valider(cfg)

    def _enregistrer(self):
        cfg = self.config()
        NomPopup("Nom du preset", "mon_" + self.base_nom,
                 lambda nom: self._faire_enregistrer(nom, cfg)).open()

    def _faire_enregistrer(self, nom, cfg):
        try:
            cfg["desc"] = "Preset personnalise (base %s)" % self.base_nom
            reglages.sauver(nom, cfg, reglages.chemin_defaut(
                dossier_travail()))
            self.dismiss()
            self.on_valider(cfg, nom)
        except Exception as e:  # noqa: BLE001
            self.title = "Erreur : %s" % e


class KitPopup(Popup):
    """Exporter ou importer un kit portable."""

    def __init__(self, ecran, **kw):
        super().__init__(title="Kit portable", size_hint=(0.92, None),
                         height=dp(300), **kw)
        self.ecran = ecran
        box = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(10))
        box.add_widget(Label(
            text="Un kit est un zip contenant les sons traites\n"
                 "ET leur placement dans les 100 slots.\n"
                 "De quoi changer de telephone ou partager.",
            font_size=dp(12), color=TEXTE_2, size_hint_y=None, height=dp(70),
            halign="center"))

        b_e = Bouton(text="Exporter le kit", couleur=ORANGE,
                     size_hint_y=None, height=dp(50))
        b_e.bind(on_release=lambda *_: self._exporter())
        box.add_widget(b_e)

        b_i = Bouton(text="Importer un kit", couleur=CYAN,
                     size_hint_y=None, height=dp(50))
        b_i.bind(on_release=lambda *_: self._importer())
        box.add_widget(b_i)

        b_f = Bouton(text="Fermer", size_hint_y=None, height=dp(44))
        b_f.bind(on_release=lambda *_: self.dismiss())
        box.add_widget(b_f)
        self.add_widget(box)

    def _exporter(self):
        if not self.ecran.projet.occupes():
            self.ecran.journal("Aucun slot rempli.")
            self.dismiss()
            return
        self.dismiss()
        NomPopup("Nom du kit", self.ecran.projet.nom,
                 self.ecran.exporter_kit).open()

    def _importer(self):
        self.dismiss()
        Chooser(self.ecran.importer_kit, filtres=["*.zip"]).open()


class Chooser(Popup):
    def __init__(self, callback, dossiers=False, filtres=None, start=None, **kw):
        super().__init__(
            title="Choisir un dossier" if dossiers else "Choisir un fichier",
            size_hint=(0.95, 0.9), **kw)
        self.callback = callback
        self.dossiers = dossiers
        box = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(6))
        self.chooser = FileChooserListView(
            path=start or default_dir(), dirselect=dossiers,
            filters=filtres or ["*"])
        box.add_widget(self.chooser)
        row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(6))
        b_no = Bouton(text="Annuler")
        b_no.bind(on_release=lambda *_: self.dismiss())
        b_ok = Bouton(text="Choisir", couleur=ORANGE)
        b_ok.bind(on_release=self._ok)
        row.add_widget(b_no)
        row.add_widget(b_ok)
        box.add_widget(row)
        self.add_widget(box)

    def _ok(self, *_):
        sel = self.chooser.selection
        chemin = sel[0] if sel else self.chooser.path
        if self.dossiers and os.path.isfile(chemin):
            chemin = os.path.dirname(chemin)
        self.dismiss()
        self.callback(chemin)


class ChoixSlot(Popup):
    """Grille compacte pour choisir un numero de slot."""

    def __init__(self, projet, callback, **kw):
        super().__init__(title="Vers quel slot ?", size_hint=(0.95, 0.8), **kw)
        self.callback = callback
        sv = ScrollView()
        g = GridLayout(cols=10, spacing=dp(2), size_hint_y=None,
                       padding=dp(6))
        g.bind(minimum_height=g.setter("height"))
        for i in range(projet.nb_slots):
            libre = projet.slots[i].vide
            fmt = "%03d" if projet.nb_slots > 100 else "%02d"
            b = Bouton(text=fmt % i, font_size=dp(11), size_hint_y=None,
                       height=dp(38), couleur=GRIS if libre else ORANGE_S)
            b.bind(on_release=lambda w, idx=i: self._choisi(idx))
            g.add_widget(b)
        sv.add_widget(g)
        self.add_widget(sv)

    def _choisi(self, i):
        self.dismiss()
        self.callback(i)


class SlotPopup(Popup):
    def __init__(self, ecran, index, **kw):
        self.ecran = ecran
        self.index = index
        slot = ecran.projet.slots[index]
        super().__init__(title="Slot %d" % index, size_hint=(0.9, None),
                         height=dp(392), **kw)

        box = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(10))
        self.lbl = Label(text=slot.nom or "(vide)", size_hint_y=None,
                         height=dp(28), shorten=True, color=TEXTE)
        box.add_widget(self.lbl)
        self.lbl_dur = Label(
            text=("%.0f ms" % slot.duree_ms) if not slot.vide else "",
            size_hint_y=None, height=dp(22), font_size=dp(11), color=TEXTE_2)
        box.add_widget(self.lbl_dur)

        b = Bouton(text="Choisir un WAV", size_hint_y=None, height=dp(46),
                   couleur=ORANGE)
        b.bind(on_release=lambda *_: Chooser(
            self._assigner, filtres=["*.wav", "*.WAV"]).open())
        box.add_widget(b)

        r1 = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        r1.add_widget(Label(text="Preset", size_hint_x=0.35, color=TEXTE))
        self.spin = Spinner(text=slot.preset, values=sorted(audio.PRESETS))
        r1.add_widget(self.spin)
        box.add_widget(r1)

        r2 = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        self.lbl_gain = Label(text="Gain %+.1f dB" % slot.gain_db,
                              size_hint_x=0.45, color=TEXTE)
        r2.add_widget(self.lbl_gain)
        self.sl = Slider(min=-12, max=12, value=slot.gain_db, step=0.5)
        self.sl.bind(value=lambda _i, v: setattr(
            self.lbl_gain, "text", "Gain %+.1f dB" % v))
        r2.add_widget(self.sl)
        box.add_widget(r2)

        r_nom = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(6))
        b_ren = Bouton(text="Renommer", font_size=dp(12), couleur=CYAN)
        b_ren.bind(on_release=lambda *_: self._renommer())
        r_nom.add_widget(b_ren)
        box.add_widget(r_nom)

        r_rang = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(6))
        for txt, action in (("Deplacer", "deplacer"),
                            ("Echanger", "echanger"),
                            ("Copier", "dupliquer")):
            bb = Bouton(text=txt, font_size=dp(12), couleur=CYAN)
            bb.bind(on_release=lambda w, a=action: self._ranger(a))
            r_rang.add_widget(bb)
        box.add_widget(r_rang)

        r3 = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(6))
        b_vider = Bouton(text="Vider")
        b_vider.bind(on_release=self._vider)
        r3.add_widget(b_vider)
        b_ok = Bouton(text="Valider", couleur=VERT)
        b_ok.bind(on_release=self._valider)
        r3.add_widget(b_ok)
        box.add_widget(r3)
        self.add_widget(box)

    def _renommer(self):
        slot = self.ecran.projet.slots[self.index]
        if slot.vide:
            self.ecran.journal("Slot %d vide." % self.index)
            return
        NomPopup("Nom du slot %d" % self.index, slot.nom,
                 self._faire_renommer).open()

    def _faire_renommer(self, nom):
        try:
            s = self.ecran.projet.renommer(self.index, nom)
            self.lbl.text = s.nom
            self.ecran.rafraichir()
            self.ecran.journal("Slot %d renomme : %s" % (self.index, s.nom))
        except Exception as e:  # noqa: BLE001
            self.ecran.journal("Renommage impossible : %s" % e)

    def _ranger(self, action):
        if self.ecran.projet.slots[self.index].vide:
            self.ecran.journal("Slot %02d vide." % self.index)
            return
        self.dismiss()
        ChoixSlot(self.ecran.projet,
                  lambda dst: self._appliquer_rangement(action, dst)).open()

    def _appliquer_rangement(self, action, dst):
        p = self.ecran.projet
        try:
            if dst == self.index:
                return
            if action == "deplacer":
                if p.slots[dst].vide:
                    p.deplacer(self.index, dst)
                    self.ecran.journal("Slot %02d -> %02d" % (self.index, dst))
                else:
                    p.echanger(self.index, dst)
                    self.ecran.journal(
                        "Slot %02d occupe : echange avec %02d" % (dst,
                                                                  self.index))
            elif action == "echanger":
                p.echanger(self.index, dst)
                self.ecran.journal("Slots %02d <-> %02d" % (self.index, dst))
            else:
                p.dupliquer(self.index, dst)
                self.ecran.journal("Slot %02d copie vers %02d" % (self.index,
                                                                  dst))
            self.ecran.rafraichir()
        except Exception as e:  # noqa: BLE001
            self.ecran.journal("Echec : %s" % e)

    def _assigner(self, chemin):
        try:
            s = self.ecran.projet.assigner(
                self.index, chemin, self.spin.text, self.sl.value)
            self.lbl.text = s.nom
            self.lbl_dur.text = "%.0f ms" % s.duree_ms
        except Exception as e:  # noqa: BLE001
            self.lbl.text = "Erreur : %s" % e

    def _valider(self, *_):
        slot = self.ecran.projet.slots[self.index]
        if not slot.vide:
            slot.preset = self.spin.text
            slot.gain_db = self.sl.value
        self.dismiss()
        self.ecran.rafraichir()

    def _vider(self, *_):
        self.ecran.projet.vider(self.index)
        self.dismiss()
        self.ecran.rafraichir()


# --------------------------------------------------------------------------
class EcranTraitement(BoxLayout):
    def __init__(self, journal, **kw):
        super().__init__(orientation="vertical", spacing=dp(8), **kw)
        self.journal = journal
        self.src = None
        self.busy = False

        b = Bouton(text="Choisir le dossier de samples", size_hint_y=None,
                   height=dp(50), couleur=ORANGE)
        b.bind(on_release=lambda *_: Chooser(self._set_src, dossiers=True).open())
        self.add_widget(b)

        self.lbl_src = Label(text="(aucun dossier)", size_hint_y=None,
                             height=dp(26), font_size=dp(12), shorten=True,
                             color=TEXTE_2)
        self.add_widget(self.lbl_src)

        row = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6))
        row.add_widget(Label(text="Preset", size_hint_x=0.3, color=TEXTE))
        self.spin = Spinner(text="punch", values=sorted(audio.PRESETS))
        self.spin.bind(text=lambda _i, v: setattr(
            self.lbl_desc, "text", audio.PRESETS[v]["desc"]))
        row.add_widget(self.spin)
        self.add_widget(row)

        self.lbl_desc = Label(text=audio.PRESETS["punch"]["desc"],
                              size_hint_y=None, height=dp(24), font_size=dp(11),
                              color=TEXTE_2)
        self.add_widget(self.lbl_desc)

        row2 = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6))
        self.lbl_gain = Label(text="Gain +0.0 dB", size_hint_x=0.4, color=TEXTE)
        row2.add_widget(self.lbl_gain)
        self.sl = Slider(min=-12, max=12, value=0, step=0.5)
        self.sl.bind(value=lambda _i, v: setattr(
            self.lbl_gain, "text", "Gain %+.1f dB" % v))
        row2.add_widget(self.sl)
        self.add_widget(row2)

        row3 = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(6))
        self.b_ana = Bouton(text="Analyser", couleur=CYAN)
        self.b_ana.bind(on_release=lambda *_: self.lancer(True))
        row3.add_widget(self.b_ana)
        self.b_go = Bouton(text="TRAITER", couleur=ORANGE)
        self.b_go.bind(on_release=lambda *_: self.lancer(False))
        row3.add_widget(self.b_go)
        self.add_widget(row3)

        self.pb = ProgressBar(max=1, value=0, size_hint_y=None, height=dp(14))
        self.add_widget(self.pb)
        self.add_widget(BoxLayout())

    def _set_src(self, chemin):
        self.src = chemin
        self.lbl_src.text = chemin
        self.journal("Dossier : %s (%d WAV)"
                     % (chemin, len(batch.list_wavs(chemin))))

    @mainthread
    def _pb(self, i, n):
        self.pb.max = max(n, 1)
        self.pb.value = i

    @mainthread
    def _fin(self):
        self.busy = False
        self.b_go.disabled = False
        self.b_ana.disabled = False

    def lancer(self, analyse_seule):
        if self.busy:
            return
        if not self.src:
            self.journal("Choisis d'abord un dossier.")
            return
        self.busy = True
        self.b_go.disabled = True
        self.b_ana.disabled = True
        threading.Thread(target=self._worker, args=(analyse_seule,),
                         daemon=True).start()

    def _worker(self, analyse_seule):
        try:
            fichiers = batch.list_wavs(self.src)
            if not fichiers:
                self.journal("Aucun WAV trouve.")
                return
            if analyse_seule:
                self.journal("--- ANALYSE ---")
                for i, p in enumerate(fichiers):
                    try:
                        s = audio.read_wav(p)
                        info = s.info()
                        lufs = audio.loudness_lufs(s)
                        note = "  <- faible" if info["rms_db"] < -20 else ""
                        taux = audio.taux_conseille(s)
                        if taux < s.rate:
                            note += " (%d Hz suffit)" % taux
                        self.journal("%-16s RMS %6.1f  LUFS %6.1f%s" % (
                            os.path.basename(p)[:16], info["rms_db"],
                            lufs, note))
                    except Exception as e:  # noqa: BLE001
                        self.journal("%s : %s" % (os.path.basename(p), e))
                    self._pb(i + 1, len(fichiers))
                return

            dst = os.path.join(self.src, "volca_out")
            self.journal("--- TRAITEMENT (%s) ---" % self.spin.text)

            def prog(i, n, rap):
                self._pb(i, n)
                self.journal("%-18s %s" % (
                    rap["fichier"][:18],
                    ("%+.1f dB" % rap["gain_db"]) if rap.get("ok")
                    else "ECHEC " + rap["erreur"]))

            raps = batch.process_folder(self.src, dst, self.spin.text,
                                        self.sl.value, prog)
            ok = sum(1 for r in raps if r.get("ok"))
            self.journal("%d fichier(s) ecrit(s) dans %s" % (ok, dst))
        except Exception as e:  # noqa: BLE001
            self.journal("ERREUR : %s" % e)
        finally:
            self._fin()


# --------------------------------------------------------------------------
class EcranEditeur(BoxLayout):
    """Forme d'onde, decoupe, ecoute avant/apres."""

    def __init__(self, journal, get_slots, **kw):
        super().__init__(orientation="vertical", spacing=dp(6), **kw)
        self.journal = journal
        self.get_slots = get_slots
        self.original = None
        self.chemin = None
        self.son = None
        self.duree_lue = 0.0
        self._ev = None
        self.apercu = None
        self.canal = "mix"
        self.override = None      # configuration issue des reglages fins
        self.historique = []      # etats precedents, pour Annuler

        b = Bouton(text="Charger un WAV", size_hint_y=None, height=dp(46),
                   couleur=ORANGE)
        b.bind(on_release=lambda *_: Chooser(
            self._charger, filtres=["*.wav", "*.WAV"]).open())
        self.add_widget(b)

        self.lbl_nom = Label(text="(aucun fichier)", size_hint_y=None,
                             height=dp(24), font_size=dp(12), shorten=True,
                             color=TEXTE_2)
        self.add_widget(self.lbl_nom)

        cadre = Panneau(orientation="vertical", size_hint_y=1,
                        padding=dp(6))
        self.onde = Onde(on_change=self._maj_temps)
        cadre.add_widget(self.onde)
        self.add_widget(cadre)

        self.lbl_temps = Label(
            text="debut 0:00.000   fin 0:00.000   duree 0 ms",
            size_hint_y=None, height=dp(26), font_size=dp(12), color=TEXTE)
        self.add_widget(self.lbl_temps)

        r0 = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(6))
        for txt, fn in (("|< tout", self._tout),
                        ("Caler zero", self._caler),
                        ("Rogner", self._rogner),
                        ("Annuler", self._annuler)):
            bb = Bouton(text=txt, font_size=dp(12))
            bb.bind(on_release=lambda w, f=fn: f())
            r0.add_widget(bb)
        self.add_widget(r0)

        rc = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(6))
        rc.add_widget(Label(text="Canal", size_hint_x=0.25, color=TEXTE,
                            font_size=dp(12)))
        self.spin_canal = Spinner(text="mix", values=list(audio.CANAUX))
        self.spin_canal.bind(text=self._changer_canal)
        rc.add_widget(self.spin_canal)
        self.b_inv = Bouton(text="Inverser", font_size=dp(12), size_hint_x=0.5)
        self.b_inv.bind(on_release=lambda *_: self._inverser())
        rc.add_widget(self.b_inv)
        self.add_widget(rc)

        r1 = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6))
        r1.add_widget(Label(text="Preset", size_hint_x=0.25, color=TEXTE))
        self.spin = Spinner(text="punch", values=sorted(audio.PRESETS))
        self.spin.bind(text=lambda *_: self._oublier_override())
        r1.add_widget(self.spin)
        b_fin = Bouton(text="Fins", font_size=dp(12), size_hint_x=0.3,
                       couleur=CYAN)
        b_fin.bind(on_release=lambda *_: self._reglages_fins())
        r1.add_widget(b_fin)
        self.add_widget(r1)

        r2 = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(6))
        self.lbl_gain = Label(text="Gain +0.0 dB", size_hint_x=0.4,
                              color=TEXTE, font_size=dp(12))
        r2.add_widget(self.lbl_gain)
        self.sl = Slider(min=-12, max=12, value=0, step=0.5)
        self.sl.bind(value=lambda _i, v: setattr(
            self.lbl_gain, "text", "Gain %+.1f dB" % v))
        r2.add_widget(self.sl)
        self.add_widget(r2)

        r3 = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(6))
        self.b_a = Bouton(text="A  original", couleur=CYAN)
        self.b_a.bind(on_release=lambda *_: self.jouer(False))
        r3.add_widget(self.b_a)
        self.b_b = Bouton(text="B  traite", couleur=VERT)
        self.b_b.bind(on_release=lambda *_: self.jouer(True))
        r3.add_widget(self.b_b)
        self.b_stop = Bouton(text="Stop", size_hint_x=0.5)
        self.b_stop.bind(on_release=lambda *_: self.stop())
        r3.add_widget(self.b_stop)
        self.add_widget(r3)

        r4 = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6))
        b_slot = Bouton(text="Vers un slot", couleur=ORANGE)
        b_slot.bind(on_release=lambda *_: self.vers_slot())
        r4.add_widget(b_slot)
        b_exp = Bouton(text="Exporter WAV")
        b_exp.bind(on_release=lambda *_: self.exporter())
        r4.add_widget(b_exp)
        self.add_widget(r4)

    # ------------------------------------------------------------ chargement
    def _charger(self, chemin):
        try:
            self.stop()
            self.original = audio.read_wav(chemin, canal=self.canal)
            self.chemin = chemin
            self.historique = []
            self.onde.charger(self.original)
            i = self.original.info()
            self.lbl_nom.text = "%s  -  %.0f ms  RMS %.1f dB  LUFS %.1f" % (
                os.path.basename(chemin), i["duree_ms"], i["rms_db"],
                audio.loudness_lufs(self.original))
            self._maj_temps()
            self.journal("Editeur : %s charge" % os.path.basename(chemin))
        except Exception as e:  # noqa: BLE001
            self.journal("Lecture impossible : %s" % e)

    def _changer_canal(self, _sp, canal):
        self.canal = canal
        if not self.chemin:
            return
        try:
            self.stop()
            self._memoriser_etat()
            garde = (self.onde.debut, self.onde.fin)
            self.original = audio.read_wav(self.chemin, canal=canal)
            self.onde.charger(self.original)
            self.onde.debut, self.onde.fin = garde
            self.onde.redraw()
            self._maj_temps()
            self.journal("Canal : %s (RMS %.1f dB)"
                         % (canal, self.original.rms_db()))
        except Exception as e:  # noqa: BLE001
            self.journal("Canal impossible : %s" % e)

    def _inverser(self):
        if self.original is None:
            return
        self._memoriser_etat()
        audio.inverser(self.original)
        self.onde.charger(self.original)
        self._maj_temps()
        self.journal("Polarite inversee.")

    def _oublier_override(self):
        if self.override is not None:
            self.override = None
            self.journal("Reglages fins abandonnes, retour au preset.")

    def _reglages_fins(self):
        base = self.spin.text
        depart = self.override if self.override is not None \
            else audio.PRESETS[base]
        ReglagesPopup(base, reglages.a_plat(depart),
                      lambda cfg: self.jouer(True, cfg),
                      self._appliquer_reglages).open()

    def _appliquer_reglages(self, cfg, nom=None):
        if nom:
            self.override = None
            self.spin.values = sorted(audio.PRESETS)
            self.spin.text = nom
            self.journal("Preset '%s' enregistre et selectionne." % nom)
        else:
            self.override = cfg
            self.journal("Reglages fins appliques (non enregistres).")

    def _maj_temps(self):
        a, b = self.onde.bornes_ms()
        self.lbl_temps.text = "debut %s   fin %s   duree %.0f ms" % (
            mmss(a / 1000.0), mmss(b / 1000.0), b - a)

    def _tout(self):
        self.onde.debut, self.onde.fin = 0.0, 1.0
        self.onde.redraw()
        self._maj_temps()

    def _caler(self):
        """Cale les deux bornes sur les passages par zero les plus proches."""
        if self.original is None:
            return
        n = len(self.original.data)
        i0 = audio.snap_zero(self.original, int(self.onde.debut * n))
        i1 = audio.snap_zero(self.original, int(self.onde.fin * n) - 1)
        self.onde.debut = i0 / float(n)
        self.onde.fin = max((i1 + 1) / float(n), self.onde.debut + 0.005)
        self.onde.redraw()
        self._maj_temps()
        self.journal("Bornes calees sur les passages par zero.")

    def _memoriser_etat(self):
        """Empile l'etat courant pour pouvoir revenir en arriere."""
        if self.original is None:
            return
        self.historique.append((self.original.copy(),
                                self.onde.debut, self.onde.fin))
        if len(self.historique) > 12:
            self.historique.pop(0)

    def _annuler(self):
        if not self.historique:
            self.journal("Rien a annuler.")
            return
        self.stop()
        sample, d, f = self.historique.pop()
        self.original = sample
        self.onde.charger(self.original)
        self.onde.debut, self.onde.fin = d, f
        self.onde.redraw()
        self._maj_temps()
        self.journal("Annule. (%d etape(s) restante(s))"
                     % len(self.historique))

    def _rogner(self):
        """Reduit le sample a la selection courante."""
        if self.original is None:
            return
        self._memoriser_etat()
        a, b = self.onde.bornes_ms()
        self.original = audio.copie_decoupee(self.original, a, b)
        self.onde.charger(self.original)
        self._maj_temps()
        self.journal("Rogne : %.0f ms conserves." % self.original.duration_ms)

    # ------------------------------------------------------------ selection
    def _selection(self, traite, override=None):
        a, b = self.onde.bornes_ms()
        s = audio.copie_decoupee(self.original, a, b)
        if traite:
            cfg = override if override is not None else self.override
            s, _ = audio.process(s, self.spin.text, self.sl.value,
                                 overrides=cfg)
        return s

    # ------------------------------------------------------------ lecture
    def jouer(self, traite, override=None):
        if self.original is None:
            self.journal("Charge d'abord un WAV.")
            return
        self.stop()
        try:
            s = self._selection(traite, override)
            chemin = os.path.join(TMP, "b.wav" if traite else "a.wav")
            audio.write_wav(chemin, s)
            self.apercu = s
            from kivy.core.audio import SoundLoader
            self.son = SoundLoader.load(chemin)
            if self.son is None:
                raise RuntimeError("lecteur audio indisponible")
            self.duree_lue = max(s.duration_ms / 1000.0, 0.01)
            self.son.volume = 1.0
            self.son.play()
            self._ev = Clock.schedule_interval(self._tick, 1 / 30.0)
            i = s.info()
            self.journal("%s  %.0f ms  RMS %.1f  LUFS %.1f" % (
                "B traite " if traite else "A original",
                i["duree_ms"], i["rms_db"], audio.loudness_lufs(s)))
        except Exception as e:  # noqa: BLE001
            self.journal("Lecture impossible : %s" % e)

    def _tick(self, _dt):
        if self.son is None:
            return False
        try:
            pos = self.son.get_pos()
        except Exception:  # noqa: BLE001
            pos = 0
        if self.son.state != "play":
            self.stop()
            return False
        frac = min(max(pos / self.duree_lue, 0.0), 1.0)
        d, f = self.onde.debut, self.onde.fin
        self.onde.tete = d + frac * (f - d)
        self.onde.redraw()
        return True

    def stop(self):
        if self._ev is not None:
            self._ev.cancel()
            self._ev = None
        if self.son is not None:
            try:
                self.son.stop()
                self.son.unload()
            except Exception:  # noqa: BLE001
                pass
            self.son = None
        self.onde.tete = None
        self.onde.redraw()

    # ------------------------------------------------------------ sorties
    def exporter(self):
        if self.original is None:
            self.journal("Charge d'abord un WAV.")
            return
        try:
            s = self._selection(True)
            base = os.path.splitext(os.path.basename(self.chemin))[0]
            out = os.path.join(dossier_travail(), base + "_edit.wav")
            audio.write_wav(out, s)
            self.journal("Exporte : %s" % out)
        except Exception as e:  # noqa: BLE001
            self.journal("Export impossible : %s" % e)

    def vers_slot(self):
        if self.original is None:
            self.journal("Charge d'abord un WAV.")
            return
        ecran = self.get_slots()
        ChoixSlot(ecran.projet, lambda i: self._poser(ecran, i)).open()

    def _poser(self, ecran, index):
        try:
            s = self._selection(True)
            out = os.path.join(dossier_travail(), "slot%02d_edit.wav" % index)
            audio.write_wav(out, s)
            # deja traite : on met le preset doux pour ne pas traiter 2 fois
            ecran.projet.assigner(index, out, "doux", 0.0)
            ecran.rafraichir()
            self.journal("Slot %02d <- %.0f ms (deja traite)"
                         % (index, s.duration_ms))
        except Exception as e:  # noqa: BLE001
            self.journal("Echec : %s" % e)


# --------------------------------------------------------------------------
class EcranSlots(BoxLayout):
    def __init__(self, journal, **kw):
        super().__init__(orientation="vertical", spacing=dp(6), **kw)
        self.journal = journal
        self.projet = project.Projet("mon_kit")
        self.busy = False
        self.dernier_flux = None
        self._cache_apercu = {}
        self.selection = set()
        self.mode_selection = False
        self._compte = None

        # Un seul conteneur defilant pour toute la page : la grille garde
        # sa hauteur naturelle (10 rangees en sample, 20 en sample2) au
        # lieu d'etre comprimee dans un defilement imbrique.
        self.page = ScrollView(do_scroll_x=False)
        self.contenu = BoxLayout(orientation="vertical", spacing=dp(6),
                                 size_hint_y=None, padding=(0, 0, 0, dp(6)))
        self.contenu.bind(minimum_height=self.contenu.setter("height"))
        self.page.add_widget(self.contenu)
        BoxLayout.add_widget(self, self.page)

        self.lbl_mem = Label(text="", size_hint_y=None, height=dp(24),
                             font_size=dp(12), color=TEXTE)
        self.contenu.add_widget(self.lbl_mem)
        self.bar = ProgressBar(max=100, value=0, size_hint_y=None,
                               height=dp(12))
        self.contenu.add_widget(self.bar)

        rm = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(6))
        rm.add_widget(Label(text="Machine", size_hint_x=0.32, color=TEXTE,
                            font_size=dp(12)))
        self.spin_modele = Spinner(
            text=project.MODELES[self.projet.modele]["libelle"],
            values=[m["libelle"] for m in project.MODELES.values()])
        self.spin_modele.bind(text=self._changer_modele)
        rm.add_widget(self.spin_modele)
        self.contenu.add_widget(rm)

        self.grille = GridLayout(cols=10, spacing=dp(2), size_hint_y=None)
        self.grille.bind(minimum_height=self.grille.setter("height"))
        self.boutons = []
        self.contenu.add_widget(self.grille)
        self._construire_grille()

        r0 = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        self.b_sel = Bouton(text="Selection", size_hint_x=0.45)
        self.b_sel.bind(on_release=lambda *_: self._basculer_selection())
        r0.add_widget(self.b_sel)
        b_rem = Bouton(text="Remplir depuis un dossier")
        b_rem.bind(on_release=lambda *_: Chooser(
            self._remplir, dossiers=True).open())
        r0.add_widget(b_rem)
        self.contenu.add_widget(r0)

        r1 = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        b_s = Bouton(text="Sauver projet")
        b_s.bind(on_release=self._sauver)
        r1.add_widget(b_s)
        b_c = Bouton(text="Ouvrir projet")
        b_c.bind(on_release=lambda *_: Chooser(
            self._charger, filtres=["*.json"]).open())
        r1.add_widget(b_c)
        b_m = Bouton(text="Optimiser", couleur=CYAN)
        b_m.bind(on_release=lambda *_: self._memoire())
        r1.add_widget(b_m)
        self.contenu.add_widget(r1)

        r1b = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        b_eg = Bouton(text="Egaliser le kit", couleur=VERT)
        b_eg.bind(on_release=lambda *_: self._egaliser())
        r1b.add_widget(b_eg)
        b_t = Bouton(text="Tasser", size_hint_x=0.6)
        b_t.bind(on_release=lambda *_: self._tasser())
        r1b.add_widget(b_t)
        b_k = Bouton(text="Kit", size_hint_x=0.5)
        b_k.bind(on_release=lambda *_: KitPopup(self).open())
        r1b.add_widget(b_k)
        self.contenu.add_widget(r1b)

        r2 = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        r2.add_widget(Label(text="Qualite", size_hint_x=0.35, font_size=dp(12),
                            color=TEXTE))
        self.spin_q = Spinner(text="16",
                              values=[str(i) for i in range(16, 7, -1)])
        r2.add_widget(self.spin_q)
        self.contenu.add_widget(r2)

        r3 = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(6))
        self.b_env = Bouton(text="ENVOYER", couleur=ORANGE)
        self.b_env.bind(on_release=lambda *_: self.envoyer())
        r3.add_widget(self.b_env)
        self.b_play = Bouton(text="Rejouer le flux")
        self.b_play.bind(on_release=lambda *_: self.rejouer())
        r3.add_widget(self.b_play)
        self.contenu.add_widget(r3)

        self.lbl_syro = Label(text="", size_hint_y=None, height=dp(22),
                              font_size=dp(11), color=TEXTE_2)
        self.contenu.add_widget(self.lbl_syro)

        self.rafraichir()
        Clock.schedule_once(lambda *_: self.maj_syro(), 0.3)
        Clock.schedule_once(lambda *_: self._reprendre(), 0.6)

    def maj_syro(self):
        if syro.disponible():
            self.lbl_syro.text = "Envoi direct actif - librarian Korg inutile"
            self.lbl_syro.color = (0.4, 0.9, 0.5, 1)
        else:
            self.lbl_syro.text = "Envoi direct indisponible (lib native absente)"
            self.lbl_syro.color = (0.9, 0.5, 0.3, 1)
            self.b_env.disabled = True

    def rafraichir(self):
        p = self.projet
        if len(self.boutons) != p.nb_slots:
            self._construire_grille()
        for i, b in enumerate(self.boutons):
            slot = p.slots[i]
            b.set_couleur(ORANGE_S if not slot.vide else GRIS)
            num = "%03d" % i if p.nb_slots > 100 else "%02d" % i
            if slot.vide:
                b.text = num
                b.set_apercu(None)
            else:
                marque = "*" if slot.taux else ""
                b.text = "%s%s\n%s" % (num, marque, slot.nom[:5])
                b.set_apercu(self._cache_apercu.get(slot.chemin))
                if i in self.selection:
                    b.set_couleur(CYAN)
            b.halign = "center"
        threading.Thread(target=self._calculer_apercus, daemon=True).start()
        if hasattr(self, "b_env"):
            n = len(self.selection)
            self.b_env.text = ("ENVOYER (%d)" % n) if n else "ENVOYER"
        pct = p.memoire_pct()
        self.bar.value = min(pct, 100)
        self.lbl_mem.text = "%d/%d slots - %.1f s / %.0f s (%.0f %%)%s" % (
            len(p.occupes()), p.nb_slots, p.memoire_utilisee_s(),
            p.memoire_totale_s(), pct,
            "  MEMOIRE DEPASSEE" if p.depassement() else "")

    def _calculer_apercus(self):
        """Calcule les mini formes d'onde manquantes, en tache de fond."""
        nouveaux = False
        for slot in self.projet.occupes():
            if slot.chemin in self._cache_apercu:
                continue
            try:
                s = audio.read_wav(slot.chemin)
                self._cache_apercu[slot.chemin] = audio.peaks(s, 18)
                nouveaux = True
            except Exception:  # noqa: BLE001
                self._cache_apercu[slot.chemin] = None
        if nouveaux:
            self._poser_apercus()

    @mainthread
    def _poser_apercus(self):
        for i, b in enumerate(self.boutons):
            slot = self.projet.slots[i]
            if not slot.vide:
                b.set_apercu(self._cache_apercu.get(slot.chemin))

    def _construire_grille(self):
        """(Re)cree les boutons : 100 slots sur sample, 200 sur sample2."""
        self.grille.clear_widgets()
        self.boutons = []
        for i in range(self.projet.nb_slots):
            b = SlotBouton(text="%02d" % i, font_size=dp(10),
                           size_hint_y=None, height=dp(42),
                           couleur=GRIS, rayon=5)
            b.bind(on_release=lambda w, idx=i: self._toucher(idx))
            self.boutons.append(b)
            self.grille.add_widget(b)

    def _changer_modele(self, _sp, libelle):
        cle = next((k for k, m in project.MODELES.items()
                    if m["libelle"] == libelle), None)
        if cle is None or cle == self.projet.modele:
            return
        perdus = self.projet.perdus_si(cle)
        if perdus:
            self.journal("ATTENTION : %d slot(s) au-dela de %d seront perdus."
                         % (len(perdus), project.MODELES[cle]["slots"] - 1))
            for s in perdus[:5]:
                self.journal("  %03d %s" % (s.index, s.nom[:16]))
        self.projet.changer_modele(cle)
        self.selection = {i for i in self.selection
                          if i < self.projet.nb_slots}
        self._construire_grille()
        self.rafraichir()
        self.journal("Machine : %s (%d slots, %.0f s)"
                     % (libelle, self.projet.nb_slots,
                        self.projet.memoire_totale_s()))

    def _toucher(self, index):
        """Un appui : edite le slot, ou le (de)selectionne en mode selection."""
        if not self.mode_selection:
            SlotPopup(self, index).open()
            return
        if self.projet.slots[index].vide:
            return
        if index in self.selection:
            self.selection.discard(index)
        else:
            self.selection.add(index)
        self.rafraichir()

    def _basculer_selection(self):
        self.mode_selection = not self.mode_selection
        if not self.mode_selection:
            self.selection.clear()
        self.b_sel.text = "Selection ON" if self.mode_selection else "Selection"
        self.b_sel.set_couleur(CYAN if self.mode_selection else GRIS)
        self.journal("Mode selection : appuie sur les slots a envoyer."
                     if self.mode_selection else "Selection annulee.")
        self.rafraichir()

    def _tasser(self):
        n = self.projet.tasser()
        self.journal("%d sample(s) regroupe(s) au debut." % n)
        self.rafraichir()

    def _egaliser(self):
        if self.busy:
            return
        if not self.projet.occupes():
            self.journal("Aucun slot rempli.")
            return
        self.busy = True
        threading.Thread(target=self._worker_egaliser, daemon=True).start()

    def _worker_egaliser(self):
        try:
            self.journal("--- EGALISATION DU KIT ---")
            self.journal("Mesure du niveau percu de chaque slot...")

            def prog(n, total, slot):
                if n % 5 == 0 or n == total:
                    self.journal("  mesure %d/%d" % (n, total))

            rap = self.projet.egaliser(progression=prog)
            if not rap:
                self.journal("Rien a egaliser.")
                return
            cible = next((r["cible"] for r in rap if "cible" in r), None)
            if cible is not None:
                self.journal("Cible : %.1f LUFS (le slot le plus faible)"
                             % cible)
            for r in rap:
                if "erreur" in r:
                    self.journal("  %02d %-12s ECHEC" % (r["slot"],
                                                         r["nom"][:12]))
                else:
                    self.journal("  %02d %-12s %+5.1f dB -> %.1f LUFS" % (
                        r["slot"], r["nom"][:12], r["gain_db"], r["obtenu"]))
            self.journal("Tous les pads repondent au meme volume percu.")
        except Exception as e:  # noqa: BLE001
            self.journal("ERREUR : %s" % e)
        finally:
            self._apres_optim()
            self.busy = False

    def _remplir(self, dossier):
        places = self.projet.remplir_depuis_dossier(dossier)
        self.journal("%d sample(s) place(s)." % len(places))
        self.rafraichir()

    def exporter_kit(self, nom):
        if self.busy:
            return
        self.busy = True
        threading.Thread(target=self._worker_export, args=(nom,),
                         daemon=True).start()

    def _worker_export(self, nom):
        try:
            self.projet.nom = nom
            cible = os.path.join(dossier_travail(),
                                 "%s.kit.zip" % kit._nom_sur(nom))
            self.journal("--- EXPORT DU KIT ---")

            def prog(n, total, slot):
                self.journal("  [%d/%d] slot %02d %s" % (n, total, slot.index,
                                                         slot.nom[:14]))

            rap = kit.exporter(self.projet, cible, True, prog)
            ok = sum(1 for r in rap if "erreur" not in r)
            taille = os.path.getsize(cible) / 1048576.0
            self.journal("%d son(s) dans %s" % (ok, cible))
            self.journal("Taille : %.1f Mo. Partageable tel quel." % taille)
        except Exception as e:  # noqa: BLE001
            self.journal("Export impossible : %s" % e)
        finally:
            self.busy = False

    def importer_kit(self, chemin):
        if self.busy:
            return
        self.busy = True
        threading.Thread(target=self._worker_import, args=(chemin,),
                         daemon=True).start()

    def _worker_import(self, chemin):
        try:
            i = kit.infos(chemin)
            self.journal("--- IMPORT : %s (%d slots) ---" % (i["nom"],
                                                             i["slots"]))

            def prog(n, total, interne):
                if n % 5 == 0 or n == total:
                    self.journal("  extraction %d/%d" % (n, total))

            p = kit.importer(chemin, dossier_travail(), prog)
            self._poser_projet(p)
        except Exception as e:  # noqa: BLE001
            self.journal("Import impossible : %s" % e)
        finally:
            self.busy = False

    @mainthread
    def _poser_projet(self, p):
        self.projet = p
        self.selection.clear()
        self._cache_apercu.clear()
        self._construire_grille()
        if hasattr(self, "spin_modele"):
            self.spin_modele.text = project.MODELES[p.modele]["libelle"]
        if p.chemin_fichier:
            self._memoriser(p.chemin_fichier)
        self.rafraichir()
        self.journal("Kit '%s' importe : %d slots, %.1f s de memoire."
                     % (p.nom, len(p.occupes()), p.memoire_utilisee_s()))

    def _reprendre(self):
        """Recharge le dernier projet ouvert, s'il existe encore."""
        try:
            chemin = etat.dernier_projet(etat.chemin_defaut(dossier_travail()))
            if not chemin:
                return
            self.projet = project.Projet.charger(chemin)
            self._construire_grille()
            if hasattr(self, "spin_modele"):
                self.spin_modele.text = \
                    project.MODELES[self.projet.modele]["libelle"]
            self.rafraichir()
            self.journal("Projet repris : %s (%d slots)"
                         % (os.path.basename(chemin),
                            len(self.projet.occupes())))
        except Exception as e:  # noqa: BLE001
            self.journal("Reprise impossible : %s" % e)

    def _memoriser(self, chemin):
        try:
            etat.memoriser_projet(chemin,
                                  etat.chemin_defaut(dossier_travail()))
        except Exception:  # noqa: BLE001
            pass

    def _sauver(self, *_):
        try:
            chemin = self.projet.chemin_fichier or os.path.join(
                dossier_travail(), "mon_kit.volca.json")
            self.projet.sauver(chemin)
            self._memoriser(chemin)
            self.journal("Projet enregistre : %s" % chemin)
        except Exception as e:  # noqa: BLE001
            self.journal("Erreur sauvegarde : %s" % e)

    def _charger(self, chemin):
        try:
            self.projet = project.Projet.charger(chemin)
            self.selection.clear()
            self._construire_grille()
            if hasattr(self, "spin_modele"):
                self.spin_modele.text = \
                    project.MODELES[self.projet.modele]["libelle"]
            self._memoriser(chemin)
            self.journal("Projet charge : %s" % chemin)
            self.rafraichir()
        except Exception as e:  # noqa: BLE001
            self.journal("Erreur chargement : %s" % e)

    def _memoire(self):
        threading.Thread(target=self._worker_memoire, daemon=True).start()

    def _worker_memoire(self):
        if not self.projet.occupes():
            self.journal("Aucun slot rempli.")
            return
        self.journal("--- OPTIMISATION MEMOIRE ---")
        avant = self.projet.memoire_utilisee_s()

        def prog(n, total, slot):
            if n % 5 == 0 or n == total:
                self.journal("  analyse %d/%d" % (n, total))

        rap, gagne = self.projet.optimiser(prog)
        for r in rap:
            if "erreur" in r:
                self.journal("  %02d %-12s ECHEC" % (r["slot"], r["nom"][:12]))
            else:
                self.journal("  %02d %-12s -> %d Hz  (%.2f s)" % (
                    r["slot"], r["nom"][:12], r["taux"], r["eco_s"]))
        if gagne:
            self.journal("Memoire %.1f s -> %.1f s, %.1f s recuperees." % (
                avant, self.projet.memoire_utilisee_s(), gagne))
            self.journal("Les slots optimises sont marques d'une etoile.")
        else:
            self.journal("Rien a gagner : tous ont besoin de leur aigu.")
        self._apres_optim()

    @mainthread
    def _apres_optim(self):
        self.rafraichir()

    @mainthread
    def _fin(self):
        self.busy = False
        self.b_env.disabled = not syro.disponible()

    def envoyer(self):
        if self.busy:
            return
        if not self.projet.occupes():
            self.journal("Aucun slot rempli.")
            return
        if self.selection:
            self.journal("Envoi partiel : %d slot(s) sur %d."
                         % (len(self.selection), len(self.projet.occupes())))
        if self.projet.depassement():
            self.journal("ATTENTION : memoire depassee.")
        self.busy = True
        self.b_env.disabled = True
        threading.Thread(target=self._worker_envoi, daemon=True).start()

    def _worker_envoi(self):
        try:
            self.journal("--- PREPARATION ---")
            d = tempfile.mkdtemp(prefix="volcagain_")
            prepares = []
            occ = [s for s in self.projet.occupes()
                   if not self.selection or s.index in self.selection]
            for n, slot in enumerate(occ, 1):
                s = audio.read_wav(slot.chemin)
                s, _ = audio.process(s, slot.preset, slot.gain_db)
                if slot.taux:
                    audio.changer_taux(s, slot.taux)
                out = os.path.join(d, "%02d.wav" % slot.index)
                audio.write_wav(out, s)
                prepares.append((slot.index, out))
                self.journal("[%d/%d] slot %02d %s" % (
                    n, len(occ), slot.index, slot.nom[:16]))

            cible = os.path.join(dossier_travail(), "transfert.wav")
            res = syro.build_stream(prepares, cible,
                                    quality=int(self.spin_q.text))
            self.dernier_flux = res["chemin"]
            self.duree_flux = res["duree_s"]
            self.journal("Flux pret : %.1f s" % res["duree_s"])
            self.journal("Casque vers SYNC IN, volume a fond.")
            syro.jouer(res["chemin"])
            self._demarrer_compte(res["duree_s"])
        except syro.SyroIndisponible as e:
            self.journal("Envoi indisponible : %s" % e)
        except Exception as e:  # noqa: BLE001
            self.journal("ERREUR : %s" % e)
        finally:
            self._fin()

    @mainthread
    def _demarrer_compte(self, duree):
        """Compte a rebours pendant la lecture du flux."""
        self._arreter_compte()
        self._reste = duree
        self._total = max(duree, 0.1)
        self.bar.max = 100
        self._compte = Clock.schedule_interval(self._tic_compte, 0.25)
        self.lbl_syro.text = "TRANSFERT EN COURS - ne touche a rien"
        self.lbl_syro.color = CYAN

    def _tic_compte(self, dt):
        self._reste -= dt
        if self._reste <= 0:
            self._arreter_compte()
            self.lbl_syro.text = "Transfert termine. La volca redemarre."
            self.lbl_syro.color = (0.4, 0.9, 0.5, 1)
            self.journal("Transfert termine.")
            Clock.schedule_once(lambda *_: self.maj_syro(), 4)
            self.rafraichir()
            return False
        fait = 100.0 * (1.0 - self._reste / self._total)
        self.bar.value = fait
        self.lbl_mem.text = "TRANSFERT  %2.0f %%  -  %d s restantes" % (
            fait, int(self._reste) + 1)
        return True

    def _arreter_compte(self):
        if self._compte is not None:
            self._compte.cancel()
            self._compte = None

    def rejouer(self):
        if not self.dernier_flux:
            self.journal("Aucun flux genere.")
            return
        try:
            syro.jouer(self.dernier_flux)
            self.journal("Relecture du flux...")
            self._demarrer_compte(getattr(self, "duree_flux", 10.0))
        except Exception as e:  # noqa: BLE001
            self.journal("Lecture impossible : %s" % e)


# --------------------------------------------------------------------------
class EcranPattern(BoxLayout):
    """Sequenceur : 10 parties x 16 pas, envoi vers un des 10 patterns."""

    def __init__(self, journal, get_slots, **kw):
        super().__init__(orientation="vertical", spacing=dp(6), **kw)
        self.journal = journal
        self.get_slots = get_slots
        self.motif = pattern.vierge("nouveau")
        self.partie = 1
        self.busy = False

        self.page = ScrollView(do_scroll_x=False)
        self.contenu = BoxLayout(orientation="vertical", spacing=dp(6),
                                 size_hint_y=None, padding=(0, 0, 0, dp(6)))
        self.contenu.bind(minimum_height=self.contenu.setter("height"))
        self.page.add_widget(self.contenu)
        self.add_widget(self.page)

        r0 = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        r0.add_widget(Label(text="Partie", size_hint_x=0.3, color=TEXTE,
                            font_size=dp(12)))
        self.spin_partie = Spinner(
            text="1", values=[str(i) for i in range(1, 11)])
        self.spin_partie.bind(text=self._changer_partie)
        r0.add_widget(self.spin_partie)
        self.contenu.add_widget(r0)

        r1 = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        self.lbl_sample = Label(text="Sample 0", size_hint_x=0.45,
                                color=TEXTE, font_size=dp(12))
        r1.add_widget(self.lbl_sample)
        self.sl_sample = Slider(min=0, max=199, value=0, step=1)
        self.sl_sample.bind(value=self._changer_sample)
        r1.add_widget(self.sl_sample)
        self.contenu.add_widget(r1)

        # grille de pas : deux rangees de huit
        cadre = Panneau(orientation="vertical", size_hint_y=None,
                        height=dp(130), padding=dp(6), spacing=dp(4))
        self.pas = []
        for rangee in range(2):
            ligne = BoxLayout(spacing=dp(3))
            for col in range(8):
                i = rangee * 8 + col
                b = Bouton(text="%d" % (i + 1), font_size=dp(13), rayon=6)
                b.bind(on_release=lambda w, idx=i: self._basculer(idx))
                self.pas.append(b)
                ligne.add_widget(b)
            cadre.add_widget(ligne)
        self.contenu.add_widget(cadre)

        r2 = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(4))
        self.b_fonc = {}
        for nom, libelle in (("loop", "Loop"), ("reverb", "Reverb"),
                             ("reverse", "Rev."), ("mute", "Mute")):
            b = Bouton(text=libelle, font_size=dp(11))
            b.bind(on_release=lambda w, n=nom: self._basculer_fonction(n))
            self.b_fonc[nom] = b
            r2.add_widget(b)
        self.contenu.add_widget(r2)

        r3 = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(6))
        self.lbl_niveau = Label(text="Niveau 127", size_hint_x=0.45,
                                color=TEXTE, font_size=dp(12))
        r3.add_widget(self.lbl_niveau)
        self.sl_niveau = Slider(min=0, max=127, value=127, step=1)
        self.sl_niveau.bind(value=self._changer_niveau)
        r3.add_widget(self.sl_niveau)
        self.contenu.add_widget(r3)

        r4 = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(6))
        for txt, fn in (("Vider partie", self._vider_partie),
                        ("Tout vider", self._vider_tout)):
            b = Bouton(text=txt, font_size=dp(12))
            b.bind(on_release=lambda w, f=fn: f())
            r4.add_widget(b)
        self.contenu.add_widget(r4)

        r5 = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        b_o = Bouton(text="Ouvrir .dat", couleur=CYAN)
        b_o.bind(on_release=lambda *_: Chooser(
            self._ouvrir, filtres=["*.dat", "*.DAT"]).open())
        r5.add_widget(b_o)
        b_s = Bouton(text="Enregistrer")
        b_s.bind(on_release=lambda *_: NomPopup(
            "Nom du pattern", self.motif.nom, self._enregistrer).open())
        r5.add_widget(b_s)
        self.contenu.add_widget(r5)

        r6 = BoxLayout(size_hint_y=None, height=dp(50), spacing=dp(6))
        r6.add_widget(Label(text="Vers", size_hint_x=0.22, color=TEXTE,
                            font_size=dp(12)))
        self.spin_dest = Spinner(text="0", values=[str(i) for i in range(10)],
                                 size_hint_x=0.28)
        r6.add_widget(self.spin_dest)
        self.b_env = Bouton(text="ENVOYER", couleur=ORANGE)
        self.b_env.bind(on_release=lambda *_: self.envoyer())
        r6.add_widget(self.b_env)
        self.contenu.add_widget(r6)

        self.lbl_etat = Label(text="", size_hint_y=None, height=dp(22),
                              font_size=dp(11), color=TEXTE_2)
        self.contenu.add_widget(self.lbl_etat)

        self.rafraichir()
        Clock.schedule_once(lambda *_: self._maj_syro(), 0.4)

    # ------------------------------------------------------------ etat
    def _maj_syro(self):
        if not syro.disponible():
            self.b_env.disabled = True
            self.lbl_etat.text = "Envoi indisponible (lib native absente)"

    def _p(self):
        return self.motif.partie(self.partie)

    def rafraichir(self):
        p = self._p()
        for i, b in enumerate(self.pas):
            if p.pas_actif(i):
                b.set_couleur(ORANGE)
            else:
                b.set_couleur(GRIS if i % 4 else ORANGE_S)
        for nom, b in self.b_fonc.items():
            b.set_couleur(CYAN if p.actif(nom) else GRIS)
        self.lbl_sample.text = "Sample %d" % p.sample_num
        self.lbl_niveau.text = "Niveau %d" % p.level
        utilisees = len(self.motif.parties_utilisees())
        self.lbl_etat.text = "%s - %d partie(s) utilisee(s)" % (
            self.motif.nom, utilisees)

    # ------------------------------------------------------------ edition
    def _changer_partie(self, _sp, txt):
        self.partie = int(txt)
        p = self._p()
        self.sl_sample.value = p.sample_num
        self.sl_niveau.value = p.level
        self.rafraichir()

    def _basculer(self, i):
        self._p().basculer_pas(i)
        self.rafraichir()

    def _basculer_fonction(self, nom):
        p = self._p()
        p.mettre(nom, not p.actif(nom))
        self.rafraichir()

    def _changer_sample(self, _sl, v):
        self._p().sample_num = int(v)
        self.lbl_sample.text = "Sample %d" % int(v)

    def _changer_niveau(self, _sl, v):
        self._p().level = int(v)
        self.lbl_niveau.text = "Niveau %d" % int(v)

    def _vider_partie(self):
        self._p().depuis_liste([])
        self.rafraichir()
        self.journal("Partie %d videe." % self.partie)

    def _vider_tout(self):
        self.motif.vider()
        self.rafraichir()
        self.journal("Pattern vide.")

    # ------------------------------------------------------------ fichiers
    def _ouvrir(self, chemin):
        try:
            self.motif = pattern.Motif.charger(chemin)
            self.spin_partie.text = "1"
            self.partie = 1
            self.sl_sample.value = self._p().sample_num
            self.sl_niveau.value = self._p().level
            self.rafraichir()
            self.journal("Pattern charge : %s (%d parties)"
                         % (self.motif.nom,
                            len(self.motif.parties_utilisees())))
        except Exception as e:  # noqa: BLE001
            self.journal("Lecture impossible : %s" % e)

    def _enregistrer(self, nom):
        try:
            self.motif.nom = nom
            cible = os.path.join(dossier_travail(), "%s.dat" % nom)
            self.motif.sauver(cible)
            self.rafraichir()
            self.journal("Pattern enregistre : %s" % cible)
        except Exception as e:  # noqa: BLE001
            self.journal("Enregistrement impossible : %s" % e)

    # ------------------------------------------------------------ envoi
    def envoyer(self):
        if self.busy:
            return
        if not self.motif.parties_utilisees():
            self.journal("Pattern vide : rien a envoyer.")
            return
        self.busy = True
        self.b_env.disabled = True
        threading.Thread(target=self._worker_envoi, daemon=True).start()

    def _worker_envoi(self):
        try:
            dest = int(self.spin_dest.text)
            self.journal("--- ENVOI DU PATTERN %d ---" % dest)
            self.journal("Le pattern %d va etre ECRASE." % dest)
            cible = os.path.join(dossier_travail(), "pattern.wav")
            res = syro.pattern_stream([(dest, self.motif.to_bytes())], cible)
            self.journal("Flux pret : %.1f s" % res["duree_s"])
            self.journal("Casque vers SYNC IN, volume a fond.")
            syro.jouer(res["chemin"])
        except syro.SyroIndisponible as e:
            self.journal("Envoi indisponible : %s" % e)
        except Exception as e:  # noqa: BLE001
            self.journal("ERREUR : %s" % e)
        finally:
            self._fin()

    @mainthread
    def _fin(self):
        self.busy = False
        self.b_env.disabled = not syro.disponible()


class EcranTuto(BoxLayout):
    def __init__(self, **kw):
        super().__init__(orientation="vertical", spacing=dp(6), **kw)

        r = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6))
        r.add_widget(Label(text="Sujet", size_hint_x=0.25, color=TEXTE))
        self.spin = Spinner(text=tips.titres()[0], values=tips.titres(),
                            text_size=(None, None))
        self.spin.bind(text=self._maj)
        r.add_widget(self.spin)
        self.add_widget(r)

        sv = ScrollView()
        self.lbl = Label(text="", size_hint_y=None, halign="left",
                         valign="top", font_size=dp(13), color=TEXTE,
                         padding=(dp(8), dp(8)))
        self.lbl.bind(texture_size=lambda i, v: setattr(i, "height", v[1]),
                      width=lambda i, v: setattr(i, "text_size", (v, None)))
        sv.add_widget(self.lbl)
        self.add_widget(sv)

        self._maj(None, self.spin.text)

    def _maj(self, _sp, titre):
        i = tips.titres().index(titre)
        self.lbl.text = "\n".join(tips.SECTIONS[i]["lignes"])


# --------------------------------------------------------------------------
class Root(BoxLayout):
    ONGLETS = ("TRAIT.", "SLOTS", "EDIT.", "PATT.", "TUTO")

    def __init__(self, **kw):
        super().__init__(orientation="vertical", spacing=dp(6),
                         padding=dp(8), **kw)

        entete = BoxLayout(orientation="vertical", size_hint_y=None,
                           height=dp(52), spacing=0)
        logo = chemin_asset("logo.png")
        if logo:
            entete.add_widget(KivyImage(source=logo, allow_stretch=True,
                                        keep_ratio=True, size_hint_y=0.78))
        else:
            entete.add_widget(Label(text="[b]MOC'TA BASS[/b]", markup=True,
                                    color=CYAN, size_hint_y=0.78))
        entete.add_widget(Label(
            text="volca sample  -  v%s" % __version__, font_size=dp(10),
            color=TEXTE_2, size_hint_y=0.22))
        self.add_widget(entete)

        barre = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(4))
        self.tabs = []
        for i, nom in enumerate(self.ONGLETS):
            b = Bouton(text=nom, font_size=dp(11), rayon=6)
            b.bind(on_release=lambda w, idx=i: self.afficher(idx))
            self.tabs.append(b)
            barre.add_widget(b)
        self.add_widget(barre)

        self.zone = BoxLayout()
        self.add_widget(self.zone)

        sv = ScrollView(size_hint_y=0.22)
        self.log = Label(text="Pret.\n", size_hint_y=None, halign="left",
                         valign="top", font_size=dp(11), color=TEXTE_2)
        self.log.bind(texture_size=lambda i, v: setattr(i, "height", v[1]),
                      width=lambda i, v: setattr(i, "text_size", (v, None)))
        sv.add_widget(self.log)
        self.add_widget(sv)

        # Chaque ecran est construit isolement : si l'un echoue, il est
        # remplace par sa trace au lieu d'emporter toute l'application.
        self.ec_slots = self._fabriquer("SLOTS", EcranSlots, self.journal)

        fabriques = [
            ("TRAIT.", EcranTraitement, (self.journal,)),
            (None, None, None),   # SLOTS, deja construit
            ("EDIT.", EcranEditeur, (self.journal, lambda: self.ec_slots)),
            ("PATT.", EcranPattern, (self.journal, lambda: self.ec_slots)),
            ("TUTO", EcranTuto, ()),
        ]
        self.ecrans = []
        for nom, classe, args in fabriques:
            if classe is None:
                self.ecrans.append(self.ec_slots)
            else:
                self.ecrans.append(self._fabriquer(nom, classe, *args))
        self.afficher(0)

    def _fabriquer(self, nom, classe, *args):
        try:
            return classe(*args)
        except Exception as e:  # noqa: BLE001
            texte = trace_complete(e)
            self.journal("ECHEC de l'onglet %s : %s" % (nom, e))
            return EcranErreur(texte, "ONGLET %s" % nom)

    @mainthread
    def journal(self, txt):
        lignes = self.log.text.split("\n")
        if len(lignes) > 200:
            self.log.text = "\n".join(lignes[-120:])
        self.log.text += txt + "\n"

    def afficher(self, i):
        # arreter la lecture en quittant l'editeur
        for e in self.ecrans:
            if isinstance(e, EcranEditeur):
                e.stop()
        self.zone.clear_widgets()
        self.zone.add_widget(self.ecrans[i])
        for j, b in enumerate(self.tabs):
            b.set_couleur(ORANGE if j == i else GRIS)


class VolcaGainApp(App):
    title = "MOC'TA BASS"

    def build(self):
        Window.clearcolor = FOND

        # Toute exception non rattrapee est ecrite sur le disque, meme si
        # l'interface ne peut plus rien afficher.
        def _hook(t, v, tr):
            try:
                import traceback as tb
                journal_crash("MOC'TA BASS v%s\n\n%s" % (
                    __version__, "".join(tb.format_exception(t, v, tr))))
            except Exception:  # noqa: BLE001
                pass
            sys.__excepthook__(t, v, tr)

        sys.excepthook = _hook
        try:
            perso = reglages.charger(reglages.chemin_defaut(dossier_travail()))
            if perso:
                print("presets personnalises charges :", list(perso))
        except Exception:  # noqa: BLE001
            pass
        if IS_ANDROID:
            Clock.schedule_once(lambda *_: self._permissions(), 0.5)
        return Root()

    @staticmethod
    def _permissions():
        try:
            from android.permissions import Permission, request_permissions
            request_permissions([
                Permission.READ_EXTERNAL_STORAGE,
                Permission.WRITE_EXTERNAL_STORAGE,
            ])
        except Exception:  # noqa: BLE001
            pass


if __name__ == "__main__":
    VolcaGainApp().run()
