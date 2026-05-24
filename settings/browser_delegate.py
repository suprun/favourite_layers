from qgis.PyQt.QtCore import QRect
from qgis.PyQt.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem

from ..icons import qgis_icon
from ..qt_compat import QT_ALIGN_CENTER


class BrowserLayerDelegate(QStyledItemDelegate):
    BUTTON_SIZE = 16
    BUTTON_MARGIN = 6

    def __init__(self, parent=None):
        super().__init__(parent)
        self.add_icon = qgis_icon("/mActionAdd.svg", "/mActionAddLayer.svg")

    @classmethod
    def add_button_rect(cls, row_rect):
        if not row_rect.isValid():
            return QRect()
        left = row_rect.right() - cls.BUTTON_MARGIN - cls.BUTTON_SIZE + 1
        top = row_rect.top() + int((row_rect.height() - cls.BUTTON_SIZE) / 2)
        return QRect(left, top, cls.BUTTON_SIZE, cls.BUTTON_SIZE)

    @classmethod
    def reserved_width(cls):
        return cls.BUTTON_SIZE + (cls.BUTTON_MARGIN * 2)

    def paint(self, painter, option, index):
        if not self._is_addable(index):
            super().paint(painter, option, index)
            return

        text_option = QStyleOptionViewItem(option)
        text_option.rect = option.rect.adjusted(0, 0, -self.reserved_width(), 0)
        super().paint(painter, text_option, index)

        button_rect = self.add_button_rect(option.rect)
        self.add_icon.paint(painter, button_rect, QT_ALIGN_CENTER)

    def _is_addable(self, index):
        model = index.model()
        return bool(model and hasattr(model, "is_addable") and model.is_addable(index))
