"""Built-in PDF viewer and annotator.

Reading: continuous scrolling, zoom, go to page, find text, table of contents, night mode.
Annotating: highlight / underline / strike-out text, sticky notes, text boxes, freehand drawing,
rectangles, ellipses and arrows, eraser, edit notes and colours, undo. Annotations are saved into
the PDF file as standard PDF annotations (the original file is backed up before the first change).
"""

from __future__ import annotations

import logging
import os

import pymupdf
from kivy.clock import Clock
from kivy.core.clipboard import Clipboard
from kivy.core.window import Window
from kivy.factory import Factory
from kivy.graphics import Color, Ellipse, InstructionGroup, Line, Rectangle
from kivy.graphics.texture import Texture
from kivy.metrics import dp
from kivy.properties import BooleanProperty, ListProperty, NumericProperty, ObjectProperty, StringProperty
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.dropdown import DropDown
from kivy.uix.modalview import ModalView
from kivy.uix.widget import Widget

from ..core import annotate
from . import theme
from .dialogs import BasePopup, TextDialog
from .icons import IconButton, ToolSeparator

log = logging.getLogger(__name__)

PX_PER_POINT = 96 / 72          # 100% zoom = 96 dpi
MIN_ZOOM, MAX_ZOOM = 0.25, 5.0
KEEP_RENDERED = 4               # pages kept in memory on each side of the visible ones
MAX_TEXTURE_SIDE = 4096

# tool id -> (name, keyboard shortcut, status bar hint)
TOOLS = {
    "select": ("Select", "v", "Scroll the page; click an annotation to edit or delete it."),
    "text": ("Select text", "t", "Drag over text to select it, then copy it, quote it with a citation or save it as a comment."),
    "Highlight": ("Highlight", "h", "Drag over text to highlight it."),
    "Underline": ("Underline", "u", "Drag over text to underline it."),
    "StrikeOut": ("Strikethrough", "s", "Drag over text to strike it through."),
    "note": ("Sticky note", "n", "Click where the sticky note should go."),
    "textbox": ("Text box", "b", "Drag a box (or click) where the text should go."),
    "draw": ("Pen", "d", "Draw freehand with the mouse or a pen."),
    "Rectangle": ("Rectangle", "r", "Drag to draw a rectangle (e.g. around a figure)."),
    "Ellipse": ("Ellipse", "o", "Drag to draw an ellipse."),
    "Arrow": ("Arrow", "a", "Drag from the arrow's tail to its tip."),
    "Line": ("Line", "l", "Drag to draw a straight line."),
    "eraser": ("Eraser", "e", "Click an annotation to delete it."),
}
TEXT_TOOLS = {"text", "Highlight", "Underline", "StrikeOut"}
SHAPE_TOOLS = {"Rectangle", "Ellipse", "Arrow", "Line"}
# Toolbar layout: groups of tool ids separated by dividers ("shapes" and "color" open menus)
TOOL_GROUPS = [["select", "text"], ["Highlight", "Underline", "StrikeOut"], ["note", "textbox"],
               ["draw", "shapes", "eraser"], ["color", "undo"]]


class PdfPage(Widget):
    """One page: white sheet, rendered image (when visible), search / selection marks and live drawing."""
    number = NumericProperty(0)  # 0-based
    texture = ObjectProperty(None, allownone=True)
    rendered_scale = NumericProperty(0)
    viewer = ObjectProperty(None, allownone=True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.marks = InstructionGroup()
        self.live = InstructionGroup()
        self.canvas.after.add(self.marks)
        self.canvas.after.add(self.live)
        self._mark_rects = []  # (pdf rect, rgba, filled)
        self.scale = 1.0
        self.bind(pos=self._redraw_marks, size=self._redraw_marks)

    # ---- coordinates
    def to_pdf(self, x, y):
        return (x - self.x) / self.scale, (self.top - y) / self.scale

    def to_widget(self, px, py):
        return self.x + px * self.scale, self.top - py * self.scale

    # ---- marks (search hits, selection, focused annotation)
    def set_marks(self, rects):
        self._mark_rects = rects
        self._redraw_marks()

    def _redraw_marks(self, *_):
        self.marks.clear()
        for (x0, y0, x1, y1), rgba, filled in self._mark_rects:
            x, top = self.to_widget(x0, y0)
            w, h = (x1 - x0) * self.scale, (y1 - y0) * self.scale
            self.marks.add(Color(*rgba))
            if filled:
                self.marks.add(Rectangle(pos=(x, top - h), size=(w, h)))
            else:
                self.marks.add(Line(rectangle=(x - dp(2), top - h - dp(2), w + dp(4), h + dp(4)), width=dp(1.5)))

    # ---- touches are handed to the viewer's active tool
    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos) or touch.is_mouse_scrolling or self.viewer is None:
            return super().on_touch_down(touch)
        if self.viewer.tool_down(self, touch):
            touch.grab(self)
            return True
        return super().on_touch_down(touch)

    def on_touch_move(self, touch):
        if touch.grab_current is self:
            self.viewer.tool_move(self, touch)
            return True
        return super().on_touch_move(touch)

    def on_touch_up(self, touch):
        if touch.grab_current is self:
            touch.ungrab(self)
            self.viewer.tool_up(self, touch)
            return True
        if self.viewer is not None and self.viewer.tool == "select" and self.collide_point(*touch.pos) \
                and not touch.is_mouse_scrolling and touch.button in (None, "left") \
                and abs(touch.x - touch.ox) < dp(6) and abs(touch.y - touch.oy) < dp(6):
            self.viewer.click_select(self, touch)
        return super().on_touch_up(touch)


