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
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.progressbar import ProgressBar
from kivy.uix.scrollview import ScrollView
from kivy.uix.slider import Slider
from kivy.uix.spinner import Spinner
from kivy.uix.widget import Widget

from volca import __version__, audio, batch, project, syro, tips

# ---------------------------------------------------------------- palette
FOND = (0.055, 0.055, 0.07, 1)
PANNEAU = (0.10, 0.10, 0.13, 1)
ORANGE = (0.92, 0.33, 0.09, 1)
ORANGE_S = (0.55, 0.20, 0.05, 1)
GRIS = (0.19, 0.19, 0.23, 1)
VERT = (0.16, 0.62, 0.35, 1)
BLEU = (0.24, 0.52, 0.78, 1)
TEXTE = (0.90, 0.90, 0.92, 1)
TEXTE_2 = (0.62, 0.62, 0.68, 1)

IS_ANDROID = "ANDROID_ARGUMENT" in os.environ
TMP = tempfile.mkdtemp(prefix="volcagain_ui_")


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
        for i in range(project.NB_SLOTS):
            libre = projet.slots[i].vide
            b = Bouton(text="%02d" % i, font_size=dp(11), size_hint_y=None,
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
        super().__init__(title="Slot %02d" % index, size_hint=(0.9, None),
                         height=dp(340), **kw)

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

        r_rang = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(6))
        for txt, action in (("Deplacer", "deplacer"),
                            ("Echanger", "echanger"),
                            ("Copier", "dupliquer")):
            bb = Bouton(text=txt, font_size=dp(12), couleur=BLEU)
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
        self.b_ana = Bouton(text="Analyser", couleur=BLEU)
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
                        ("Rogner", self._rogner)):
            bb = Bouton(text=txt, font_size=dp(12))
            bb.bind(on_release=lambda w, f=fn: f())
            r0.add_widget(bb)
        self.add_widget(r0)

        r1 = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6))
        r1.add_widget(Label(text="Preset", size_hint_x=0.3, color=TEXTE))
        self.spin = Spinner(text="punch", values=sorted(audio.PRESETS))
        r1.add_widget(self.spin)
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
        self.b_a = Bouton(text="A  original", couleur=BLEU)
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
            self.original = audio.read_wav(chemin)
            self.chemin = chemin
            self.onde.charger(self.original)
            i = self.original.info()
            self.lbl_nom.text = "%s  -  %.0f ms  RMS %.1f dB  LUFS %.1f" % (
                os.path.basename(chemin), i["duree_ms"], i["rms_db"],
                audio.loudness_lufs(self.original))
            self._maj_temps()
            self.journal("Editeur : %s charge" % os.path.basename(chemin))
        except Exception as e:  # noqa: BLE001
            self.journal("Lecture impossible : %s" % e)

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

    def _rogner(self):
        """Reduit le sample a la selection courante."""
        if self.original is None:
            return
        a, b = self.onde.bornes_ms()
        self.original = audio.copie_decoupee(self.original, a, b)
        self.onde.charger(self.original)
        self._maj_temps()
        self.journal("Rogne : %.0f ms conserves." % self.original.duration_ms)

    # ------------------------------------------------------------ selection
    def _selection(self, traite):
        a, b = self.onde.bornes_ms()
        s = audio.copie_decoupee(self.original, a, b)
        if traite:
            s, _ = audio.process(s, self.spin.text, self.sl.value)
        return s

    # ------------------------------------------------------------ lecture
    def jouer(self, traite):
        if self.original is None:
            self.journal("Charge d'abord un WAV.")
            return
        self.stop()
        try:
            s = self._selection(traite)
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

        self.lbl_mem = Label(text="", size_hint_y=None, height=dp(24),
                             font_size=dp(12), color=TEXTE)
        self.add_widget(self.lbl_mem)
        self.bar = ProgressBar(max=100, value=0, size_hint_y=None,
                               height=dp(12))
        self.add_widget(self.bar)

        sv = ScrollView(size_hint_y=0.5)
        self.grille = GridLayout(cols=10, spacing=dp(2), size_hint_y=None)
        self.grille.bind(minimum_height=self.grille.setter("height"))
        self.boutons = []
        for i in range(project.NB_SLOTS):
            b = SlotBouton(text="%02d" % i, font_size=dp(10),
                           size_hint_y=None, height=dp(42),
                           couleur=GRIS, rayon=5)
            b.bind(on_release=lambda w, idx=i: SlotPopup(self, idx).open())
            self.boutons.append(b)
            self.grille.add_widget(b)
        sv.add_widget(self.grille)
        self.add_widget(sv)

        r0 = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        b_rem = Bouton(text="Remplir depuis un dossier")
        b_rem.bind(on_release=lambda *_: Chooser(
            self._remplir, dossiers=True).open())
        r0.add_widget(b_rem)
        self.add_widget(r0)

        r1 = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        b_s = Bouton(text="Sauver projet")
        b_s.bind(on_release=self._sauver)
        r1.add_widget(b_s)
        b_c = Bouton(text="Ouvrir projet")
        b_c.bind(on_release=lambda *_: Chooser(
            self._charger, filtres=["*.json"]).open())
        r1.add_widget(b_c)
        b_m = Bouton(text="Optimiser", couleur=BLEU)
        b_m.bind(on_release=lambda *_: self._memoire())
        r1.add_widget(b_m)
        self.add_widget(r1)

        r1b = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        b_eg = Bouton(text="Egaliser le kit", couleur=VERT)
        b_eg.bind(on_release=lambda *_: self._egaliser())
        r1b.add_widget(b_eg)
        b_t = Bouton(text="Tasser")
        b_t.bind(on_release=lambda *_: self._tasser())
        r1b.add_widget(b_t)
        self.add_widget(r1b)

        r2 = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        r2.add_widget(Label(text="Qualite", size_hint_x=0.35, font_size=dp(12),
                            color=TEXTE))
        self.spin_q = Spinner(text="16",
                              values=[str(i) for i in range(16, 7, -1)])
        r2.add_widget(self.spin_q)
        self.add_widget(r2)

        r3 = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(6))
        self.b_env = Bouton(text="ENVOYER", couleur=ORANGE)
        self.b_env.bind(on_release=lambda *_: self.envoyer())
        r3.add_widget(self.b_env)
        self.b_play = Bouton(text="Rejouer le flux")
        self.b_play.bind(on_release=lambda *_: self.rejouer())
        r3.add_widget(self.b_play)
        self.add_widget(r3)

        self.lbl_syro = Label(text="", size_hint_y=None, height=dp(22),
                              font_size=dp(11), color=TEXTE_2)
        self.add_widget(self.lbl_syro)

        self.rafraichir()
        Clock.schedule_once(lambda *_: self.maj_syro(), 0.3)

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
        for i, b in enumerate(self.boutons):
            slot = p.slots[i]
            b.set_couleur(ORANGE_S if not slot.vide else GRIS)
            if slot.vide:
                b.text = "%02d" % i
                b.set_apercu(None)
            else:
                marque = "*" if slot.taux else ""
                b.text = "%02d%s\n%s" % (i, marque, slot.nom[:5])
                b.set_apercu(self._cache_apercu.get(slot.chemin))
            b.halign = "center"
        threading.Thread(target=self._calculer_apercus, daemon=True).start()
        pct = p.memoire_pct()
        self.bar.value = min(pct, 100)
        self.lbl_mem.text = "%d/%d slots - %.1f s / %.0f s (%.0f %%)%s" % (
            len(p.occupes()), project.NB_SLOTS, p.memoire_utilisee_s(),
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

    def _sauver(self, *_):
        try:
            chemin = os.path.join(dossier_travail(), "mon_kit.volca.json")
            self.projet.sauver(chemin)
            self.journal("Projet enregistre : %s" % chemin)
        except Exception as e:  # noqa: BLE001
            self.journal("Erreur sauvegarde : %s" % e)

    def _charger(self, chemin):
        try:
            self.projet = project.Projet.charger(chemin)
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
            occ = self.projet.occupes()
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
            self.journal("Flux pret : %.1f s" % res["duree_s"])
            self.journal("Casque vers SYNC IN, volume a fond.")
            syro.jouer(res["chemin"])
        except syro.SyroIndisponible as e:
            self.journal("Envoi indisponible : %s" % e)
        except Exception as e:  # noqa: BLE001
            self.journal("ERREUR : %s" % e)
        finally:
            self._fin()

    def rejouer(self):
        if not self.dernier_flux:
            self.journal("Aucun flux genere.")
            return
        try:
            syro.jouer(self.dernier_flux)
            self.journal("Relecture du flux...")
        except Exception as e:  # noqa: BLE001
            self.journal("Lecture impossible : %s" % e)


# --------------------------------------------------------------------------
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
    ONGLETS = ("TRAIT.", "SLOTS", "EDIT.", "TUTO")

    def __init__(self, **kw):
        super().__init__(orientation="vertical", spacing=dp(6),
                         padding=dp(8), **kw)

        self.add_widget(Label(
            text="[b]VOLCA GAIN[/b]  [size=13sp]v%s[/size]" % __version__,
            markup=True, size_hint_y=None, height=dp(30), color=ORANGE))

        barre = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(4))
        self.tabs = []
        for i, nom in enumerate(self.ONGLETS):
            b = Bouton(text=nom, font_size=dp(12), rayon=6)
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

        self.ec_slots = EcranSlots(self.journal)
        self.ecrans = [
            EcranTraitement(self.journal),
            self.ec_slots,
            EcranEditeur(self.journal, lambda: self.ec_slots),
            EcranTuto(),
        ]
        self.afficher(0)

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
    title = "Volca Gain"

    def build(self):
        Window.clearcolor = FOND
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
