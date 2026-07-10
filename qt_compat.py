from qgis.PyQt.QtCore import QEvent, QPoint, Qt
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QDialogButtonBox,
    QHeaderView,
    QSizePolicy,
    QToolButton,
)

try:
    from qgis.PyQt.QtGui import QAction
except ImportError:
    from qgis.PyQt.QtWidgets import QAction


def _qt_enum(enum_name, value_name):
    enum = getattr(Qt, enum_name, None)
    if enum is not None and hasattr(enum, value_name):
        return getattr(enum, value_name)
    return getattr(Qt, value_name)


def _event_type(value_name):
    enum = getattr(QEvent, "Type", None)
    if enum is not None and hasattr(enum, value_name):
        return getattr(enum, value_name)
    return getattr(QEvent, value_name)


def _object_enum(owner, enum_name, value_name):
    enum = getattr(owner, enum_name, None)
    if enum is not None and hasattr(enum, value_name):
        return getattr(enum, value_name)
    return getattr(owner, value_name)


QT_LEFT_BUTTON = _qt_enum("MouseButton", "LeftButton")
QT_POINTING_HAND_CURSOR = _qt_enum("CursorShape", "PointingHandCursor")
QT_FORBIDDEN_CURSOR = _qt_enum("CursorShape", "ForbiddenCursor")
QT_COPY_ACTION = _qt_enum("DropAction", "CopyAction")
QT_MOVE_ACTION = _qt_enum("DropAction", "MoveAction")
QT_IGNORE_ACTION = _qt_enum("DropAction", "IgnoreAction")
QT_TRANSPARENT = _qt_enum("GlobalColor", "transparent")
QT_ALIGN_CENTER = _qt_enum("AlignmentFlag", "AlignCenter")
QT_ALIGN_VCENTER = _qt_enum("AlignmentFlag", "AlignVCenter")
QT_ALIGN_LEFT = _qt_enum("AlignmentFlag", "AlignLeft")
QT_ELIDE_RIGHT = _qt_enum("TextElideMode", "ElideRight")
QT_RICH_TEXT = _qt_enum("TextFormat", "RichText")
QT_HORIZONTAL = _qt_enum("Orientation", "Horizontal")
QT_USER_ROLE = _qt_enum("ItemDataRole", "UserRole")
QT_DISPLAY_ROLE = _qt_enum("ItemDataRole", "DisplayRole")
QT_ITEM_IS_EDITABLE = _qt_enum("ItemFlag", "ItemIsEditable")
QT_TOOLTIP_EVENT = _event_type("ToolTip")

QABSTRACT_ITEM_VIEW_SINGLE_SELECTION = _object_enum(
    QAbstractItemView, "SelectionMode", "SingleSelection"
)
QABSTRACT_ITEM_VIEW_EXTENDED_SELECTION = _object_enum(
    QAbstractItemView, "SelectionMode", "ExtendedSelection"
)
QABSTRACT_ITEM_VIEW_DRAG_DROP = _object_enum(
    QAbstractItemView, "DragDropMode", "DragDrop"
)
QDIALOG_BUTTON_OK = _object_enum(QDialogButtonBox, "StandardButton", "Ok")
QDIALOG_BUTTON_CANCEL = _object_enum(QDialogButtonBox, "StandardButton", "Cancel")
QHEADER_VIEW_STRETCH = _object_enum(QHeaderView, "ResizeMode", "Stretch")
QSIZE_POLICY_EXPANDING = _object_enum(QSizePolicy, "Policy", "Expanding")
QSIZE_POLICY_FIXED = _object_enum(QSizePolicy, "Policy", "Fixed")
QSIZE_POLICY_MINIMUM = _object_enum(QSizePolicy, "Policy", "Minimum")
QTOOL_BUTTON_INSTANT_POPUP = _object_enum(
    QToolButton, "ToolButtonPopupMode", "InstantPopup"
)


def exec_qt(obj, *args):
    method = getattr(obj, "exec", None)
    if callable(method):
        return method(*args)
    return obj.exec_(*args)


def event_pos(event):
    position = getattr(event, "position", None)
    if callable(position):
        return position().toPoint()

    pos = getattr(event, "pos", None)
    if callable(pos):
        return pos()

    return QPoint()


def event_global_pos(event):
    position = getattr(event, "globalPosition", None)
    if callable(position):
        return position().toPoint()

    pos = getattr(event, "globalPos", None)
    if callable(pos):
        return pos()

    return QPoint()


def set_header_section_resize_mode(header, section, mode=QHEADER_VIEW_STRETCH):
    method = getattr(header, "setSectionResizeMode", None)
    if callable(method):
        method(section, mode)
        return
    header.setResizeMode(section, mode)
