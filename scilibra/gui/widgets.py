"""Small widget building blocks for the Material-style look: hover tracking and rounded text fields.

Importing this module registers the classes with Kivy's Factory, so layout.kv can use them.
"""

from __future__ import annotations

import weakref

from kivy.core.window import Window
from kivy.factory import Factory
from kivy.graphics import Color, InstructionGroup, Line, RoundedRectangle
from kivy.metrics import dp
from kivy.properties import BooleanProperty, ColorProperty, NumericProperty
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput

from . import theme

_hover_widgets = weakref.WeakSet()


def _visible(widget):
    """True when the widget and all its parents are shown and it is attached to the window."""
    w = widget
    while w is not None and w is not Window:
        if w.opacity == 0 or w.disabled:
            return False
        if w.parent is w:
            break
        w = w.parent
    return widget.get_root_window() is not None


def _on_mouse_pos(_window, pos):
    top = Window.children[0] if Window.children else None
    for widget in list(_hover_widgets):
        inside = False
        if widget.width > 0 and widget.height > 0 and _visible(widget):
            # only the top-most layer (an open dialog / menu, or the main screen) reacts to hover
            root = widget
            while root.parent is not None and root.parent is not Window and root.parent is not root:
                root = root.parent
            if top is None or root is top:
                inside = widget.collide_point(*widget.to_widget(*pos))
        if widget.hovered != inside:
            widget.hovered = inside


Window.bind(mouse_pos=_on_mouse_pos)


class HoverBehavior:
    """Mixin: `hovered` is True while the mouse pointer is over the widget."""
    hovered = BooleanProperty(False)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        _hover_widgets.add(self)


Factory.register("HoverBehavior", cls=HoverBehavior)


class HoverButton(HoverBehavior, Button):
    """Pill button with a `hovered` state; its look comes from the `<FlatButton>` rule in layout.kv."""
    bg = ColorProperty(theme.BUTTON)       # fill colour
    fg = ColorProperty(theme.TEXT)         # text colour
    radius = NumericProperty(dp(19))       # corner radius (capped at half the height)
    elevation = NumericProperty(0)         # 0 = flat, 1 = soft shadow


class RoundedInput(TextInput):
    """Filled text field with rounded corners and an accent outline while focused."""
    fill = ColorProperty(theme.INPUT)
    radius = NumericProperty(dp(10))
    focus_color = ColorProperty(theme.ACCENT)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Draw below everything TextInput puts in canvas.before (cursor, selection), hence insert at 0.
        # The instructions go into a group built with add(): inserting a vertex instruction directly
        # puts its texture binding after it, so it would be drawn with a stale texture.
        self._fill_color = Color(*self.fill)
        self._fill = RoundedRectangle()
        self._line_color = Color(0, 0, 0, 0)
        self._line = Line(width=dp(1.2))
        group = InstructionGroup()
        for instruction in (self._fill_color, self._fill, self._line_color, self._line):
            group.add(instruction)
        self.canvas.before.insert(0, group)
        self.bind(pos=self._redraw, size=self._redraw, focus=self._redraw, fill=self._redraw,
                  radius=self._redraw, focus_color=self._redraw, disabled=self._redraw)
        self._redraw()

    def _redraw(self, *_):
        self._fill_color.rgba = theme.alpha(self.fill, self.fill[3] * (0.6 if self.disabled else 1))
        r = min(self.radius, self.height / 2)
        self._fill.pos, self._fill.size, self._fill.radius = self.pos, self.size, [r]
        self._line_color.rgba = self.focus_color if self.focus else (0, 0, 0, 0)
        self._line.rounded_rectangle = (self.x + dp(0.6), self.y + dp(0.6), max(0, self.width - dp(1.2)),
                                        max(0, self.height - dp(1.2)), r)


def style_file_entry(entry):
    """Recolour a FileChooserListView row (Kivy draws them for a dark background)."""
    entry.even_color = (0, 0, 0, 0)
    entry.odd_color = theme.alpha(theme.ROW, 1)
    entry.color_selected = theme.ROW_SELECTED
    for child in entry.walk(restrict=True):
        if hasattr(child, "color") and child is not entry and child.__class__.__name__ == "Label":
            child.color = theme.TEXT


def style_file_chooser(chooser):
    for child in chooser.walk(restrict=True):
        if child.__class__.__name__ == "Label":
            child.color = theme.MUTED
