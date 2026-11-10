#!/usr/bin/env python3
"""Драйвери: проверка, търсене и инсталиране на драйвери за Debian.
   ./drv-marka.py                   прозорец
   ./drv-marka.py --text            проверка в терминала
   ./drv-marka.py --text --search   и търсене на драйвери за устройствата
   ./drv-marka.py --fix             търси и инсталира (пита преди всяко нещо)
   ./drv-marka.py --kernel          кое ядро работи и инсталиране на по-ново (по избор)
   ./drv-marka.py --reset           връща всичко, направено от програмата (като фабрично)
Проверката само чете. Нещо се променя само след „Поправи“ и паролата (pkexec)."""
import os
import subprocess
import sys
import threading

HERE = os.path.dirname(os.path.realpath(__file__))   # realpath: командата drv-marka е символна връзка
sys.path.insert(0, HERE)
import jezgro

HELPER = os.path.join(HERE, "popravi.py")


def main_text(deep):
    print(jezgro.as_text(jezgro.collect(deep=deep)), end="")


def main_fix():
    r = jezgro.collect(lambda s: print(s), deep=True)
    if not r.fixes:
        print("Няма какво да се инсталира.")
        return
    chosen = []
    for f in r.fixes:
        d = "Д/н" if f.default else "д/Н"
        a = input(f"{f.title}\n  {f.detail}\n  Да го направя ли? [{d}] ").strip().lower()
        if a in ("д", "да", "y", "yes") or (a == "" and f.default):
            chosen.append(f)
    if chosen:
        sys.exit(subprocess.run(jezgro.fix_command(chosen, HELPER)).returncode)


def main_kernel():
    k = jezgro.kernels()
    print(f"Сега работи ядро {k.running}. Инсталирани: {', '.join(k.installed)}")
    if not k.options:
        print("Няма по-ново ядро за този компютър.")
        return
    for f in k.options:
        a = input(f"{f.title}\n  {f.detail}\n  Да го инсталирам ли? [д/Н] ").strip().lower()
        if a in ("д", "да", "y", "yes"):
            sys.exit(subprocess.run(jezgro.fix_command([f], HELPER)).returncode)


def main_reset():
    h = jezgro.history()
    if not h:
        print("Програмата не е променяла нищо. Няма какво да връщам.")
        return
    pk = sorted({p for e in h for p in e.get("packages", [])})
    print("Ще махна пакетите, сложени от програмата:", " ".join(pk) or "няма")
    print("Ще върна старите извори на apt и групите на потребителя.")
    if input("Да продължа ли? [д/Н] ").strip().lower() in ("д", "да", "y", "yes"):
        sys.exit(subprocess.run(jezgro.reset_command(HELPER)).returncode)