class AnnotationItem(ButtonBehavior, BoxLayout):
    """A row in the viewer's (and the details panel's) annotation list."""
    page = NumericProperty(0)
    heading = StringProperty("")
    body = StringProperty("")
    swatch = ListProperty([0.9, 0.8, 0.3, 1])
    index = NumericProperty(0)
    target = ObjectProperty(None, allownone=True)  # callable(index)

    def on_release(self):
        if self.target:
            self.target(self.index)


class TocItem(ButtonBehavior, BoxLayout):
    title = StringProperty("")
    page = NumericProperty(1)
    level = NumericProperty(1)
    target = ObjectProperty(None, allownone=True)

    def on_release(self):
        if self.target:
            self.target(self.page)


def annotation_rows(annotations):
    """Display data for annotations (shared by the viewer and the details panel)."""
    rows = []
    for i, a in enumerate(annotations):
        body = []
        if a.text:
            body.append(f"“{a.text}”")
        if a.note:
            body.append(a.note)
        color = list(a.color[:3]) + [1] if len(a.color) >= 3 else [0.6, 0.65, 0.7, 1]
        rows.append({"index": i, "page": a.page, "swatch": color,
                     "heading": f"p. {a.page}  ·  {a.label}" + (f"  ·  {a.author}" if a.author else ""),
                     "body": "\n".join(body) or "(no text)"})
    return rows


def fill_annotation_list(box, annotations, on_select):
    box.clear_widgets()
    for row in annotation_rows(annotations):
        box.add_widget(AnnotationItem(target=on_select, **row))


class ColorSwatch(ButtonBehavior, Widget):
    rgb = ListProperty([1, 1, 0])
    name = StringProperty("")
    selected = BooleanProperty(False)
    target = ObjectProperty(None, allownone=True)  # callable(name, rgb)

    def on_release(self):
        if self.target:
            self.target(self.name, tuple(self.rgb))


def add_swatches(box, current_rgb, on_pick):
    """Append one colour swatch per annotation colour to `box`."""
    swatches = []
    for name, rgb in annotate.COLORS.items():
        sw = ColorSwatch(rgb=list(rgb), name=name, target=on_pick,
                         selected=all(abs(a - b) < 0.02 for a, b in zip(rgb, current_rgb)))
        swatches.append(sw)
        box.add_widget(sw)
    return swatches


class AnnotationEditor(BasePopup):
    """Edit the note / colour of an existing annotation, or delete it."""
    heading = StringProperty("")
    marked_text = StringProperty("")
    note = StringProperty("")
    color = ListProperty([1, 0.89, 0.2])
    callback = ObjectProperty(None, allownone=True)  # callback(action, note, color) with action save/delete

    def on_open(self):
        self.ids.swatches.clear_widgets()
        self._swatches = add_swatches(self.ids.swatches, self.color, self.choose)

    def choose(self, _name, rgb):
        self.color = list(rgb)
        for sw in self._swatches:
            sw.selected = sw.name == _name

    def finish(self, action):
        self.dismiss()
        if self.callback:
            self.callback(action, self.ids.note.text.strip(), tuple(self.color))


