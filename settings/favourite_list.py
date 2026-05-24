import json

from qgis.PyQt.QtCore import pyqtSignal
from qgis.PyQt.QtGui import QPainter
from qgis.PyQt.QtWidgets import (
    QLineEdit,
    QListWidget,
    QStyledItemDelegate,
)

from ..qt_compat import (
    QABSTRACT_ITEM_VIEW_DRAG_DROP,
    QT_MOVE_ACTION,
    event_pos,
)
from .common import FAVOURITE_LAYER_MIME


class FavouriteListItemDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        editor = super().createEditor(parent, option, index)
        if isinstance(editor, QLineEdit):
            editor.setStyleSheet(
                "QLineEdit { border: 1px solid #202020; padding: 1px 3px; }"
            )
        return editor


class FavouriteListWidget(QListWidget):
    favouritesDropped = pyqtSignal(list, int)
    listAboutToChange = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._external_drop_row = None
        self.setItemDelegate(FavouriteListItemDelegate(self))
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QABSTRACT_ITEM_VIEW_DRAG_DROP)
        self.setDefaultDropAction(QT_MOVE_ACTION)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(FAVOURITE_LAYER_MIME):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(FAVOURITE_LAYER_MIME):
            self._set_external_drop_row(self._drop_row_from_pos(event_pos(event)))
            event.acceptProposedAction()
            return
        self._clear_external_drop_row()
        super().dragMoveEvent(event)

    def dragLeaveEvent(self, event):
        self._clear_external_drop_row()
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        if not event.mimeData().hasFormat(FAVOURITE_LAYER_MIME):
            self._clear_external_drop_row()
            self.listAboutToChange.emit()
            super().dropEvent(event)
            return

        try:
            payload = bytes(event.mimeData().data(FAVOURITE_LAYER_MIME)).decode("utf-8")
            favourites = json.loads(payload)
        except (TypeError, ValueError):
            favourites = []

        if not isinstance(favourites, list):
            favourites = []

        row = self._external_drop_row
        if row is None:
            row = self._drop_row_from_pos(event_pos(event))

        self._clear_external_drop_row()
        self.favouritesDropped.emit(favourites, row)
        event.acceptProposedAction()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._external_drop_row is None:
            return

        y = self._drop_line_y(self._external_drop_row)
        painter = QPainter(self.viewport())
        painter.fillRect(
            2,
            max(0, y - 1),
            self.viewport().width() - 4,
            2,
            self.palette().highlight(),
        )
        painter.end()

    def _drop_row_from_pos(self, pos):
        index = self.indexAt(pos)
        row = index.row()
        if row < 0:
            return self.count()

        rect = self.visualItemRect(self.item(row))
        if pos.y() > rect.center().y():
            row += 1
        return max(0, min(row, self.count()))

    def _drop_line_y(self, row):
        if self.count() == 0:
            return 0
        if row <= 0:
            return self.visualItemRect(self.item(0)).top()
        if row >= self.count():
            return self.visualItemRect(self.item(self.count() - 1)).bottom() + 1
        return self.visualItemRect(self.item(row)).top()

    def _set_external_drop_row(self, row):
        row = max(0, min(row, self.count()))
        if self._external_drop_row == row:
            return
        self._external_drop_row = row
        self.viewport().update()

    def _clear_external_drop_row(self):
        if self._external_drop_row is None:
            return
        self._external_drop_row = None
        self.viewport().update()
