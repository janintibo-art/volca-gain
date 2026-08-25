#!/usr/bin/env python3
"""
Volca Gain - interface graphique (Kivy).
Meme code pour le .exe Windows et l'APK Android.

Deux ecrans :
  TRAITEMENT : analyse et traitement d'un dossier de samples
  SLOTS      : les 100 slots de la volca, comme le librarian, + envoi direct

Sans Kivy : utiliser cli.py (aucune dependance).
"""

import os
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
from kivy.uix.textinput import TextInput

from volca import __version__, audio, batch, project, syro

BG = (0.07, 0.07, 0.09, 1)
ORANGE = (0.94, 0.35, 0.10, 1)
GRIS = (0.22, 0.22, 0.25, 1)
VERT = (0.15, 0.55, 0.30, 1)

IS_ANDROID = "ANDROID_ARGUMENT" in os.environ


def default_dir():
    if IS_ANDROID:
        for p in ("/storage/emulated/0/Download", "/sdcard/Download", "/sdcard"):
            if os.path.isdir(p):
                return p
    return os.path.expanduser("~")


def dossier_travail():
    if IS_ANDROID:
        p = os.environ.get("ANDROID_PRIVATE") or default_dir()
        return p
    return os.getcwd()


# --------------------------------------------------------------------------
class Chooser(Popup):
    def __init__(self, callback, dossiers=False, filtres=None, start=None, **kw):
        super().__init__(title="Choisir un dossier" if dossiers else "Choisir un fichier",
                         size_hint=(0.95, 0.9), **kw)
        self.callback = callback
        self.dossiers = dossiers
        box = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(6))
        self.chooser = FileChooserListView(
            path=start or default_dir(), dirselect=dossiers,
            filters=filtres or ["*"])
        box.add_widget(self.chooser)
        row = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(6))
        b_no = Button(text="Annuler")
        b_no.bind(on_release=lambda *_: self.dismiss())
        b_ok = Button(text="Choisir", background_color=ORANGE)
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


class SlotPopup(Popup):
    """Editer un slot : assigner un WAV, choisir preset et gain, vider."""

    def __init__(self, ecran, index, **kw):
        self.ecran = ecran
        self.index = index
        slot = ecran.projet.slots[index]
        super().__init__(title="Slot %02d" % index, size_hint=(0.9, None),
                         height=dp(330), **kw)

        box = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(10))
        self.lbl = Label(text=slot.nom or "(vide)", size_hint_y=None,
                         height=dp(28), shorten=True)
        box.add_widget(self.lbl)
        self.lbl_dur = Label(
            text=("%.0f ms" % slot.duree_ms) if not slot.vide else "",
            size_hint_y=None, height=dp(22), font_size=dp(11),
            color=(0.7, 0.7, 0.7, 1))
        box.add_widget(self.lbl_dur)

        b = Button(text="Choisir un WAV", size_hint_y=None, height=dp(46),
                   background_color=ORANGE)
        b.bind(on_release=lambda *_: Chooser(
            self._assigner, filtres=["*.wav", "*.WAV"]).open())
        box.add_widget(b)

        r1 = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        r1.add_widget(Label(text="Preset", size_hint_x=0.35))
        self.spin = Spinner(text=slot.preset, values=sorted(audio.PRESETS))
        r1.add_widget(self.spin)
        box.add_widget(r1)

        r2 = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        self.lbl_gain = Label(text="Gain %+.1f dB" % slot.gain_db,
                              size_hint_x=0.45)
        r2.add_widget(self.lbl_gain)
        self.sl = Slider(min=-12, max=12, value=slot.gain_db, step=0.5)
        self.sl.bind(value=lambda _i, v: setattr(
            self.lbl_gain, "text", "Gain %+.1f dB" % v))
        r2.add_widget(self.sl)
        box.add_widget(r2)

        r3 = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(6))
        b_vider = Button(text="Vider")
        b_vider.bind(on_release=self._vider)
        r3.add_widget(b_vider)
        b_ok = Button(text="Valider", background_color=VERT)
        b_ok.bind(on_release=self._valider)
        r3.add_widget(b_ok)
        box.add_widget(r3)
        self.add_widget(box)

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

        b = Button(text="Choisir le dossier de samples", size_hint_y=None,
                   height=dp(50), background_color=ORANGE)
        b.bind(on_release=lambda *_: Chooser(self._set_src, dossiers=True).open())
        self.add_widget(b)

        self.lbl_src = Label(text="(aucun dossier)", size_hint_y=None,
                             height=dp(26), font_size=dp(12), shorten=True)
        self.add_widget(self.lbl_src)

        row = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6))
        row.add_widget(Label(text="Preset", size_hint_x=0.3))
        self.spin = Spinner(text="punch", values=sorted(audio.PRESETS))
        self.spin.bind(text=lambda _i, v: setattr(
            self.lbl_desc, "text", audio.PRESETS[v]["desc"]))
        row.add_widget(self.spin)
        self.add_widget(row)

        self.lbl_desc = Label(text=audio.PRESETS["punch"]["desc"],
                              size_hint_y=None, height=dp(24), font_size=dp(11),
                              color=(0.7, 0.7, 0.7, 1))
        self.add_widget(self.lbl_desc)

        row2 = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6))
        self.lbl_gain = Label(text="Gain +0.0 dB", size_hint_x=0.4)
        row2.add_widget(self.lbl_gain)
        self.sl = Slider(min=-12, max=12, value=0, step=0.5)
        self.sl.bind(value=lambda _i, v: setattr(
            self.lbl_gain, "text", "Gain %+.1f dB" % v))
        row2.add_widget(self.sl)
        self.add_widget(row2)

        row3 = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(6))
        self.b_ana = Button(text="Analyser")
        self.b_ana.bind(on_release=lambda *_: self.lancer(True))
        row3.add_widget(self.b_ana)
        self.b_go = Button(text="TRAITER", background_color=ORANGE)
        self.b_go.bind(on_release=lambda *_: self.lancer(False))
        row3.add_widget(self.b_go)
        self.add_widget(row3)

        self.pb = ProgressBar(max=1, value=0, size_hint_y=None, height=dp(14))
        self.add_widget(self.pb)
        self.add_widget(BoxLayout())  # espaceur

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
                        info = audio.read_wav(p).info()
                        self.journal("%-20s crete %6.1f  RMS %6.1f%s" % (
                            os.path.basename(p)[:20], info["peak_db"],
                            info["rms_db"],
                            "  <- faible" if info["rms_db"] < -20 else ""))
                    except Exception as e:  # noqa: BLE001
                        self.journal("%s : %s" % (os.path.basename(p), e))
                    self._pb(i + 1, len(fichiers))
                return

            dst = os.path.join(self.src, "volca_out")
            self.journal("--- TRAITEMENT (%s) ---" % self.spin.text)

            def prog(i, n, rap):
                self._pb(i, n)
                self.journal("%-20s %s" % (
                    rap["fichier"][:20],
                    ("%+.1f dB" % rap["gain_db"]) if rap.get("ok")
                    else "ECHEC " + rap["erreur"]))

            raps = batch.process_folder(self.src, dst, self.spin.text,
                                        self.sl.value, prog)
            ok = sum(1 for r in raps if r.get("ok"))
            self.journal("%d fichier(s) ecrit(s) dans %s" % (ok, dst))
            self.journal("Va dans SLOTS pour les envoyer a la volca.")
        except Exception as e:  # noqa: BLE001
            self.journal("ERREUR : %s" % e)
        finally:
            self._fin()


