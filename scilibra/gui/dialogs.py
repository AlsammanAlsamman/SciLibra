"""Reusable popups: messages, confirmations, file choosers, progress, text entry and value picking."""

from __future__ import annotations

import os

from kivy.clock import Clock
from kivy.core.clipboard import Clipboard
from kivy.properties import BooleanProperty, ListProperty, NumericProperty, ObjectProperty, StringProperty
from kivy.uix.popup import Popup
from kivy.uix.recycleview.views import RecycleDataViewBehavior
from kivy.uix.boxlayout import BoxLayout


class Collapsible(BoxLayout):
    """A container that can be hidden. While hidden it ignores all clicks, so that nothing inside it can
    swallow clicks meant for the widgets that are visible in its place."""
    shown = BooleanProperty(True)

    def on_touch_down(self, touch):
        return super().on_touch_down(touch) if self.shown else False

    def on_touch_move(self, touch):
        return super().on_touch_move(touch) if self.shown else False

    def on_touch_up(self, touch):
        return super().on_touch_up(touch) if self.shown else False


class BasePopup(Popup):
    """Popup styled by the `<BasePopup>` rule in layout.kv."""

    def __init__(self, **kwargs):
        kwargs.setdefault("auto_dismiss", True)
        super().__init__(**kwargs)

    # Open and close instantly: the fade animation only delays the next dialog.
    def open(self, *args, **kwargs):
        kwargs.setdefault("animation", False)
        return super().open(*args, **kwargs)

    def dismiss(self, *args, **kwargs):
        kwargs.setdefault("animation", False)
        return super().dismiss(*args, **kwargs)


class MessageDialog(BasePopup):
    message = StringProperty("")

    def copy(self):
        try:
            Clipboard.copy(self.message)
        except Exception:
            pass


class ConfirmDialog(BasePopup):
    message = StringProperty("")
    confirm_text = StringProperty("OK")
    danger = BooleanProperty(False)
    action = ObjectProperty(None, allownone=True)  # called when confirmed

    def confirm(self):
        self.dismiss()
        if self.action:
            self.action()


class TextDialog(BasePopup):
    """Multi-line text entry (e.g. paste BibTeX)."""
    hint = StringProperty("")
    text = StringProperty("")
    confirm_text = StringProperty("OK")
    info = StringProperty("")
    action = ObjectProperty(None, allownone=True)  # action(text); returning False keeps the dialog open

    def confirm(self):
        if self.action and self.action(self.ids.input.text) is False:
            return  # callback asked to keep the dialog open
        self.dismiss()


class ProgressDialog(BasePopup):
    message = StringProperty("")
    value = NumericProperty(0)
    maximum = NumericProperty(1)
    cancelled = BooleanProperty(False)

    def __init__(self, **kwargs):
        kwargs.setdefault("auto_dismiss", False)
        super().__init__(**kwargs)

    def update(self, value, maximum=None, message=None):
        def apply(_dt):
            if maximum is not None:
                self.maximum = max(maximum, 1)
            self.value = value
            if message is not None:
                self.message = message
        Clock.schedule_once(apply)


class FileDialog(BasePopup):
    """File / folder chooser.

    mode: "open" (one or more files), "folder" (choose a folder) or "save" (folder + file name).
    """
    mode = StringProperty("open")
    path = StringProperty(os.path.expanduser("~"))
    filters = ListProperty([])
    multiselect = BooleanProperty(False)
    filename = StringProperty("")
    confirm_text = StringProperty("Open")
    callback = ObjectProperty(None, allownone=True)  # callback(result, current_folder)
    error = StringProperty("")

    def go_to(self, path):
        path = os.path.expanduser(path.strip())
        if os.path.isfile(path):
            path = os.path.dirname(path)
        if os.path.isdir(path):
            self.ids.chooser.path = path
            self.error = ""
        else:
            self.error = "Folder not found"

    def go_up(self):
        self.go_to(os.path.dirname(self.ids.chooser.path.rstrip(os.sep)) or os.sep)

    def confirm(self):
        chooser = self.ids.chooser
        if self.mode == "open":
            files = [f for f in chooser.selection if os.path.isfile(f)]
            if not files:
                self.error = "Select a file first"
                return
            result = files if self.multiselect else files[0]
        elif self.mode == "folder":
            chosen = [f for f in chooser.selection if os.path.isdir(f)]
            result = chosen[0] if chosen else chooser.path
        else:
            name = self.ids.filename.text.strip()
            if not name or any(c in name for c in '<>:"/\\|?*'):
                self.error = "Enter a valid file name"
                return
            result = os.path.join(chooser.path, name)
        self.dismiss()
        if self.callback:
            self.callback(result, chooser.path)


class PickRow(RecycleDataViewBehavior, BoxLayout):
    text = StringProperty("")
    count = NumericProperty(0)
    checked = BooleanProperty(False)
    index = None

    def refresh_view_attrs(self, rv, index, data):
        self.index = index
        return super().refresh_view_attrs(rv, index, data)

    def toggle(self):
        widget = self.parent
        while widget is not None and not isinstance(widget, ValuePicker):
            widget = widget.parent
        if widget is not None:
            widget.toggle(self.text)


class ValuePicker(BasePopup):
    """Choose any number of existing values (keywords, tag groups...) or type new ones."""
    values = ListProperty([])       # [(value, count)]
    selected = ListProperty([])
    callback = ObjectProperty(None, allownone=True)  # callback(selected_values)

    def on_open(self):
        self.refresh()

    def toggle(self, value):
        if value in self.selected:
            self.selected.remove(value)
        else:
            self.selected.append(value)
        self.refresh()

    def add_new(self, text):
        for value in [v.strip() for v in text.replace(";", ",").split(",") if v.strip()]:
            if value not in self.selected:
                self.selected.append(value)
        self.ids.new_value.text = ""
        self.refresh()

    def refresh(self, *_):
        needle = self.ids.filter.text.strip().lower()
        known = {v for v, _ in self.values}
        rows = [(v, 0) for v in self.selected if v not in known] + list(self.values)
        self.ids.rv.data = [{"text": v, "count": c, "checked": v in self.selected}
                            for v, c in rows if not needle or needle in v.lower()]

    def done(self):
        self.dismiss()
        if self.callback:
            self.callback(list(self.selected))
