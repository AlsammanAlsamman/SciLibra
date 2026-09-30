"""Start-up screen: the round logo inside an animated loading ring, shown while the library opens."""

from __future__ import annotations

from kivy.animation import Animation
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.properties import NumericProperty, StringProperty
from kivy.uix.floatlayout import FloatLayout

INTRO_SECONDS = 0.8  # the ring fills to 70% while the logo pops in; then the library is opened


class Splash(FloatLayout):
    """Covers the window; `progress` (0..1) drives the ring, `spin` turns the glow, `status` is the caption.
    Its look is the `<Splash>` rule in layout.kv."""
    icon = StringProperty("")
    status = StringProperty("Starting...")
    progress = NumericProperty(0)
    spin = NumericProperty(0)
    logo_scale = NumericProperty(0.82)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._spin = Clock.schedule_interval(self._turn, 1 / 60)
        Animation(logo_scale=1, d=0.55, t="out_back").start(self)
        Animation(progress=0.7, d=INTRO_SECONDS, t="out_quad").start(self)

    def _turn(self, dt):
        self.spin = (self.spin + dt * 220) % 360

    def show(self):
        Window.add_widget(self)

    def finish(self, on_done=None):
        """Complete the ring, pause a moment on the full ring, then fade out and remove."""
        def fade(*_):
            anim = Animation(opacity=0, d=0.35, t="in_quad")
            anim.bind(on_complete=lambda *_: self._remove(on_done))
            anim.start(self)

        Animation.cancel_all(self, "progress")
        self.status = "Ready"
        anim = Animation(progress=1, d=0.35, t="out_quad")
        anim.bind(on_complete=lambda *_: Clock.schedule_once(fade, 0.25))
        anim.start(self)

    def _remove(self, on_done):
        self._spin.cancel()
        if self.parent is not None:
            self.parent.remove_widget(self)
        if on_done:
            on_done()

    # The splash is on top of everything: keep clicks from reaching the library underneath.
    def on_touch_down(self, touch):
        return True

    def on_touch_move(self, touch):
        return True

    def on_touch_up(self, touch):
        return True