# --------------------------------------------------------------------------
class EcranSlots(BoxLayout):
    def __init__(self, journal, **kw):
        super().__init__(orientation="vertical", spacing=dp(6), **kw)
        self.journal = journal
        self.projet = project.Projet("mon_kit")
        self.busy = False
        self.dernier_flux = None

        self.lbl_mem = Label(text="", size_hint_y=None, height=dp(24),
                             font_size=dp(12))
        self.add_widget(self.lbl_mem)
        self.bar = ProgressBar(max=100, value=0, size_hint_y=None,
                               height=dp(12))
        self.add_widget(self.bar)

        sv = ScrollView(size_hint_y=0.55)
        self.grille = GridLayout(cols=10, spacing=dp(2), size_hint_y=None)
        self.grille.bind(minimum_height=self.grille.setter("height"))
        self.boutons = []
        for i in range(project.NB_SLOTS):
            b = Button(text="%02d" % i, font_size=dp(11), size_hint_y=None,
                       height=dp(38), background_color=GRIS)
            b.bind(on_release=lambda w, idx=i: SlotPopup(self, idx).open())
            self.boutons.append(b)
            self.grille.add_widget(b)
        sv.add_widget(self.grille)
        self.add_widget(sv)

        r0 = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        b_rem = Button(text="Remplir depuis un dossier")
        b_rem.bind(on_release=lambda *_: Chooser(
            self._remplir, dossiers=True).open())
        r0.add_widget(b_rem)
        self.add_widget(r0)

        r1 = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        b_s = Button(text="Sauver projet")
        b_s.bind(on_release=self._sauver)
        r1.add_widget(b_s)
        b_c = Button(text="Ouvrir projet")
        b_c.bind(on_release=lambda *_: Chooser(
            self._charger, filtres=["*.json"]).open())
        r1.add_widget(b_c)
        self.add_widget(r1)

        r2 = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        r2.add_widget(Label(text="Qualite", size_hint_x=0.35, font_size=dp(12)))
        self.spin_q = Spinner(text="16", values=[str(i) for i in range(16, 7, -1)])
        r2.add_widget(self.spin_q)
        self.add_widget(r2)

        r3 = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(6))
        self.b_env = Button(text="ENVOYER", background_color=ORANGE)
        self.b_env.bind(on_release=lambda *_: self.envoyer())
        r3.add_widget(self.b_env)
        self.b_play = Button(text="Rejouer le flux")
        self.b_play.bind(on_release=lambda *_: self.rejouer())
        r3.add_widget(self.b_play)
        self.add_widget(r3)

        self.lbl_syro = Label(text="", size_hint_y=None, height=dp(22),
                              font_size=dp(11), color=(0.7, 0.7, 0.7, 1))
        self.add_widget(self.lbl_syro)

        self.rafraichir()
        Clock.schedule_once(lambda *_: self.maj_syro(), 0.3)

    # ------------------------------------------------------------- etat
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
            b.background_color = ORANGE if not slot.vide else GRIS
            b.text = ("%02d\n%s" % (i, slot.nom[:6])) if not slot.vide else "%02d" % i
            b.halign = "center"
        pct = p.memoire_pct()
        self.bar.value = min(pct, 100)
        self.lbl_mem.text = "%d/%d slots - %.1f s / %.0f s (%.0f %%)%s" % (
            len(p.occupes()), project.NB_SLOTS, p.memoire_utilisee_s(),
            p.memoire_totale_s(), pct,
            "  MEMOIRE DEPASSEE" if p.depassement() else "")

    def _remplir(self, dossier):
        places = self.projet.remplir_depuis_dossier(dossier)
        self.journal("%d sample(s) place(s) depuis %s" % (len(places), dossier))
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

    # ------------------------------------------------------------- envoi
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
            self.journal("ATTENTION : memoire depassee, la volca refusera "
                         "peut-etre une partie.")
        self.busy = True
        self.b_env.disabled = True
        threading.Thread(target=self._worker_envoi, daemon=True).start()

    def _worker_envoi(self):
        import tempfile
        try:
            self.journal("--- PREPARATION ---")
            d = tempfile.mkdtemp(prefix="volcagain_")
            prepares = []
            occ = self.projet.occupes()
            for n, slot in enumerate(occ, 1):
                s = audio.read_wav(slot.chemin)
                s, _ = audio.process(s, slot.preset, slot.gain_db)
                out = os.path.join(d, "%02d.wav" % slot.index)
                audio.write_wav(out, s)
                prepares.append((slot.index, out))
                self.journal("[%d/%d] slot %02d %s" % (n, len(occ),
                                                       slot.index, slot.nom[:16]))

            cible = os.path.join(dossier_travail(), "transfert.wav")
            res = syro.build_stream(prepares, cible,
                                    quality=int(self.spin_q.text))
            self.dernier_flux = res["chemin"]
            self.journal("Flux pret : %.1f s" % res["duree_s"])
            self.journal("Branche la sortie casque sur SYNC IN, volume a fond.")
            self.journal("Lecture en cours, ne touche a rien...")
            syro.jouer(res["chemin"])
        except syro.SyroIndisponible as e:
            self.journal("Envoi direct indisponible : %s" % e)
        except Exception as e:  # noqa: BLE001
            self.journal("ERREUR : %s" % e)
        finally:
            self._fin()

    def rejouer(self):
        if not self.dernier_flux:
            self.journal("Aucun flux genere pour l'instant.")
            return
        try:
            syro.jouer(self.dernier_flux)
            self.journal("Relecture du flux...")
        except Exception as e:  # noqa: BLE001
            self.journal("Lecture impossible : %s" % e)