def main_gui():
    try:
        import gi
        gi.require_version("Gtk", "4.0")
        gi.require_version("Gdk", "4.0")
        from gi.repository import Gdk, Gio, GLib, Gtk, Pango
    except (ImportError, ValueError):
        print("Липсва GTK 4 за прозореца. Инсталирай го с:\n  sudo apt install python3-gi gir1.2-gtk-4.0\n"
              "Дотогава работи в терминала: drv-marka.py --text --search  или  drv-marka.py --fix\n")
        main_text(False)
        return

    CSS = b"""
    .ok { color: #1b7f3b; } .warn { color: #b3261e; } .info { color: alpha(currentColor, .6); }
    .verdict { font-size: 18pt; font-weight: bold; padding: 8px 16px 0 16px; }
    .sub { padding: 0 16px 8px 16px; opacity: .7; }
    .name { font-weight: bold; }
    .small { font-size: 90%; opacity: .75; }
    .log { font-family: monospace; font-size: 90%; }
    row { padding: 6px 12px; }
    """

    class FixWin(Gtk.Window):
        """Отметки какво да се направи, после изходът от apt."""
        def __init__(self, parent, fixes, on_done, reset=None, head=None, title=None):
            super().__init__(transient_for=parent, modal=True, title=title or ("Върни както беше" if reset else "Поправи"), default_width=640, default_height=520)
            self.on_done, self.fixes, self.reset = on_done, fixes, reset
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_top=12, margin_bottom=12, margin_start=12, margin_end=12)
            self.set_child(box)
            head = reset or head or "Избери какво да направя. Ще поискам паролата ти."
            box.append(Gtk.Label(label=head, xalign=0, css_classes=["name"], wrap=True))
            lb = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
            self.checks = []
            for f in ([] if reset else fixes):
                c = Gtk.CheckButton(active=f.default)
                v = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
                v.append(Gtk.Label(label=f.title, xalign=0, css_classes=["name"], wrap=True))
                v.append(Gtk.Label(label=f.detail, xalign=0, css_classes=["small", "warn"] if f.removes else ["small"], wrap=True))
                c.set_child(v)
                self.checks.append(c)
                lb.append(c)
            self.top = Gtk.ScrolledWindow(child=lb, vexpand=True)
            box.append(self.top)
            self.buf = Gtk.TextBuffer()
            self.view = Gtk.TextView(buffer=self.buf, editable=False, monospace=True, css_classes=["log"], wrap_mode=Gtk.WrapMode.WORD_CHAR)
            self.logsw = Gtk.ScrolledWindow(child=self.view, vexpand=True, visible=False)
            box.append(self.logsw)
            bar = Gtk.Box(spacing=8, halign=Gtk.Align.END)
            self.close_b = Gtk.Button(label="Затвори")
            self.close_b.connect("clicked", lambda *_: self.close())
            self.go = Gtk.Button(label="Върни" if reset else "Инсталирай" if title else "Поправи", css_classes=["destructive-action" if reset else "suggested-action"])
            self.go.connect("clicked", self.start)
            bar.append(self.close_b)
            bar.append(self.go)
            self.go.set_visible(bool(fixes) or bool(reset))
            box.append(bar)
            self.connect("close-request", self.closing)
            self.ran = False

        def add(self, s):
            self.buf.insert(self.buf.get_end_iter(), s)
            self.view.scroll_to_mark(self.buf.get_insert(), 0, False, 0, 1)
            return False

        def start(self, *_):
            chosen = [f for f, c in zip(self.fixes, self.checks) if c.get_active()]
            if not chosen and not self.reset:
                return
            self.ran = True
            self.go.set_sensitive(False)
            self.close_b.set_sensitive(False)
            self.top.set_visible(False)
            self.logsw.set_visible(True)
            cmd = jezgro.reset_command(HELPER) if self.reset else jezgro.fix_command(chosen, HELPER)

            def work():
                try:
                    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace", bufsize=1)
                    for line in p.stdout:
                        GLib.idle_add(self.add, line)
                    code = p.wait()
                except OSError as e:
                    GLib.idle_add(self.add, f"{e}\n")
                    code = 1
                msg = {0: "", 126: "\nОтказано: паролата не беше въведена.\n", 127: "\nОтказано: паролата не беше въведена.\n"}.get(code, f"\nСпря с грешка (код {code}).\n")
                GLib.idle_add(self.add, msg)
                GLib.idle_add(self.close_b.set_sensitive, True)
            threading.Thread(target=work, daemon=True).start()

        def closing(self, *_):
            if self.ran:
                self.on_done()
            return False

    class Win(Gtk.ApplicationWindow):
        def __init__(self, app):
            super().__init__(application=app, title="Драйвери (drv-marka)", default_width=860, default_height=700)
            self.report, self.deep = None, False
            head = Gtk.HeaderBar()
            self.set_titlebar(head)
            self.btn = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text="Провери отново")
            self.btn.connect("clicked", lambda *_: self.load(self.deep))
            head.pack_start(self.btn)
            self.find_b = Gtk.Button(label="Намери драйвери", tooltip_text="Търси драйвери и пакети за всяко устройство")
            self.find_b.connect("clicked", lambda *_: self.load(True))
            head.pack_start(self.find_b)
            self.kern_b = Gtk.Button(label="Ядро Linux", tooltip_text="Кое ядро работи и има ли по-ново")
            self.kern_b.connect("clicked", self.kernel)
            head.pack_start(self.kern_b)
            copy = Gtk.Button(icon_name="edit-copy-symbolic", tooltip_text="Копирай всичко като текст")
            copy.connect("clicked", self.copy)
            head.pack_end(copy)
            self.fix_b = Gtk.Button(label="Поправи…", css_classes=["suggested-action"], sensitive=False)
            self.fix_b.connect("clicked", self.fix)
            head.pack_end(self.fix_b)
            self.reset_b = Gtk.Button(icon_name="edit-undo-symbolic", tooltip_text="Върни както беше: маха всичко, сложено от програмата", sensitive=False)
            self.reset_b.connect("clicked", self.undo)
            head.pack_end(self.reset_b)
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            self.set_child(box)
            self.title_l = Gtk.Label(xalign=0, css_classes=["verdict"], label="Проверявам…", wrap=True)
            self.sub_l = Gtk.Label(xalign=0, css_classes=["sub"], wrap=True)
            box.append(self.title_l)
            box.append(self.sub_l)
            self.search = Gtk.SearchEntry(placeholder_text="Търси драйвер или устройство", margin_start=12, margin_end=12, margin_bottom=8)
            self.search.connect("search-changed", lambda *_: self.fill())
            box.append(self.search)
            sw = Gtk.StackSwitcher(halign=Gtk.Align.CENTER, margin_bottom=6)
            self.stack = Gtk.Stack(vexpand=True)
            sw.set_stack(self.stack)
            box.append(sw)
            box.append(self.stack)
            self.lists = {}
            for key, title in (("check", "Проверка"), ("dev", "Устройства"), ("mod", "Заредени драйвери"), ("pkg", "Фърмуер и пакети")):
                lb = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
                sc = Gtk.ScrolledWindow(child=lb)
                self.stack.add_titled(sc, key, title)
                self.lists[key] = lb
            self.load(False)

        def load(self, deep):
            self.deep = deep
            for b in (self.btn, self.find_b, self.fix_b, self.reset_b):
                b.set_sensitive(False)
            self.title_l.set_text("Търся драйвери…" if deep else "Проверявам…")
            self.title_l.remove_css_class("ok")
            self.title_l.remove_css_class("warn")

            def work():
                r = jezgro.collect(lambda s: GLib.idle_add(self.sub_l.set_text, s), deep=deep)
                GLib.idle_add(self.done, r)
            threading.Thread(target=work, daemon=True).start()

        def done(self, r):
            self.report = r
            lvl, text = jezgro.verdict(r)
            self.title_l.set_text(text)
            self.title_l.add_css_class(lvl if lvl != jezgro.INFO else "ok")
            how = "Търсенето е направено." if r.deep else "За по-задълбочено търсене натисни „Намери драйвери“."
            self.sub_l.set_text(f"{r.system}, ядро {r.kernel}. {how}")
            self.btn.set_sensitive(True)
            self.find_b.set_sensitive(True)
            self.fix_b.set_sensitive(bool(r.fixes))
            self.fix_b.set_label(f"Поправи ({len(r.fixes)})…" if r.fixes else "Поправи…")
            self.reset_b.set_sensitive(bool(r.history))
            self.fill()
            return False

        def row(self, lb, level, title, sub="", right=""):
            mark = {jezgro.OK: "✓", jezgro.WARN: "!", jezgro.INFO: "•"}[level]
            h = Gtk.Box(spacing=12)
            h.append(Gtk.Label(label=mark, css_classes=[level, "name"], valign=Gtk.Align.START))
            v = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
            v.append(Gtk.Label(label=title, xalign=0, css_classes=["name"], wrap=True, selectable=True))
            if sub:
                v.append(Gtk.Label(label=sub, xalign=0, css_classes=["small"], wrap=True, selectable=True))
            h.append(v)
            if right:
                h.append(Gtk.Label(label=right, css_classes=["small"], valign=Gtk.Align.START, selectable=True, ellipsize=Pango.EllipsizeMode.END, max_width_chars=26))
            lb.append(h)

        def fill(self):
            r = self.report
            if not r:
                return
            q = self.search.get_text().strip().lower()
            hit = lambda *a: not q or q in " ".join(a).lower()
            for lb in self.lists.values():
                while (c := lb.get_first_child()):
                    lb.remove(c)
            lc = self.lists["check"]
            for f in r.findings:
                if hit(f.title, f.detail, f.package):
                    self.row(lc, f.level, f.title, f.detail)
            for x in r.limits:
                if hit(x):
                    self.row(lc, jezgro.INFO, "Не беше проверено", x)
            if lc.get_first_child() is None and not q:
                self.row(lc, jezgro.OK, "Няма какво да се прави", "Не намерих липсващи драйвери или фърмуер.")
            for d in sorted(r.devices, key=lambda d: ({jezgro.WARN: 0, jezgro.OK: 1, jezgro.INFO: 2}[d.state], d.bus, d.kind)):
                if hit(d.name, d.kind, d.driver, d.bus):
                    self.row(self.lists["dev"], d.state, d.name, f"{d.bus} · {d.kind}" + (f"\n{d.note}" if d.note else ""), d.driver or "без драйвер")
            for m in r.modules:
                if hit(m.name, m.description):
                    self.row(self.lists["mod"], jezgro.OK, m.name, m.description, f"{m.size_kb} KB")
            for p in r.packages:
                if hit(p.name, p.summary):
                    self.row(self.lists["pkg"], jezgro.OK, p.name, p.summary, p.version)

        def fix(self, *_):
            if self.report and self.report.fixes:
                FixWin(self, self.report.fixes, lambda: self.load(self.deep)).present()

        def kernel(self, *_):
            self.kern_b.set_sensitive(False)

            def work():
                k = jezgro.kernels()
                GLib.idle_add(show, k)

            def show(k):
                self.kern_b.set_sensitive(True)
                inst = "\n".join(f"  • {v}" + ("  ← работи сега" if v == k.running else "") for v in k.installed)
                text = f"Сега работи ядро {k.running}.\nИнсталирани:\n{inst}\n\n"
                text += ("Може да се сложи (не е отметнато, избери само ако имаш нужда, например нов хардуер без драйвер):"
                         if k.options else "Няма по-ново ядро за този компютър.")
                FixWin(self, k.options, lambda: self.load(self.deep), head=text, title="Ядро Linux").present()
                return False
            threading.Thread(target=work, daemon=True).start()

        def undo(self, *_):
            h = self.report.history if self.report else []
            if not h:
                return
            pk = sorted({p for e in h for p in e.get("packages", [])})
            text = ("Ще махна всичко, сложено от програмата, и ще върна старите извори на apt.\n\n"
                    f"Пакети ({len(pk)}): {', '.join(pk) or 'няма'}\n\nПосле рестартирай компютъра.")
            FixWin(self, [], lambda: self.load(self.deep), reset=text).present()

        def copy(self, *_):
            if self.report:
                self.get_clipboard().set(jezgro.as_text(self.report))
                self.sub_l.set_text("Копирано.")

    def activate(app):
        p = Gtk.CssProvider()
        p.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(), p, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        Win(app).present()

    app = Gtk.Application(application_id="com.palamarka.drvmarka", flags=Gio.ApplicationFlags.FLAGS_NONE)
    app.connect("activate", activate)
    app.run([sys.argv[0]])


if __name__ == "__main__":
    if "--version" in sys.argv:
        print("drv-marka", jezgro.VERSION)
    elif "--fix" in sys.argv:
        main_fix()
    elif "--reset" in sys.argv:
        main_reset()
    elif "--kernel" in sys.argv:
        main_kernel()
    elif "--text" in sys.argv:
        main_text("--search" in sys.argv)
    else:
        main_gui()
