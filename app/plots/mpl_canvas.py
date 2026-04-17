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
        self._marker_artist = None
        self.canvas.mpl_connect("button_press_event", self._on_click)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas)

    def set_click_callback(self, callback: Callable[[float, float], None] | None) -> None:
        self._click_callback = callback

    def clear(self) -> None:
        self.axes.clear()
        self._marker_artist = None

    def reset_labels(self, title: str, x_label: str, y_label: str) -> None:
        self.axes.set_title(title)
        self.axes.set_xlabel(x_label)
        self.axes.set_ylabel(y_label)
        self.axes.grid(True, which="both", linestyle="--", linewidth=0.5, alpha=0.55)

    def draw_idle(self) -> None:
        self.canvas.draw_idle()

    def set_marker(self, x_value: float, y_value: float) -> None:
        if self._marker_artist is not None:
            self._marker_artist.remove()
        (self._marker_artist,) = self.axes.plot(
            [x_value],
            [y_value],
            marker="o",
            markersize=7,
            color="crimson",
            linestyle="None",
            zorder=5,
        )
        self.canvas.draw_idle()

    def _on_click(self, event) -> None:
        if event.inaxes != self.axes or event.xdata is None or event.ydata is None:
            return
        if self._click_callback is not None:
            self._click_callback(float(event.xdata), float(event.ydata))