class PdfViewer(ModalView):
    title = StringProperty("")
    path = StringProperty("")
    page = NumericProperty(1)          # current page, 1-based
    page_count = NumericProperty(0)
    zoom = NumericProperty(1.0)
    fit_width = BooleanProperty(True)
    status = StringProperty("")
    panel = StringProperty("")         # "", "annotations" or "contents"
    annotations = ListProperty([])
    toc = ListProperty([])
    hit_count = NumericProperty(0)
    error = StringProperty("")
    tool = StringProperty("select")
    color_name = StringProperty("Yellow")
    night = BooleanProperty(False)
    selection_text = StringProperty("")
    can_undo = BooleanProperty(False)
    modified = BooleanProperty(False)
    color_names = ListProperty(list(annotate.COLORS))
    # callbacks provided by the app
    external_callback = ObjectProperty(None, allownone=True)   # () -> None
    comment_callback = ObjectProperty(None, allownone=True)    # (text) -> message
    export_callback = ObjectProperty(None, allownone=True)     # () -> None
    closed_callback = ObjectProperty(None, allownone=True)     # (viewer) -> None
    citation = StringProperty("")
    backup_dir = StringProperty("")

    def __init__(self, path, title="", start_page=1, **kwargs):
        kwargs.setdefault("auto_dismiss", False)
        super().__init__(**kwargs)
        self.path = path
        self.title = title or os.path.basename(path)
        self.doc = None
        self.pages: list[PdfPage] = []
        self.sizes = []
        self.hits = []          # (page index, rect)
        self.hit_index = -1
        self.undo_stack = []    # (page index, xref) of annotations created in this session
        self._queue = []
        self._start_page = start_page
        self._drag = None       # state of the current tool gesture
        self._selection = None  # (page index, words)
        self._update_trigger = Clock.create_trigger(self._update_visible, 0.05)
        try:
            self.doc = pymupdf.open(path)
            self.page_count = self.doc.page_count
            self.sizes = [(p.rect.width, p.rect.height) for p in self.doc]
            self.toc = [(lvl, title, page) for lvl, title, page in self.doc.get_toc(simple=True) if page >= 1]
        except Exception as exc:
            self.error = f"Cannot open this PDF: {exc}"
        self.annotations = self._read_annotations()
        self.panel = "annotations" if self.annotations else ("contents" if self.toc else "")
        Clock.schedule_once(self._build, 0)

    # ------------------------------------------------------------------ setup / teardown
    def on_open(self):
        Window.bind(on_key_down=self._on_key, mouse_pos=self._on_mouse)

    def on_dismiss(self):
        Window.unbind(on_key_down=self._on_key, mouse_pos=self._on_mouse)
        Clock.unschedule(self._render_next)
        if self.closed_callback:
            self.closed_callback(self)
        for p in self.pages:
            p.texture = None
        if self.doc is not None:
            self.doc.close()
            self.doc = None

    def _build(self, *_):
        box = self.ids.pages
        box.clear_widgets()
        self.pages = []
        for i in range(self.page_count):
            page = PdfPage(number=i, size_hint=(None, None), pos_hint={"center_x": 0.5}, viewer=self)
            box.add_widget(page)
            self.pages.append(page)
        self.ids.scroll.bind(scroll_y=lambda *_: self._update_trigger(), size=lambda *_: self._on_resize())
        self._refresh_lists()
        self._build_toolbar()
        self.on_tool(self, self.tool)
        self._apply_zoom(keep_position=False)
        Clock.schedule_once(lambda _dt: self.go_to(self._start_page), 0.1)

    def _build_toolbar(self):
        row = self.ids.tool_row
        row.clear_widgets()
        self._icon_buttons = {}
        for n, group in enumerate(TOOL_GROUPS):
            if n:
                row.add_widget(ToolSeparator())
            for item in group:
                if item == "shapes":
                    button = IconButton(icon="shapes", menu=True, width=dp(48), hint="Shapes: rectangle, ellipse, arrow, line")
                    button.bind(on_release=self._open_shapes)
                elif item == "color":
                    button = IconButton(icon="color", menu=True, width=dp(48), hint="Colour of new annotations")
                    button.bind(on_release=self._open_colors)
                elif item == "undo":
                    button = IconButton(icon="undo", hint="Undo the last annotation (Ctrl+Z)")
                    button.bind(on_release=lambda *_: self.undo())
                else:
                    name, key, _hint = TOOLS[item]
                    button = IconButton(icon=item, hint=f"{name} ({key.upper()})")
                    button.bind(on_release=lambda _b, t=item: self.set_tool(t))
                row.add_widget(button)
                self._icon_buttons[item] = button
        self._update_toolbar()

    def _menu(self, button, items, choose):
        """Drop-down under `button`: items are (icon or rgb, label, value)."""
        menu = DropDown(auto_width=False, width=dp(190))
        for icon, label, value in items:
            line = BoxLayout(size_hint_y=None, height=dp(38), padding=(dp(6), dp(2)), spacing=dp(8))
            with line.canvas.before:
                Color(*theme.INPUT)
                bg = Rectangle(pos=line.pos, size=line.size)
            line.bind(pos=lambda w, _p, r=bg: setattr(r, "pos", w.pos), size=lambda w, _s, r=bg: setattr(r, "size", w.size))
            if isinstance(icon, str):
                picture = IconButton(icon=icon, accent=self.color, size=(dp(34), dp(34)))
            else:
                picture = ColorSwatch(rgb=list(icon), selected=value == self.color_name)
            picture.bind(on_release=lambda *_a, v=value: (menu.dismiss(), choose(v)))
            text = Factory.FlatButton(text=label, halign="left", bg=theme.INPUT, height=dp(34))
            text.bind(size=lambda w, _s: setattr(w, "text_size", (w.width - dp(12), None)))
            text.bind(on_release=lambda *_a, v=value: (menu.dismiss(), choose(v)))
            line.add_widget(picture)
            line.add_widget(text)
            menu.add_widget(line)
        menu.open(button)
        return menu

    def _open_shapes(self, button):
        items = [(t, f"{TOOLS[t][0]}  ({TOOLS[t][1].upper()})", t) for t in ("Rectangle", "Ellipse", "Arrow", "Line")]
        return self._menu(button, items, self.set_tool)

    def _open_colors(self, button):
        return self._menu(button, [(rgb, name, name) for name, rgb in annotate.COLORS.items()], self._pick_color)

    def _pick_color(self, name, _rgb=None):
        self.color_name = name

    def _update_toolbar(self, *_):
        buttons = getattr(self, "_icon_buttons", {})
        for item, button in buttons.items():
            button.accent = self.color
            if item in TOOLS:
                button.active = item == self.tool
        shapes = buttons.get("shapes")
        if shapes is not None:
            shapes.active = self.tool in SHAPE_TOOLS
            shapes.icon = self.tool if self.tool in SHAPE_TOOLS else "shapes"
        if "undo" in buttons:
            buttons["undo"].disabled = not self.can_undo

    def on_can_undo(self, *_):
        self._update_toolbar()

    def on_color_name(self, *_):
        self._update_toolbar()

    def _on_mouse(self, _window, pos):
        """Hover hints for the toolbar icons."""
        for button in getattr(self, "_icon_buttons", {}).values():
            inside = button.get_root_window() is not None and button.collide_point(*button.to_widget(*pos))
            if inside and not button.hovered:
                self.status = button.hint
            button.hovered = inside

    def _read_annotations(self):
        if self.doc is None:
            return []
        try:
            return annotate.document_annotations(self.doc)
        except Exception as exc:
            log.warning("Cannot read annotations: %s", exc)
            return []

    def _refresh_lists(self):
        fill_annotation_list(self.ids.annotation_list, self.annotations, self.show_annotation)
        box = self.ids.toc_list
        box.clear_widgets()
        for level, title, page in self.toc:
            box.add_widget(TocItem(title=title, page=page, level=level, target=self.go_to))

    # ------------------------------------------------------------------ geometry
    def _scale(self):
        return self.zoom * PX_PER_POINT * dp(1)

    def _fit_zoom(self):
        if not self.sizes:
            return 1.0
        available = self.ids.scroll.width - dp(40)
        widest = max(w for w, _ in self.sizes)
        return max(MIN_ZOOM, min(MAX_ZOOM, available / (widest * PX_PER_POINT * dp(1))))

    def _on_resize(self):
        if self.fit_width:
            self._apply_zoom()

    def on_panel(self, *_):
        if self.fit_width and self.pages:
            Clock.schedule_once(lambda _dt: self._apply_zoom(), 0)

    def _apply_zoom(self, keep_position=True):
        if not self.pages:
            return
        current = self.page
        if self.fit_width:
            self.zoom = self._fit_zoom()
        scale = self._scale()
        for page, (w, h) in zip(self.pages, self.sizes):
            page.scale = scale
            page.size = (w * scale, h * scale)
            if page.rendered_scale and abs(page.rendered_scale - scale) > 1e-3:
                page.rendered_scale = 0  # re-render at the new zoom (old texture shown meanwhile)
        self._show_marks()
        if keep_position:
            Clock.schedule_once(lambda _dt: self.go_to(current), 0)
        self._update_trigger()

    def set_zoom(self, zoom):
        self.fit_width = False
        self.zoom = max(MIN_ZOOM, min(MAX_ZOOM, zoom))
        self._apply_zoom()

    def zoom_in(self):
        self.set_zoom(self.zoom * 1.2)

    def zoom_out(self):
        self.set_zoom(self.zoom / 1.2)

    def fit(self):
        self.fit_width = True
        self._apply_zoom()

    def _viewport(self):
        """(bottom, top) of the visible area in the page container's coordinates."""
        scroll, box = self.ids.scroll, self.ids.pages
        extra = max(box.height - scroll.height, 0)
        bottom = extra * scroll.scroll_y
        return bottom, bottom + scroll.height

    def _page_span(self, page):
        box = self.ids.pages
        return page.y - box.y, page.top - box.y

    # ------------------------------------------------------------------ navigation
    def go_to(self, number, offset_points=0.0):
        """Scroll so that page `number` (1-based) starts at the top of the view."""
        if not self.pages:
            return
        number = max(1, min(self.page_count, int(number)))
        page = self.pages[number - 1]
        scroll, box = self.ids.scroll, self.ids.pages
        extra = box.height - scroll.height
        if extra <= 0:
            scroll.scroll_y = 1
        else:
            top = page.top - box.y - offset_points * page.scale + dp(8)
            scroll.scroll_y = max(0.0, min(1.0, (top - scroll.height) / extra))
        self.page = number
        self._update_trigger()

    def next_page(self):
        self.go_to(self.page + 1)

    def previous_page(self):
        self.go_to(self.page - 1)

    def scroll_by(self, pixels):
        scroll, box = self.ids.scroll, self.ids.pages
        extra = box.height - scroll.height
        if extra > 0:
            scroll.scroll_y = max(0.0, min(1.0, scroll.scroll_y + pixels / extra))

    # ------------------------------------------------------------------ rendering
    def _update_visible(self, *_):
        if not self.pages or self.doc is None:
            return
        bottom, top = self._viewport()
        visible = [i for i, p in enumerate(self.pages)
                   if self._page_span(p)[1] >= bottom and self._page_span(p)[0] <= top]
        if not visible:
            return
        middle = (bottom + top) / 2
        for i in visible:
            low, high = self._page_span(self.pages[i])
            if low <= middle <= high or i == visible[-1]:
                self.page = i + 1
                break
        wanted = list(range(max(0, visible[0] - 1), min(self.page_count, visible[-1] + 2)))
        self._queue = [i for i in wanted if not self.pages[i].rendered_scale]
        for i, page in enumerate(self.pages):
            if page.texture is not None and (i < visible[0] - KEEP_RENDERED or i > visible[-1] + KEEP_RENDERED):
                page.texture = None
                page.rendered_scale = 0
        if self._queue:
            Clock.unschedule(self._render_next)
            Clock.schedule_once(self._render_next, 0)

    def _render_next(self, *_):
        """Render one page per frame so scrolling stays smooth."""
        while self._queue:
            i = self._queue.pop(0)
            page = self.pages[i]
            if page.rendered_scale:
                continue
            try:
                page.texture = self._render(i, page.scale)
                page.rendered_scale = page.scale
            except Exception as exc:
                log.warning("Cannot render page %s: %s", i + 1, exc)
                page.rendered_scale = -1
            break
        if self._queue:
            Clock.schedule_once(self._render_next, 0)

    def _render(self, index, scale):
        pdf_page = self.doc[index]
        w, h = self.sizes[index]
        scale = min(scale, MAX_TEXTURE_SIDE / max(w, h, 1))
        # Render on white, then add an opaque alpha channel (4-byte pixels upload reliably to OpenGL).
        pix = pdf_page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False, annots=True)
        if self.night:
            pix.invert_irect(pix.irect)
        pix = pymupdf.Pixmap(pix, 1)
        texture = Texture.create(size=(pix.width, pix.height), colorfmt="rgba")
        texture.blit_buffer(pix.samples, colorfmt="rgba", bufferfmt="ubyte")
        texture.flip_vertical()
        return texture

    def rerender(self, indexes=None):
        for i in (range(self.page_count) if indexes is None else indexes):
            self.pages[i].rendered_scale = 0
        self._update_trigger()

    def on_night(self, *_):
        if self.pages:
            self.rerender()

    # ------------------------------------------------------------------ search
    def search(self, text):
        text = text.strip()
        self.hits = []
        if text and self.doc is not None:
            for i in range(self.page_count):
                for r in self.doc[i].search_for(text):
                    self.hits.append((i, (r.x0, r.y0, r.x1, r.y1)))
        self.hit_count = len(self.hits)
        self.hit_index = 0 if self.hits else -1
        if text and not self.hits:
            self.status = f"'{text}' not found"
        self._show_marks()
        self._show_hit()

    def next_hit(self, step=1):
        if self.hits:
            self.hit_index = (self.hit_index + step) % len(self.hits)
            self._show_marks()
            self._show_hit()

    def _show_hit(self):
        if 0 <= self.hit_index < len(self.hits):
            index, rect = self.hits[self.hit_index]
            self.go_to(index + 1, offset_points=max(rect[1] - 60, 0))
            self.status = f"Match {self.hit_index + 1} of {len(self.hits)}"

    def _show_marks(self, focus_annotation=None):
        per_page = {i: [] for i in range(self.page_count)}
        for n, (i, rect) in enumerate(self.hits):
            current = n == self.hit_index
            per_page[i].append((rect, (1, 0.55, 0, 0.45) if current else (1, 0.9, 0, 0.35), True))
        if self._selection:
            index, words = self._selection
            for r in annotate.line_rects(words):
                per_page[index].append(((r.x0, r.y0, r.x1, r.y1), (0.26, 0.52, 0.96, 0.35), True))
        if focus_annotation is not None:
            a = self.annotations[focus_annotation]
            if a.rect:
                per_page[a.page - 1].append((a.rect, (0.26, 0.52, 0.96, 1), False))
        for i, page in enumerate(self.pages):
            page.set_marks(per_page.get(i, []))

    # ------------------------------------------------------------------ side panels
    def show_annotation(self, index):
        a = self.annotations[index]
        self._show_marks(focus_annotation=index)
        self.go_to(a.page, offset_points=max(a.rect[1] - 60, 0) if a.rect else 0)

    def toggle_panel(self, name):
        self.panel = "" if self.panel == name else name

    def save_all_as_comments(self):
        if not self.comment_callback:
            return
        added = 0
        for a in self.annotations:
            if a.text or a.note:
                added += bool(self.comment_callback(a.as_comment()))
        self.status = f"{added} annotations saved as comments" if added else \
            "All annotations are already saved as comments"

    def export_notes(self):
        if self.export_callback:
            self.export_callback()

    def open_external(self):
        if self.external_callback:
            self.external_callback()

    # ------------------------------------------------------------------ tools
    @property
    def color(self):
        return annotate.COLORS.get(self.color_name, annotate.COLORS["Yellow"])

    def set_tool(self, tool):
        self.tool = tool

    def on_tool(self, _inst, tool):
        if "scroll" not in self.ids:
            return
        # With an editing tool, dragging on the page draws instead of scrolling (the wheel and bars still scroll).
        self.ids.scroll.scroll_type = ["bars", "content"] if tool == "select" else ["bars"]
        if tool not in TEXT_TOOLS:
            self.clear_selection()
        if (tool in SHAPE_TOOLS or tool in ("draw", "textbox")) and self.color_name == "Yellow":
            self.color_name = "Red"  # yellow is hard to see as a line
        elif tool in ("Highlight",) and self.color_name == "Red":
            self.color_name = "Yellow"
        self._update_toolbar()
        self.status = f"{TOOLS[tool][0]}: {TOOLS[tool][2]}"

    def tool_down(self, page, touch):
        if self.tool == "select" or self.doc is None or touch.button not in (None, "left"):
            return False
        start = page.to_pdf(*touch.pos)
        self._drag = {"page": page, "start": start, "points": [start]}
        if self.tool in TEXT_TOOLS:
            self._drag["words"] = annotate.page_words(self.doc[page.number])
        return True

    def tool_move(self, page, touch):
        drag = self._drag
        if not drag or drag["page"] is not page:
            return
        point = page.to_pdf(*touch.pos)
        drag["points"].append(point)
        page.live.clear()
        rgba = list(self.color) + [0.9]
        if self.tool in TEXT_TOOLS:
            words = annotate.words_between(drag["words"], drag["start"], point)
            page.live.add(Color(0.26, 0.52, 0.96, 0.35))
            for r in annotate.line_rects(words):
                x, top = page.to_widget(r.x0, r.y0)
                page.live.add(Rectangle(pos=(x, top - r.height * page.scale),
                                        size=(r.width * page.scale, r.height * page.scale)))
        elif self.tool == "draw":
            page.live.add(Color(*rgba))
            pts = [c for p in drag["points"] for c in page.to_widget(*p)]
            page.live.add(Line(points=pts, width=dp(1.3)))
        elif self.tool in SHAPE_TOOLS or self.tool == "textbox":
            (x0, y0), (x1, y1) = page.to_widget(*drag["start"]), page.to_widget(*point)
            page.live.add(Color(*rgba))
            if self.tool == "Ellipse":
                page.live.add(Line(ellipse=(min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0)), width=dp(1.3)))
            elif self.tool in ("Arrow", "Line"):
                page.live.add(Line(points=[x0, y0, x1, y1], width=dp(1.3)))
                if self.tool == "Arrow":
                    page.live.add(Ellipse(pos=(x1 - dp(3), y1 - dp(3)), size=(dp(6), dp(6))))
            else:
                page.live.add(Line(rectangle=(min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0)), width=dp(1.3)))

    def tool_up(self, page, touch):
        drag, self._drag = self._drag, None
        page.live.clear()
        if not drag or self.doc is None:
            return
        end = page.to_pdf(*touch.pos)
        pdf_page = self.doc[page.number]
        tool = self.tool
        if tool in TEXT_TOOLS:
            words = annotate.words_between(drag["words"], drag["start"], end)
            if not words:
                self.status = "No text here - this page may be a scanned image."
                return
            if tool == "text":
                self._selection = (page.number, words)
                self.selection_text = annotate.words_text(words)
                self._show_marks()
                return
            self._commit(page.number, lambda: annotate.add_markup(pdf_page, tool, words, self.color))
        elif tool == "note":
            self._ask_text("Sticky note", "Type your note...", lambda text: self._commit(
                page.number, lambda: annotate.add_note(pdf_page, end, text, self.color)))
        elif tool == "textbox":
            (x0, y0), (x1, y1) = drag["start"], end
            if abs(x1 - x0) < 20 or abs(y1 - y0) < 12:
                x1, y1 = x0 + 200, y0 + 40
            rect = (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))
            self._ask_text("Text box", "Text shown on the page...", lambda text: self._commit(
                page.number, lambda: annotate.add_textbox(pdf_page, rect, text, self.color)))
        elif tool == "draw":
            points = drag["points"] + [end]
            self._commit(page.number, lambda: annotate.add_ink(pdf_page, [points], self.color))
        elif tool in SHAPE_TOOLS:
            self._commit(page.number, lambda: annotate.add_shape(pdf_page, tool, drag["start"], end, self.color))
        elif tool == "eraser":
            annot = annotate.annot_at(pdf_page, end)
            if annot is None:
                self.status = "No annotation here."
                return
            kind = annot.type[1]
            self._commit(page.number, lambda: annotate.delete_annot(pdf_page, annot.xref), created=False,
                         message=f"Deleted {kind.lower()} on page {page.number + 1}")

    def _ask_text(self, title, hint, done):
        def action(text):
            if not text.strip():
                return False
            done(text.strip())
            return None
        dialog = TextDialog(title=title, hint=hint, confirm_text="Add", action=action, size_hint=(0.5, 0.45))
        dialog.open()
        Clock.schedule_once(lambda _dt: setattr(dialog.ids.input, "focus", True), 0.1)

    def click_select(self, page, touch):
        """Select tool: clicking an annotation opens its editor."""
        if self.doc is None:
            return
        pdf_page = self.doc[page.number]
        annot = annotate.annot_at(pdf_page, page.to_pdf(*touch.pos))
        if annot is None:
            return
        xref = annot.xref
        found = next((a for a in self.annotations if a.xref == xref and a.page == page.number + 1), None)
        colors = annot.colors or {}
        color = colors.get("stroke") or colors.get("fill") or annotate.COLORS["Yellow"]

        def done(action, note, rgb):
            if action == "delete":
                self._commit(page.number, lambda: annotate.delete_annot(pdf_page, xref), created=False,
                             message="Annotation deleted")
            elif action == "save":
                self._commit(page.number, lambda: annotate.update_annot(pdf_page, xref, note=note, color=rgb),
                             created=False, message="Annotation updated")
        AnnotationEditor(title="Annotation", heading=f"p. {page.number + 1}  ·  {found.label if found else annot.type[1]}",
                         marked_text=(found.text if found else ""),
                         note=(found.note if found else (annot.info or {}).get("content", "")),
                         color=list(color[:3]), callback=done).open()

    def _commit(self, page_index, change, created=True, message=""):
        """Apply a change to the document, save it into the PDF file and refresh the view."""
        try:
            if self.backup_dir:
                annotate.backup_once(self.path, self.backup_dir)
            result = change()
            if not result:
                self.status = "Nothing was changed."
                return
            if annotate.save_document(self.doc, self.path):
                self._reopen()
        except Exception as exc:
            log.exception("Cannot save annotation")
            self.status = f"Could not save the annotation: {exc}"
            return
        if created and isinstance(result, int):
            self.undo_stack.append((page_index, result))
        self.can_undo = bool(self.undo_stack)
        self.modified = True
        self.annotations = self._read_annotations()
        self._refresh_lists()
        self.rerender([page_index])
        self.status = message or f"Saved in the PDF ({TOOLS.get(self.tool, ('Annotation',))[0].lower()})"

    def _reopen(self):
        self.doc.close()
        self.doc = pymupdf.open(self.path)

    def undo(self):
        if not self.undo_stack or self.doc is None:
            self.status = "Nothing to undo."
            return
        page_index, xref = self.undo_stack.pop()
        self._commit(page_index, lambda: annotate.delete_annot(self.doc[page_index], xref), created=False,
                     message="Undone")

    # ------------------------------------------------------------------ text selection actions
    def clear_selection(self):
        self._selection = None
        self.selection_text = ""
        if self.pages:
            self._show_marks()

    def _selection_page(self):
        return (self._selection[0] + 1) if self._selection else self.page

    def copy_selection(self, with_citation=False):
        text = self.selection_text
        if not text:
            return
        if with_citation:
            text = f"“{text}” ({self.citation or self.title}, p. {self._selection_page()})"
        try:
            Clipboard.copy(text)
            self.status = "Copied" + (" with citation" if with_citation else "")
        except Exception:
            self.status = "Clipboard not available"

    def markup_selection(self, kind):
        if not self._selection:
            return
        index, words = self._selection
        self._commit(index, lambda: annotate.add_markup(self.doc[index], kind, words, self.color))
        self.clear_selection()

    def selection_to_comment(self):
        if self.selection_text and self.comment_callback:
            comment = f"[p. {self._selection_page()}] “{self.selection_text}”"
            self.status = "Saved as a comment" if self.comment_callback(comment) else "This comment already exists"
            self.clear_selection()

    # ------------------------------------------------------------------ keyboard / mouse wheel
    def on_touch_down(self, touch):
        if touch.is_mouse_scrolling and "ctrl" in Window.modifiers and self.ids.scroll.collide_point(*touch.pos):
            if touch.button == "scrollup":
                self.zoom_out()
            elif touch.button == "scrolldown":
                self.zoom_in()
            return True
        return super().on_touch_down(touch)

    def _on_key(self, _window, key, _scancode, codepoint, modifiers):
        if Window.children and Window.children[0] is not self:
            return False  # another popup is on top
        ctrl = "ctrl" in modifiers or "meta" in modifiers
        search = self.ids.search
        if ctrl and codepoint == "f":
            search.focus = True
            return True
        if ctrl and codepoint == "z":
            self.undo()
            return True
        if ctrl and codepoint == "c" and self.selection_text and not search.focus:
            self.copy_selection()
            return True
        if key == 27:  # Escape: leave search, then drop the tool/selection, then close
            if search.focus:
                search.focus = False
            elif self.selection_text:
                self.clear_selection()
            elif self.tool != "select":
                self.tool = "select"
            else:
                self.dismiss()
            return True
        if search.focus or self.ids.page_input.focus:
            return False
        if key in (281, 32) or (key == 274 and ctrl):   # PageDown / Space
            self.next_page()
        elif key == 280 or (key == 273 and ctrl):       # PageUp
            self.previous_page()
        elif key == 274:
            self.scroll_by(-dp(60))
        elif key == 273:
            self.scroll_by(dp(60))
        elif key == 278:
            self.go_to(1)
        elif key == 279:
            self.go_to(self.page_count)
        elif codepoint in ("+", "="):
            self.zoom_in()
        elif codepoint == "-":
            self.zoom_out()
        elif codepoint == "0":
            self.fit()
        elif not ctrl and codepoint and any(codepoint == t[1] for t in TOOLS.values()):
            self.tool = next(k for k, t in TOOLS.items() if t[1] == codepoint)
        else:
            return False
        return True
