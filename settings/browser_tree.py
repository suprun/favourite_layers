import json

from qgis.PyQt.QtCore import (
    QByteArray,
    QCoreApplication,
    QMimeData,
    QModelIndex,
    QPoint,
    QRect,
    QTimer,
    pyqtSignal,
)
from qgis.PyQt.QtGui import QColor, QDrag, QPainter, QPixmap
from qgis.PyQt.QtWidgets import QToolTip, QTreeView

from ..icons import layer_icon, qgis_icon
from ..qt_compat import (
    QT_ALIGN_CENTER,
    QT_ALIGN_LEFT,
    QT_ALIGN_VCENTER,
    QT_COPY_ACTION,
    QT_ELIDE_RIGHT,
    QT_FORBIDDEN_CURSOR,
    QT_LEFT_BUTTON,
    QT_POINTING_HAND_CURSOR,
    QT_TOOLTIP_EVENT,
    QT_TRANSPARENT,
    event_global_pos,
    event_pos,
    exec_qt,
)
from .browser_delegate import BrowserLayerDelegate
from .common import FAVOURITE_LAYER_MIME, tr


class BrowserLayerTreeView(QTreeView):
    favouritesRequested = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)

    def selected_favourites(self):
        proxy = self.model()
        if proxy is None:
            return []

        favourites = []
        for index in self.selectionModel().selectedRows():
            if proxy.is_addable(index):
                favourite = proxy.favourite_from_proxy_index(index)
                if favourite.get("uri"):
                    favourites.append(favourite)
        return favourites

    def mouseReleaseEvent(self, event):
        if event.button() == QT_LEFT_BUTTON:
            pos = event_pos(event)
            index = self._add_button_index_at(pos)
            if index.isValid():
                self._request_favourite(index)
                event.accept()
                return
            index = self._info_button_index_at(pos)
            if index.isValid():
                self._show_layer_info(index)
                event.accept()
                return
        super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event):
        pos = event_pos(event)
        if self._add_button_index_at(pos).isValid() or self._info_button_index_at(pos).isValid():
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
            index = self._add_button_index_at(pos)
            if index.isValid():
                QToolTip.showText(
                    event_global_pos(event),
                    tr("Add this layer to the menu"),
                    self.viewport(),
                    self._add_button_rect(index),
                )
                return True
            index = self._info_button_index_at(pos)
            if index.isValid():
                QToolTip.showText(
                    event_global_pos(event),
                    tr("Show layer properties"),
                    self.viewport(),
                    self._info_button_rect(index),
                )
                return True
            QToolTip.hideText()
        return super().viewportEvent(event)

    def startDrag(self, supported_actions):
        favourites = self.selected_favourites()
        if not favourites:
            self._show_denied_drag_cursor()
            return

        mime_data = QMimeData()
        mime_data.setData(
            FAVOURITE_LAYER_MIME,
            QByteArray(json.dumps(favourites, ensure_ascii=False).encode("utf-8")),
        )

        drag = QDrag(self)
        drag.setMimeData(mime_data)
        drag.setPixmap(self._drag_pixmap(favourites))
        drag.setHotSpot(QPoint(12, 12))
        exec_qt(drag, QT_COPY_ACTION)

    def _request_favourite(self, index):
        proxy = self.model()
        if proxy is None or not proxy.is_addable(index):
            return
        favourite = proxy.favourite_from_proxy_index(index)
        if favourite.get("uri"):
            self.favouritesRequested.emit([favourite])

    def _add_button_index_at(self, pos):
        index = self.indexAt(pos)
        if not index.isValid() or index.column() != 0:
            return QModelIndex()
        proxy = self.model()
        if proxy is None or not proxy.is_addable(index):
            return QModelIndex()
        if not self._add_button_rect(index).contains(pos):
            return QModelIndex()
        return index

    def _add_button_rect(self, index):
        return BrowserLayerDelegate.add_button_rect(self.visualRect(index))

    def _info_button_index_at(self, pos):
        index = self.indexAt(pos)
        if not index.isValid() or index.column() != 0:
            return QModelIndex()
        proxy = self.model()
        if proxy is None or not proxy.is_addable(index):
            return QModelIndex()
        if not self._info_button_rect(index).contains(pos):
            return QModelIndex()
        return index

    def _info_button_rect(self, index):
        return BrowserLayerDelegate.info_button_rect(self.visualRect(index))

    def _show_layer_info(self, index):
        proxy = self.model()
        if proxy is None:
            return
        favourite = proxy.favourite_from_proxy_index(index)
        if not favourite:
            return

        from .common import SourceInfoDialog
        dialog = SourceInfoDialog(favourite, self.window())
        exec_qt(dialog)

    def _drag_pixmap(self, favourites):
        max_rows = 5
        rows = favourites[:max_rows]
        extra_count = max(0, len(favourites) - len(rows))
        row_height = max(24, self.sizeHintForRow(0) if self.model() else 24)
        margin = 2
        metrics = self.fontMetrics()
        arrow_icon = qgis_icon("/mActionArrowRight.svg", "/mIconNext.svg")
        more_arrow_icon = qgis_icon(
            ":/images/themes/default/mActionDoubleArrowRight.svg",
            "/mActionDoubleArrowRight.svg",
            "/mActionArrowRight.svg",
        )

        labels = [favourite.get("name") or favourite.get("uri") for favourite in rows]
        if extra_count:
            labels.append(tr("{count} more layers").format(count=extra_count))

        width = 180
        for label in labels:
            width = max(width, min(metrics.horizontalAdvance(label) + 70, 380))
        height = (row_height * len(labels)) + (margin * 2)

        pixmap = QPixmap(width, height)
        pixmap.fill(QT_TRANSPARENT)

        painter = QPainter(pixmap)
        painter.setPen(self.palette().color(self.foregroundRole()))
        painter.setBrush(self.palette().base())
        y = margin
        for favourite in rows:
            row_rect = QRect(0, y, width, row_height)
            painter.fillRect(row_rect, self.palette().base())
            painter.setPen(QColor(210, 210, 210))
            painter.drawLine(
                row_rect.left(), row_rect.bottom(), row_rect.right(), row_rect.bottom()
            )

            icon_rect = QRect(margin + 4, y + int((row_height - 16) / 2), 16, 16)
            arrow_rect = QRect(width - 24, y + int((row_height - 16) / 2), 16, 16)
            text_rect = QRect(30, y, width - 58, row_height)
            layer_icon(favourite).paint(painter, icon_rect, QT_ALIGN_CENTER)
            arrow_icon.paint(painter, arrow_rect, QT_ALIGN_CENTER)
            painter.setPen(self.palette().color(self.foregroundRole()))
            text = metrics.elidedText(
                favourite.get("name") or favourite.get("uri"),
                QT_ELIDE_RIGHT,
                text_rect.width(),
            )
            painter.drawText(text_rect, QT_ALIGN_VCENTER | QT_ALIGN_LEFT, text)
            y += row_height

        if extra_count:
            arrow_rect = QRect(width - 24, y + int((row_height - 16) / 2), 16, 16)
            text_rect = QRect(30, y, width - 58, row_height)
            painter.fillRect(QRect(0, y, width, row_height), self.palette().base())
            painter.setPen(self.palette().color(self.foregroundRole()))
            painter.drawText(
                text_rect,
                QT_ALIGN_VCENTER | QT_ALIGN_LEFT,
                tr("{count} more layers").format(count=extra_count),
            )
            more_arrow_icon.paint(painter, arrow_rect, QT_ALIGN_CENTER)

        painter.end()
        return pixmap

    def _show_denied_drag_cursor(self):
        self.viewport().setCursor(QT_FORBIDDEN_CURSOR)
        QCoreApplication.processEvents()
        QTimer.singleShot(300, self.viewport().unsetCursor)
