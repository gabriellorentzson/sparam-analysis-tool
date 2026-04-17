from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QListWidget, QListWidgetItem


class FileListWidget(QListWidget):
    visibility_changed = pyqtSignal(str, bool)
    files_dropped = pyqtSignal(list)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)

    def add_file(self, file_path: str, display_name: str, checked: bool = True) -> None:
        item = QListWidgetItem(display_name)
        item.setData(Qt.ItemDataRole.UserRole, file_path)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsSelectable)
        item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self.addItem(item)

    def selected_file_paths(self) -> list[str]:
        return [item.data(Qt.ItemDataRole.UserRole) for item in self.selectedItems()]

    def remove_file(self, file_path: str) -> None:
        for row in range(self.count()):
            item = self.item(row)
            if item.data(Qt.ItemDataRole.UserRole) == file_path:
                self.takeItem(row)
                return

    def clear_files(self) -> None:
        self.clear()

    def dragEnterEvent(self, event) -> None:  # pragma: no cover - Qt hook
        mime_data = event.mimeData()
        if mime_data.hasUrls():
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event) -> None:  # pragma: no cover - Qt hook
        mime_data = event.mimeData()
        if mime_data.hasUrls():
            event.acceptProposedAction()
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event) -> None:  # pragma: no cover - Qt hook
        mime_data = event.mimeData()
        if not mime_data.hasUrls():
            super().dropEvent(event)
            return

        file_paths = []
        for url in mime_data.urls():
            local_path = url.toLocalFile()
            if local_path.lower().endswith(".s4p"):
                file_paths.append(local_path)

        if file_paths:
            self.files_dropped.emit(file_paths)
            event.acceptProposedAction()
            return
        super().dropEvent(event)
