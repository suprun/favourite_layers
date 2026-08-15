import json

from qgis.PyQt.QtCore import pyqtSignal, QModelIndex, QRect
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
    QT_IGNORE_ACTION,
    QT_POINTING_HAND_CURSOR,
    QT_TOOLTIP_EVENT,
    QT_USER_ROLE,
    event_global_pos,
    event_pos,
    exec_qt,
)
from ..storage import (
    ADD_TRANSPARENCY_SLIDER_KEY,
    add_transparency_slider_enabled,
    is_separator,
    normalise_favourite,
)
from .common import FAVOURITE_LAYER_MIME, tr, transparency_slider_tooltip


class FavouriteListItemDelegate(QStyledItemDelegate):
    BUTTON_SIZE = 16
    BUTTON_MARGIN = 6
    BUTTON_SPACING = 4

    def __init__(self, parent=None):
        super().__init__(parent)
        from ..icons import qgis_icon, transparency_slider_icon

        self.info_icon = qgis_icon("/mActionPropertiesWidget.svg")
        self.transparency_icon = transparency_slider_icon()
        self.transparency_checked_icon = transparency_slider_icon(checked=True)

    @classmethod
    def info_button_rect(cls, row_rect):
        if not row_rect.isValid():
            return QRect()
        left = row_rect.right() - cls.BUTTON_MARGIN - cls.BUTTON_SIZE + 1
        top = row_rect.top() + int((row_rect.height() - cls.BUTTON_SIZE) / 2)
        return QRect(left, top, cls.BUTTON_SIZE, cls.BUTTON_SIZE)

    @classmethod
    def transparency_button_rect(cls, row_rect):
        if not row_rect.isValid():
            return QRect()
        right = (
            row_rect.right()
            - cls.BUTTON_MARGIN
            - cls.BUTTON_SIZE
            - cls.BUTTON_SPACING
        )
        left = right - cls.BUTTON_SIZE + 1
        top = row_rect.top() + int((row_rect.height() - cls.BUTTON_SIZE) / 2)
        return QRect(left, top, cls.BUTTON_SIZE, cls.BUTTON_SIZE)

    @classmethod
    def reserved_width(cls):
        return (
            (cls.BUTTON_SIZE * 2)
            + cls.BUTTON_SPACING
            + (cls.BUTTON_MARGIN * 2)
        )

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

        transparency_rect = self.transparency_button_rect(option.rect)
        enabled = add_transparency_slider_enabled(favourite)
        if enabled:
            painter.save()
            highlight = option.palette.highlight().color()
            background = highlight
            background.setAlpha(70)
            painter.setPen(highlight)
            painter.setBrush(background)
            painter.drawRoundedRect(
                transparency_rect.adjusted(0, 0, -1, -1),
                2,
                2,
            )
            painter.restore()

        painter.save()
        transparency_icon = (
            self.transparency_checked_icon if enabled else self.transparency_icon
        )
        transparency_icon.paint(
            painter,
            transparency_rect.adjusted(1, 1, -1, -1),
            QT_ALIGN_CENTER,
        )
        painter.restore()

        info_rect = self.info_button_rect(option.rect)
        self.info_icon.paint(painter, info_rect, QT_ALIGN_CENTER)

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
    internalMoveFinished = pyqtSignal(bool)
    transparencySliderToggled = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._external_drop_row = None
        self._pressed_item_button = None
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
            source_row = self.currentRow()
            if source_row < 0:
                event.ignore()
                return
            target_row = self._drop_row_from_pos(event_pos(event))
            if target_row < 0:
                target_row = self.count()

            # Якщо елемент кинули на самого себе або після самого себе, змін немає
            if target_row == source_row or target_row == source_row + 1:
                event.setDropAction(QT_IGNORE_ACTION)
                event.accept()
                return

            self.listAboutToChange.emit()
            item = self.takeItem(source_row)
            insert_row = target_row
            if source_row < target_row:
                insert_row -= 1
            self.insertItem(insert_row, item)
            self.setCurrentItem(item)
            self.internalMoveFinished.emit(True)
            event.setDropAction(QT_IGNORE_ACTION)
            event.accept()
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

    def mousePressEvent(self, event):
        if event.button() == QT_LEFT_BUTTON:
            button_name, index = self._item_button_at(event_pos(event))
            if index.isValid():
                if button_name == "transparency":
                    self.setCurrentIndex(index)
                self._pressed_item_button = (button_name, index.row())
                event.accept()
                return
        self._pressed_item_button = None
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == QT_LEFT_BUTTON and self._pressed_item_button:
            button_name, row = self._pressed_item_button
            self._pressed_item_button = None
            released_button, index = self._item_button_at(event_pos(event))
            if (
                index.isValid()
                and index.row() == row
                and released_button == button_name
            ):
                if button_name == "transparency":
                    self.toggle_transparency_slider(index)
                else:
                    self._show_layer_info(index)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == QT_LEFT_BUTTON:
            button_name, index = self._item_button_at(event_pos(event))
            if button_name and index.isValid():
                self._pressed_item_button = (button_name, index.row())
                event.accept()
                return
        super().mouseDoubleClickEvent(event)

    def mouseMoveEvent(self, event):
        button_name, index = self._item_button_at(event_pos(event))
        if button_name and index.isValid():
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
            button_name, index = self._item_button_at(pos)
            if index.isValid():
                if button_name == "transparency":
                    tooltip = transparency_slider_tooltip(
                        tr("Add transparency slider when the layer is added")
                    )
                    rect = self._transparency_button_rect(index)
                else:
                    tooltip = tr("Show layer properties")
                    rect = self._info_button_rect(index)
                QToolTip.showText(
                    event_global_pos(event),
                    tooltip,
                    self.viewport(),
                    rect,
                )
                return True
            QToolTip.hideText()
        return super().viewportEvent(event)

    def _item_button_at(self, pos):
        index = self.indexAt(pos)
        if not index.isValid():
            return None, QModelIndex()

        favourite = index.data(QT_USER_ROLE)
        if not favourite or is_separator(favourite):
            return None, QModelIndex()

        if self._transparency_button_rect(index).contains(pos):
            return "transparency", index
        if self._info_button_rect(index).contains(pos):
            return "info", index
        return None, QModelIndex()

    def _info_button_rect(self, index):
        delegate = self.itemDelegate()
        rect = self.visualRect(index)
        if delegate and hasattr(delegate, "info_button_rect"):
            return delegate.info_button_rect(rect)
        return QRect()

    def _transparency_button_rect(self, index):
        delegate = self.itemDelegate()
        rect = self.visualRect(index)
        if delegate and hasattr(delegate, "transparency_button_rect"):
            return delegate.transparency_button_rect(rect)
        return QRect()

    def toggle_transparency_slider(self, index):
        if not index.isValid():
            return

        item = self.item(index.row())
        if item is None:
            return

        favourite = normalise_favourite(item.data(QT_USER_ROLE))
        if is_separator(favourite):
            return

        self.listAboutToChange.emit()
        favourite[ADD_TRANSPARENCY_SLIDER_KEY] = (
            not add_transparency_slider_enabled(favourite)
        )
        item.setData(QT_USER_ROLE, favourite)
        self.viewport().update(self.visualRect(index))
        self.transparencySliderToggled.emit()

    def _show_layer_info(self, index):
        favourite = index.data(QT_USER_ROLE)
        if not favourite:
            return

        from .common import SourceInfoDialog
        dialog = SourceInfoDialog(favourite, self.window())
        exec_qt(dialog)
