from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QListWidget, QListWidgetItem


class FileListWidget(QListWidget):
    visibility_changed = pyqtSignal(str, bool)

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
