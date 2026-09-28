"""Toolbar icons drawn with Kivy graphics (no icon font needed), in the style of office/PDF editors."""

from __future__ import annotations

from kivy.core.text.markup import MarkupLabel
from kivy.graphics import Color, Line, Mesh, Rectangle, RoundedRectangle
from kivy.metrics import dp, sp
from kivy.properties import BooleanProperty, ListProperty, StringProperty
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.widget import Widget

from . import theme

_text_cache = {}


def _text_texture(markup, size, bold=True):
    key = (markup, size, bold)
    if key not in _text_cache:
        label = MarkupLabel(text=markup, font_size=size, bold=bold, color=(1, 1, 1, 1))
        label.refresh()
        _text_cache[key] = label.texture
    return _text_cache[key]


def _glyph(canvas, markup, cx, cy, size, color, bold=True):
    tex = _text_texture(markup, size, bold)
    w, h = tex.size
    canvas.add(Color(*color))
    canvas.add(Rectangle(texture=tex, pos=(cx - w / 2, cy - h / 2), size=(w, h)))


def _polygon(canvas, points):
    """Filled convex polygon from [(x, y), ...]."""
    verts = []
    for x, y in points:
        verts += [x, y, 0, 0]
    canvas.add(Mesh(vertices=verts, indices=list(range(len(points))), mode="triangle_fan"))


def draw_icon(canvas, name, cx, cy, s, fg, accent):
    """Draw icon `name` centred on (cx, cy) in a box of size s. `accent` is the current annotation colour."""
    lw = dp(1.4)
    c = list(fg)
    a = list(accent[:3]) + [1]
    if name == "select":  # mouse cursor
        canvas.add(Color(*c))
        pts = [(cx - s * .22, cy + s * .34), (cx - s * .22, cy - s * .26), (cx - s * .06, cy - s * .1),
               (cx + s * .06, cy - s * .36), (cx + s * .14, cy - s * .32), (cx + s * .02, cy - s * .06),
               (cx + s * .22, cy - s * .06)]
        _polygon(canvas, [pts[0], pts[1], pts[2], pts[6]])
        _polygon(canvas, [pts[2], pts[3], pts[4], pts[5]])
    elif name == "text":  # I-beam text cursor
        canvas.add(Color(*c))
        canvas.add(Line(points=[cx, cy - s * .32, cx, cy + s * .32], width=lw))
        for y in (cy - s * .32, cy + s * .32):
            canvas.add(Line(points=[cx - s * .14, y, cx + s * .14, y], width=lw))
    elif name == "Highlight":  # "ab" on a coloured bar + marker
        canvas.add(Color(*a))
        canvas.add(Rectangle(pos=(cx - s * .36, cy - s * .38), size=(s * .72, s * .16)))
        _glyph(canvas, "ab", cx, cy + s * .08, sp(15), c)
    elif name == "Underline":
        _glyph(canvas, "[u]U[/u]", cx, cy, sp(17), c)
    elif name == "StrikeOut":
        _glyph(canvas, "[s]abc[/s]", cx, cy, sp(14), c)
    elif name == "note":  # speech bubble with lines
        canvas.add(Color(*c))
        canvas.add(Line(rounded_rectangle=(cx - s * .34, cy - s * .16, s * .68, s * .48, dp(3)), width=lw))
        canvas.add(Line(points=[cx - s * .16, cy - s * .16, cx - s * .24, cy - s * .36, cx - s * .02, cy - s * .16],
                        width=lw))
        for dy in (s * .16, s * .02):
            canvas.add(Line(points=[cx - s * .2, cy + dy, cx + s * .2, cy + dy], width=dp(1)))
    elif name == "textbox":  # T inside a box
        canvas.add(Color(*c))
        canvas.add(Line(rectangle=(cx - s * .34, cy - s * .3, s * .68, s * .6), width=dp(1.1)))
        _glyph(canvas, "T", cx, cy, sp(15), c)
    elif name == "draw":  # pen with a squiggle
        canvas.add(Color(*a))
        canvas.add(Line(bezier=[cx - s * .38, cy - s * .3, cx - s * .2, cy - s * .02, cx - s * .02, cy - s * .5,
                                cx + s * .12, cy - s * .26], width=lw))
        canvas.add(Color(*c))
        canvas.add(Line(points=[cx + s * .02, cy - s * .12, cx + s * .3, cy + s * .34], width=dp(3)))
        _polygon(canvas, [(cx - s * .02, cy - s * .2), (cx + s * .06, cy - s * .06), (cx - s * .03, cy - s * .08)])
    elif name == "Rectangle":
        canvas.add(Color(*c))
        canvas.add(Line(rectangle=(cx - s * .34, cy - s * .24, s * .68, s * .48), width=lw))
    elif name == "Ellipse":
        canvas.add(Color(*c))
        canvas.add(Line(ellipse=(cx - s * .36, cy - s * .26, s * .72, s * .52), width=lw))
    elif name == "Arrow":
        canvas.add(Color(*c))
        x0, y0, x1, y1 = cx - s * .32, cy - s * .3, cx + s * .3, cy + s * .3
        canvas.add(Line(points=[x0, y0, x1, y1], width=lw))
        _polygon(canvas, [(x1 + s * .04, y1 + s * .04), (x1 - s * .24, y1 - s * .02), (x1 - s * .02, y1 - s * .24)])
    elif name == "Line":
        canvas.add(Color(*c))
        canvas.add(Line(points=[cx - s * .32, cy - s * .3, cx + s * .32, cy + s * .3], width=lw))
    elif name == "shapes":  # square + circle overlapping
        canvas.add(Color(*c))
        canvas.add(Line(rectangle=(cx - s * .36, cy - s * .08, s * .4, s * .4), width=dp(1.2)))
        canvas.add(Line(ellipse=(cx - s * .08, cy - s * .36, s * .44, s * .44), width=dp(1.2)))
    elif name == "eraser":
        canvas.add(Color(*c))
        body = [(cx - s * .36, cy - s * .08), (cx - s * .02, cy + s * .3), (cx + s * .36, cy - s * .02),
                (cx + s * .02, cy - s * .36)]
        canvas.add(Line(points=[p for xy in body + body[:1] for p in xy], width=lw))
        _polygon(canvas, [body[0], (cx - s * .19, cy + s * .11), (cx + s * .17, cy - s * .21), body[3]])
        canvas.add(Line(points=[cx - s * .1, cy - s * .36, cx + s * .4, cy - s * .36], width=dp(1)))
    elif name == "undo":  # curved arrow
        canvas.add(Color(*c))
        canvas.add(Line(circle=(cx + s * .02, cy - s * .04, s * .26, -90, 150), width=lw))
        _polygon(canvas, [(cx - s * .34, cy + s * .1), (cx - s * .08, cy + s * .22), (cx - s * .3, cy + s * .36)])
    elif name == "color":  # letter A over the current colour
        _glyph(canvas, "A", cx, cy + s * .1, sp(16), c)
        canvas.add(Color(*a))
        canvas.add(Rectangle(pos=(cx - s * .36, cy - s * .38), size=(s * .72, s * .14)))
    elif name == "notes":  # list of notes
        canvas.add(Color(*c))
        for i, dy in enumerate((s * .24, 0, -s * .24)):
            canvas.add(Rectangle(pos=(cx - s * .36, cy + dy - s * .05), size=(s * .1, s * .1)))
            canvas.add(Line(points=[cx - s * .18, cy + dy, cx + s * .36, cy + dy], width=dp(1.2)))
    elif name == "contents":  # indented outline
        canvas.add(Color(*c))
        for x0, dy in ((cx - s * .36, s * .26), (cx - s * .2, s * .08), (cx - s * .2, -s * .1), (cx - s * .36, -s * .28)):
            canvas.add(Line(points=[x0, cy + dy, cx + s * .36, cy + dy], width=dp(1.2)))
    elif name == "night":  # crescent moon
        canvas.add(Color(*c))
        canvas.add(Line(circle=(cx, cy, s * .3, 200, 520), width=lw))
        canvas.add(Line(circle=(cx + s * .14, cy + s * .1, s * .24, 190, 400), width=lw))


