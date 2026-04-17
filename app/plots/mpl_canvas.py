from __future__ import annotations

from collections.abc import Callable

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT
from matplotlib.figure import Figure
from PyQt6.QtWidgets import QVBoxLayout, QWidget


class PlotCanvas(QWidget):
    def __init__(self, title: str, x_label: str, y_label: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.figure = Figure(figsize=(7, 4), constrained_layout=True)
        self.canvas = FigureCanvasQTAgg(self.figure)
        self.toolbar = NavigationToolbar2QT(self.canvas, self)
        self.axes = self.figure.add_subplot(111)
        self.axes.set_title(title)
        self.axes.set_xlabel(x_label)
        self.axes.set_ylabel(y_label)
        self.axes.grid(True, which="both", linestyle="--", linewidth=0.5, alpha=0.55)
        self._click_callback: Callable[[float, float], None] | None = None
        self._drag_callback: Callable[[float, float], None] | None = None
        self._hover_callback: Callable[[float | None, float | None], None] | None = None
        self._marker_artists = []
        self._hover_annotation = None
        self._dragging = False
        self.canvas.mpl_connect("button_press_event", self._on_click)
        self.canvas.mpl_connect("motion_notify_event", self._on_motion)
        self.canvas.mpl_connect("button_release_event", self._on_release)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas)

    def set_click_callback(self, callback: Callable[[float, float], None] | None) -> None:
        self._click_callback = callback

    def set_drag_callback(self, callback: Callable[[float, float], None] | None) -> None:
        self._drag_callback = callback

    def set_hover_callback(self, callback: Callable[[float | None, float | None], None] | None) -> None:
        self._hover_callback = callback

    def clear(self) -> None:
        self.axes.clear()
        self._marker_artists = []
        self._hover_annotation = None

    def reset_labels(self, title: str, x_label: str, y_label: str) -> None:
        self.axes.set_title(title)
        self.axes.set_xlabel(x_label)
        self.axes.set_ylabel(y_label)
        self.axes.grid(True, which="both", linestyle="--", linewidth=0.5, alpha=0.55)

    def draw_idle(self) -> None:
        self.canvas.draw_idle()

    def clear_markers(self) -> None:
        for artist in self._marker_artists:
            artist.remove()
        self._marker_artists = []

    def set_hover_annotation(self, x_value: float, y_value: float, text: str) -> None:
        x_limits = self.axes.get_xlim()
        y_limits = self.axes.get_ylim()
        x_midpoint = (x_limits[0] + x_limits[1]) / 2.0
        y_midpoint = (y_limits[0] + y_limits[1]) / 2.0
        x_offset = -12 if x_value >= x_midpoint else 12
        y_offset = -12 if y_value >= y_midpoint else 12

        if self._hover_annotation is None:
            self._hover_annotation = self.axes.annotate(
                text,
                xy=(x_value, y_value),
                xytext=(x_offset, y_offset),
                textcoords="offset points",
                bbox={"boxstyle": "round,pad=0.3", "fc": "#1f1f1f", "ec": "#c0c0c0", "alpha": 0.9},
                color="white",
                fontsize=8,
                zorder=6,
                annotation_clip=True,
            )
            self._hover_annotation.set_in_layout(False)
        else:
            self._hover_annotation.xy = (x_value, y_value)
            self._hover_annotation.set_position((x_offset, y_offset))
            self._hover_annotation.set_text(text)
            self._hover_annotation.set_visible(True)
        self.canvas.draw_idle()

    def clear_hover_annotation(self) -> None:
        if self._hover_annotation is not None:
            self._hover_annotation.set_visible(False)
            self.canvas.draw_idle()

    def set_point_marker(self, x_value: float, y_value: float) -> None:
        self.clear_markers()
        (artist,) = self.axes.plot(
            [x_value],
            [y_value],
            marker="o",
            markersize=7,
            color="crimson",
            linestyle="None",
            zorder=5,
        )
        self._marker_artists = [artist]
        self.canvas.draw_idle()

    def set_vertical_marker(self, x_value: float) -> None:
        self.clear_markers()
        artist = self.axes.axvline(x_value, color="crimson", linestyle="--", linewidth=1.2, zorder=4)
        self._marker_artists = [artist]
        self.canvas.draw_idle()

    def _on_click(self, event) -> None:
        if event.inaxes != self.axes or event.xdata is None or event.ydata is None:
            return
        if event.button == 1 and self._drag_callback is not None:
            self._dragging = True
        if self._click_callback is not None:
            self._click_callback(float(event.xdata), float(event.ydata))

    def _on_motion(self, event) -> None:
        if self._hover_callback is not None:
            if event.inaxes != self.axes or event.xdata is None or event.ydata is None:
                self._hover_callback(None, None)
            else:
                self._hover_callback(float(event.xdata), float(event.ydata))
        if not self._dragging or self._drag_callback is None:
            return
        if event.inaxes != self.axes or event.xdata is None or event.ydata is None:
            return
        self._drag_callback(float(event.xdata), float(event.ydata))

    def _on_release(self, _event) -> None:
        self._dragging = False
