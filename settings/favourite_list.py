import json

from qgis.PyQt.QtCore import pyqtSignal, QModelIndex, QPoint, QRect, Qt
from qgis.PyQt.QtGui import QPainter
from qgis.PyQt.QtWidgets import (
    QLineEdit,
    QListWidget,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QToolTip,
)

from ..qt_compat import (
    QABSTRACT_ITEM_VIEW_DRAG_DROP,
    QT_ALIGN_CENTER,
    QT_LEFT_BUTTON,
    QT_MOVE_ACTION,
    QT_POINTING_HAND_CURSOR,
    QT_TOOLTIP_EVENT,
    QT_USER_ROLE,
    event_global_pos,
    event_pos,
    exec_qt,
)
from ..storage import is_separator
from .common import FAVOURITE_LAYER_MIME


class FavouriteListItemDelegate(QStyledItemDelegate):
    BUTTON_SIZE = 16
    BUTTON_MARGIN = 6

    def __init__(self, parent=None):
        super().__init__(parent)
        from ..icons import qgis_icon
        self.info_icon = qgis_icon("/mActionPropertiesWidget.svg")

    @classmethod
    def info_button_rect(cls, row_rect):
        if not row_rect.isValid():
            return QRect()
        left = row_rect.right() - cls.BUTTON_MARGIN - cls.BUTTON_SIZE + 1
        top = row_rect.top() + int((row_rect.height() - cls.BUTTON_SIZE) / 2)
        return QRect(left, top, cls.BUTTON_SIZE, cls.BUTTON_SIZE)

    @classmethod
    def reserved_width(cls):
        return cls.BUTTON_SIZE + (cls.BUTTON_MARGIN * 2)

    def paint(self, painter, option, index):
        favourite = index.data(QT_USER_ROLE)
        if not favourite or is_separator(favourite):
            super().paint(painter, option, index)
            return

        widget = option.widget or self.parent()
        is_drag_visual = False
        if widget:
            viewport = getattr(widget, "viewport", None)
            if callable(viewport):
                try:
                    vp = viewport()
                    if vp and painter.device() != vp:
                        is_drag_visual = True
                except Exception:
                    pass

        if is_drag_visual:
            super().paint(painter, option, index)
            return

        text_option = QStyleOptionViewItem(option)
        text_option.rect = option.rect.adjusted(0, 0, -self.reserved_width(), 0)
        super().paint(painter, text_option, index)

        button_rect = self.info_button_rect(option.rect)
        self.info_icon.paint(painter, button_rect, QT_ALIGN_CENTER)

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
        self.setDropIndicatorShown(False)
        self.setDragDropMode(QABSTRACT_ITEM_VIEW_DRAG_DROP)
        self.setDefaultDropAction(QT_MOVE_ACTION)
        self.setMouseTracking(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(FAVOURITE_LAYER_MIME) or event.source() == self:
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(FAVOURITE_LAYER_MIME) or event.source() == self:
            self._set_external_drop_row(self._drop_row_from_pos(event_pos(event)))
            event.acceptProposedAction()
            return
        self._clear_external_drop_row()
        super().dragMoveEvent(event)

    def dragLeaveEvent(self, event):
        self._clear_external_drop_row()
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        if event.mimeData().hasFormat(FAVOURITE_LAYER_MIME):
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
        elif event.source() == self:
            self._clear_external_drop_row()
            self.listAboutToChange.emit()
            super().dropEvent(event)
        else:
            self._clear_external_drop_row()
            super().dropEvent(event)

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

    def mouseReleaseEvent(self, event):
        if event.button() == QT_LEFT_BUTTON:
            index = self._info_button_index_at(event_pos(event))
            if index.isValid():
                self._show_layer_info(index)
                event.accept()
                return
        super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event):
        if self._info_button_index_at(event_pos(event)).isValid():
            self.viewport().setCursor(QT_POINTING_HAND_CURSOR)
        else:
            self.viewport().unsetCursor()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self.viewport().unsetCursor()
        super().leaveEvent(event)

    def viewportEvent(self, event):
        if event.type() == QT_TOOLTIP_EVENT:
            pos = event_pos(event)
            index = self._info_button_index_at(pos)
            if index.isValid():
                from .common import tr
                QToolTip.showText(
                    event_global_pos(event),
                    tr("Show layer properties"),
                    self.viewport(),
                    self._info_button_rect(index),
                )
                return True
            QToolTip.hideText()
        return super().viewportEvent(event)

    def _info_button_index_at(self, pos):
        index = self.indexAt(pos)
        if not index.isValid():
            return QModelIndex()

        favourite = index.data(QT_USER_ROLE)
        if not favourite or is_separator(favourite):
            return QModelIndex()

        if not self._info_button_rect(index).contains(pos):
            return QModelIndex()
        return index

    def _info_button_rect(self, index):
        delegate = self.itemDelegate()
        rect = self.visualRect(index)
        if delegate and hasattr(delegate, "info_button_rect"):
            return delegate.info_button_rect(rect)
        return QRect()

    def _show_layer_info(self, index):
        favourite = index.data(QT_USER_ROLE)
        if not favourite:
            return

        from .common import SourceInfoDialog
        dialog = SourceInfoDialog(favourite, self.window())
        exec_qt(dialog)