class IconButton(ButtonBehavior, Widget):
    """Square toolbar button showing a drawn icon; `menu` adds a small ▾ marker for drop-down buttons."""
    icon = StringProperty("")
    hint = StringProperty("")         # shown in the status bar on hover
    active = BooleanProperty(False)
    menu = BooleanProperty(False)
    accent = ListProperty([1, 0.89, 0.2])
    hovered = BooleanProperty(False)

    def __init__(self, **kwargs):
        kwargs.setdefault("size_hint", (None, None))
        kwargs.setdefault("size", (dp(38), dp(34)))
        super().__init__(**kwargs)
        self.bind(pos=self.redraw, size=self.redraw, active=self.redraw, state=self.redraw, icon=self.redraw,
                  accent=self.redraw, hovered=self.redraw, menu=self.redraw, disabled=self.redraw)
        self.redraw()

    def redraw(self, *_):
        self.canvas.clear()
        if self.active:
            bg = theme.ACCENT
        elif self.state == "down":
            bg = theme.darker(theme.BUTTON, 0.08)
        elif self.hovered:
            bg = theme.BUTTON
        else:
            bg = (0, 0, 0, 0)
        self.canvas.add(Color(*bg))
        self.canvas.add(RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(5)]))
        fg = list(theme.TEXT[:3]) + [0.35 if self.disabled else 1]
        width = self.width - (dp(10) if self.menu else 0)
        draw_icon(self.canvas, self.icon, self.x + width / 2, self.center_y, min(width, self.height) * 0.8,
                  fg, self.accent)
        if self.menu:  # small drop-down triangle
            self.canvas.add(Color(*fg))
            x, y = self.right - dp(9), self.center_y
            _polygon(self.canvas, [(x - dp(3.5), y + dp(2)), (x + dp(3.5), y + dp(2)), (x, y - dp(2.5))])


class ToolSeparator(Widget):
    def __init__(self, **kwargs):
        kwargs.setdefault("size_hint", (None, None))
        kwargs.setdefault("size", (dp(13), dp(34)))
        super().__init__(**kwargs)
        self.bind(pos=self.redraw, size=self.redraw)

    def redraw(self, *_):
        self.canvas.clear()
        self.canvas.add(Color(*theme.MUTED[:3], 0.35))
        self.canvas.add(Rectangle(pos=(self.center_x - dp(0.5), self.y + dp(6)), size=(dp(1), self.height - dp(12))))