# --------------------------------------------------------------------------
class Root(BoxLayout):
    def __init__(self, **kw):
        super().__init__(orientation="vertical", spacing=dp(6),
                         padding=dp(10), **kw)

        self.add_widget(Label(
            text="[b]VOLCA GAIN[/b]  v%s" % __version__, markup=True,
            size_hint_y=None, height=dp(32), color=ORANGE))

        onglets = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(4))
        self.b1 = Button(text="TRAITEMENT", background_color=ORANGE)
        self.b1.bind(on_release=lambda *_: self.afficher(0))
        self.b2 = Button(text="SLOTS", background_color=GRIS)
        self.b2.bind(on_release=lambda *_: self.afficher(1))
        onglets.add_widget(self.b1)
        onglets.add_widget(self.b2)
        self.add_widget(onglets)

        self.zone = BoxLayout()
        self.add_widget(self.zone)

        sv = ScrollView(size_hint_y=0.3)
        self.log = Label(text="Pret.\n", size_hint_y=None, halign="left",
                         valign="top", font_size=dp(11))
        self.log.bind(texture_size=lambda i, v: setattr(i, "height", v[1]),
                      width=lambda i, v: setattr(i, "text_size", (v, None)))
        sv.add_widget(self.log)
        self.add_widget(sv)

        self.ecrans = [EcranTraitement(self.journal),
                       EcranSlots(self.journal)]
        self.afficher(0)

    @mainthread
    def journal(self, txt):
        self.log.text += txt + "\n"

    def afficher(self, i):
        self.zone.clear_widgets()
        self.zone.add_widget(self.ecrans[i])
        self.b1.background_color = ORANGE if i == 0 else GRIS
        self.b2.background_color = ORANGE if i == 1 else GRIS


class VolcaGainApp(App):
    title = "Volca Gain"

    def build(self):
        Window.clearcolor = BG
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
