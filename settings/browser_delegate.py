from qgis.PyQt.QtCore import QRect
from qgis.PyQt.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem

from ..icons import qgis_icon
from ..qt_compat import QT_ALIGN_CENTER


class BrowserLayerDelegate(QStyledItemDelegate):
    BUTTON_SIZE = 16
    BUTTON_MARGIN = 6
    BUTTON_SPACING = 4

    def __init__(self, parent=None):
        super().__init__(parent)
        self.add_icon = qgis_icon("/mActionAdd.svg", "/mActionAddLayer.svg")
        self.info_icon = qgis_icon("/mActionPropertiesWidget.svg")

    @classmethod
    def add_button_rect(cls, row_rect):
        if not row_rect.isValid():
            return QRect()
        left = row_rect.right() - cls.BUTTON_MARGIN - cls.BUTTON_SIZE + 1
        top = row_rect.top() + int((row_rect.height() - cls.BUTTON_SIZE) / 2)
        return QRect(left, top, cls.BUTTON_SIZE, cls.BUTTON_SIZE)

    @classmethod
    def info_button_rect(cls, row_rect):
        if not row_rect.isValid():
            return QRect()
        left = row_rect.right() - cls.BUTTON_MARGIN - cls.BUTTON_SIZE - cls.BUTTON_SPACING - cls.BUTTON_SIZE + 1
        top = row_rect.top() + int((row_rect.height() - cls.BUTTON_SIZE) / 2)
        return QRect(left, top, cls.BUTTON_SIZE, cls.BUTTON_SIZE)

    @classmethod
    def reserved_width(cls):
        return (cls.BUTTON_SIZE * 2) + cls.BUTTON_SPACING + (cls.BUTTON_MARGIN * 2)

    def paint(self, painter, option, index):
        if not self._is_addable(index):
            super().paint(painter, option, index)
            return

        text_option = QStyleOptionViewItem(option)
        text_option.rect = option.rect.adjusted(0, 0, -self.reserved_width(), 0)
        super().paint(painter, text_option, index)

        add_rect = self.add_button_rect(option.rect)
        self.add_icon.paint(painter, add_rect, QT_ALIGN_CENTER)

        info_rect = self.info_button_rect(option.rect)
        self.info_icon.paint(painter, info_rect, QT_ALIGN_CENTER)

    def _is_addable(self, index):
        model = index.model()
        return bool(model and hasattr(model, "is_addable") and model.is_addable(index))
