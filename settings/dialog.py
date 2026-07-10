from qgis.PyQt.QtCore import QAbstractItemModel, QModelIndex
from qgis.PyQt.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidgetItem,
    QSizePolicy,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from qgis.core import QgsBrowserModel

from ..icons import add_separator_icon, layer_icon, qgis_icon, separator_icon
from ..qt_compat import (
    QABSTRACT_ITEM_VIEW_EXTENDED_SELECTION,
    QABSTRACT_ITEM_VIEW_SINGLE_SELECTION,
    QDIALOG_BUTTON_CANCEL,
    QDIALOG_BUTTON_OK,
    QSIZE_POLICY_EXPANDING,
    QSIZE_POLICY_MINIMUM,
    QT_HORIZONTAL,
    QT_ITEM_IS_EDITABLE,
    QT_RICH_TEXT,
    QT_USER_ROLE,
    set_header_section_resize_mode,
)
from ..storage import (
    is_separator,
    normalise_favourite,
    normalise_favourites,
    separator_item,
)
from .browser_delegate import BrowserLayerDelegate
from .browser_model import BrowserLayerProxyModel
from .browser_tree import BrowserLayerTreeView
from .common import tr
from .favourite_list import FavouriteListWidget


class SettingsDialog(QDialog):
    def __init__(self, iface, favourites, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.setWindowTitle(tr("Configure favourite layers"))
        self.resize(980, 620)
        self._updating_list_item = False
        self._restoring_undo = False
        self._undo_stack = []

        self.list_widget = FavouriteListWidget(self)
        self.list_widget.setSelectionMode(QABSTRACT_ITEM_VIEW_SINGLE_SELECTION)
        self.list_widget.favouritesDropped.connect(self._insert_favourites)
        self.list_widget.listAboutToChange.connect(self._push_undo_snapshot)
        self.list_widget.itemChanged.connect(self._update_item_name)

        self.browser_model = self._browser_model()
        self.proxy_model = BrowserLayerProxyModel(self)
        self.proxy_model.setSourceModel(self.browser_model)
        self.proxy_model.setDynamicSortFilter(False)
        if hasattr(self.proxy_model, "setRecursiveFilteringEnabled"):
            self.proxy_model.setRecursiveFilteringEnabled(True)

        self.tree_view = BrowserLayerTreeView(self)
        self.tree_view.setModel(self.proxy_model)
        self.tree_view.setItemDelegate(BrowserLayerDelegate(self.tree_view))
        self.tree_view.setHeaderHidden(True)
        self.tree_view.header().setStretchLastSection(True)
        set_header_section_resize_mode(self.tree_view.header(), 0)
        self.tree_view.setSelectionMode(QABSTRACT_ITEM_VIEW_EXTENDED_SELECTION)
        self.tree_view.setDragEnabled(True)
        self.tree_view.favouritesRequested.connect(self._insert_favourites)
        self.tree_view.doubleClicked.connect(
            lambda index: self._add_selected_from_browser()
        )
        self.tree_view.expanded.connect(self._fetch_more)

        self._build_layout()
        self._load_favourites(favourites)
        self._update_buttons()

        from qgis.core import QgsSettings
        settings = QgsSettings()
        icon_theme = settings.value("favourite_layers/icon_theme", "default")
        if icon_theme == "yellow":
            self.btn_yellow_icon.setChecked(True)
        else:
            self.btn_default_icon.setChecked(True)

        self.list_widget.itemSelectionChanged.connect(self._update_buttons)
        self.tree_view.selectionModel().selectionChanged.connect(self._update_buttons)

    def _browser_model(self):
        getter = getattr(self.iface, "browserModel", None)
        if callable(getter):
            try:
                model = getter()
                if isinstance(model, QAbstractItemModel) and hasattr(model, "dataItem"):
                    return model
            except Exception:
                pass

        model = QgsBrowserModel(self)
        try:
            model.initialize()
        except Exception:
            pass
        return model

    def _build_layout(self):
        main_layout = QVBoxLayout(self)
        main_layout.addWidget(self._instruction_label())

        splitter = QSplitter(QT_HORIZONTAL, self)

        browser_panel = QWidget(splitter)
        browser_layout = QVBoxLayout(browser_panel)
        browser_layout.setContentsMargins(0, 0, 0, 0)
        browser_layout.addLayout(self._browser_toolbar())
        browser_layout.addWidget(self.tree_view)

        menu_panel = QWidget(splitter)
        menu_layout = QVBoxLayout(menu_panel)
        menu_layout.setContentsMargins(0, 0, 0, 0)
        menu_layout.addLayout(self._menu_list_toolbar())
        menu_layout.addWidget(self.list_widget)

        splitter.addWidget(browser_panel)
        splitter.addWidget(menu_panel)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 1)
        main_layout.addWidget(splitter, 1)

        bottom_layout = QHBoxLayout()

        icon_label = QLabel(tr("Plugin icon:"), self)
        bottom_layout.addWidget(icon_label)

        from qgis.PyQt.QtWidgets import QButtonGroup, QToolButton
        from ..icons import local_icon, is_dark_interface

        self.icon_group = QButtonGroup(self)
        self.icon_group.setExclusive(True)

        self.btn_default_icon = QToolButton(self)
        self.btn_default_icon.setCheckable(True)
        default_icon_name = "icon-dark.svg" if is_dark_interface() else "icon.svg"
        self.btn_default_icon.setIcon(local_icon(default_icon_name))
        self.btn_default_icon.setToolTip(tr("Default theme icon"))
        self.icon_group.addButton(self.btn_default_icon)
        bottom_layout.addWidget(self.btn_default_icon)

        self.btn_yellow_icon = QToolButton(self)
        self.btn_yellow_icon.setCheckable(True)
        self.btn_yellow_icon.setIcon(local_icon("icon_yellow.svg"))
        self.btn_yellow_icon.setToolTip(tr("Yellow icon"))
        self.icon_group.addButton(self.btn_yellow_icon)
        bottom_layout.addWidget(self.btn_yellow_icon)

        bottom_layout.addStretch(1)

        buttons = QDialogButtonBox(QDIALOG_BUTTON_OK | QDIALOG_BUTTON_CANCEL)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        bottom_layout.addWidget(buttons)

        main_layout.addLayout(bottom_layout)

    def accept(self):
        from qgis.core import QgsSettings
        settings = QgsSettings()
        if self.btn_yellow_icon.isChecked():
            settings.setValue("favourite_layers/icon_theme", "yellow")
        else:
            settings.setValue("favourite_layers/icon_theme", "default")
        super().accept()

    def _instruction_label(self):
        add_icon = (
            '<img src=":/images/themes/default/mActionAdd.svg" '
            'width="14" height="14" />'
        )
        label = QLabel(
            tr(
                "Select layers in the Browser tree and click {add_icon} Add, "
                "or drag them into the menu list."
            ).format(add_icon=add_icon),
            self,
        )
        label.setTextFormat(QT_RICH_TEXT)
        label.setWordWrap(True)
        label.setMargin(0)

        policy = QSizePolicy(QSIZE_POLICY_EXPANDING, QSIZE_POLICY_MINIMUM)
        policy.setHeightForWidth(True)
        label.setSizePolicy(policy)
        label.setMinimumHeight(0)
        return label

    def _tool_button(self, icon, tooltip, slot):
        button = QToolButton(self)
        button.setIcon(icon)
        button.setToolTip(tooltip)
        button.setAutoRaise(True)
        button.clicked.connect(lambda checked=False: slot())
        return button

    def _menu_list_toolbar(self):
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        self.edit_button = self._tool_button(
            qgis_icon("/mActionToggleEditing.svg", "/mActionEdit.svg"),
            tr("Rename selected menu item"),
            self._edit_selected,
        )
        self.undo_button = self._tool_button(
            qgis_icon("/mActionUndo.svg"),
            tr("Undo last menu list change"),
            self._undo,
        )
        self.separator_button = self._tool_button(
            add_separator_icon(),
            tr("Add separator"),
            self._add_separator,
        )
        self.remove_button = self._tool_button(
            qgis_icon("/mActionDeleteSelected.svg"),
            tr("Remove selected menu item"),
            self._remove_selected,
        )
        self.up_button = self._tool_button(
            qgis_icon("/mActionArrowUp.svg", "/mActionMoveFeature.svg"),
            tr("Move selected menu item up"),
            self._move_selected_up,
        )
        self.down_button = self._tool_button(
            qgis_icon("/mActionArrowDown.svg", "/mActionMoveFeature.svg"),
            tr("Move selected menu item down"),
            self._move_selected_down,
        )

        for button in (
            self.undo_button,
            self.separator_button,
            self.edit_button,
            self.remove_button,
            self.up_button,
            self.down_button,
        ):
            layout.addWidget(button)
        layout.addStretch(1)
        return layout

    def _browser_toolbar(self):
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        self.add_button = self._tool_button(
            qgis_icon("/mActionAdd.svg", "/mActionAddLayer.svg"),
            tr("Add selected browser layer to the menu"),
            self._add_selected_from_browser,
        )
        self.refresh_button = self._tool_button(
            qgis_icon("/mActionRefresh.svg", "/mActionReload.svg"),
            tr("Refresh browser layers"),
            self._refresh_browser,
        )

        layout.addWidget(self.add_button)
        layout.addWidget(self.refresh_button)
        layout.addStretch(1)
        return layout

    def _make_list_item(self, favourite):
        favourite = normalise_favourite(favourite)
        if is_separator(favourite):
            item = QListWidgetItem(separator_icon(), tr("Separator"))
            item.setToolTip(tr("Menu separator"))
            item.setData(QT_USER_ROLE, favourite)
            item.setFlags(item.flags() & ~QT_ITEM_IS_EDITABLE)
            return item

        item = QListWidgetItem(
            layer_icon(favourite),
            favourite.get("name") or favourite.get("uri"),
        )
        item.setToolTip(favourite.get("uri", ""))
        item.setData(QT_USER_ROLE, favourite)
        item.setFlags(item.flags() | QT_ITEM_IS_EDITABLE)
        return item

    def _load_favourites(self, favourites):
        self._restoring_undo = True
        self.list_widget.clear()
        try:
            for favourite in normalise_favourites(favourites):
                self.list_widget.addItem(self._make_list_item(favourite))
        finally:
            self._restoring_undo = False

    def _insert_favourites(self, favourites, row=None):
        if row is None:
            row = self.list_widget.count()

        valid_favourites = []
        for favourite in favourites:
            favourite = normalise_favourite(favourite)
            if is_separator(favourite) or not favourite.get("uri"):
                continue
            valid_favourites.append(favourite)

        if not valid_favourites:
            self._update_buttons()
            return

        self._push_undo_snapshot()

        inserted = 0
        for favourite in valid_favourites:
            self.list_widget.insertItem(row + inserted, self._make_list_item(favourite))
            inserted += 1

        if inserted:
            self.list_widget.setCurrentRow(row)
        self._update_buttons()

    def _selected_list_row(self):
        return self.list_widget.currentRow()

    def _selected_list_item(self):
        row = self._selected_list_row()
        if row < 0:
            return None
        return self.list_widget.item(row)

    def _edit_selected(self):
        item = self._selected_list_item()
        if item is None or is_separator(item.data(QT_USER_ROLE)):
            return

        self.list_widget.editItem(item)

    def _update_item_name(self, item):
        if self._updating_list_item or self._restoring_undo:
            return

        favourite = item.data(QT_USER_ROLE)
        if is_separator(favourite):
            return

        favourite = normalise_favourite(favourite)
        name = item.text().strip()
        if not name:
            name = favourite.get("name") or favourite.get("uri")
        if item.text() != name:
            self._updating_list_item = True
            try:
                item.setText(name)
            finally:
                self._updating_list_item = False

        if name == (favourite.get("name") or favourite.get("uri")):
            return

        self._push_undo_snapshot()
        favourite["name"] = name
        item.setData(QT_USER_ROLE, favourite)

    def _add_separator(self):
        row = self._selected_list_row()
        if row < 0:
            row = self.list_widget.count()
        else:
            row += 1
        self._push_undo_snapshot()
        self.list_widget.insertItem(row, self._make_list_item(separator_item()))
        self.list_widget.setCurrentRow(row)
        self._update_buttons()

    def _remove_selected(self):
        row = self._selected_list_row()
        if row >= 0:
            self._push_undo_snapshot()
            self.list_widget.takeItem(row)
        self._update_buttons()

    def _move_selected_up(self):
        row = self._selected_list_row()
        if row <= 0:
            return
        self._push_undo_snapshot()
        item = self.list_widget.takeItem(row)
        self.list_widget.insertItem(row - 1, item)
        self.list_widget.setCurrentRow(row - 1)

    def _move_selected_down(self):
        row = self._selected_list_row()
        if row < 0 or row >= self.list_widget.count() - 1:
            return
        self._push_undo_snapshot()
        item = self.list_widget.takeItem(row)
        self.list_widget.insertItem(row + 1, item)
        self.list_widget.setCurrentRow(row + 1)

    def _add_selected_from_browser(self):
        favourites = self.tree_view.selected_favourites()
        self._insert_favourites(favourites)

    def _fetch_more(self, proxy_index):
        source_index = self.proxy_model.mapToSource(proxy_index)
        try:
            while self.browser_model.canFetchMore(source_index):
                self.browser_model.fetchMore(source_index)
        except Exception:
            pass

    def _refresh_browser(self):
        refreshed = False
        for method_name in ("refresh", "reload"):
            method = getattr(self.browser_model, method_name, None)
            if not callable(method):
                continue
            try:
                method()
                refreshed = True
                break
            except TypeError:
                try:
                    method(QModelIndex())
                    refreshed = True
                    break
                except Exception:
                    pass
            except Exception:
                pass

        if not refreshed and isinstance(self.browser_model, QgsBrowserModel):
            try:
                self.browser_model.initialize()
            except Exception:
                pass

        self.proxy_model.invalidateFilter()

    def _list_snapshot(self):
        return [
            normalise_favourite(self.list_widget.item(row).data(QT_USER_ROLE))
            for row in range(self.list_widget.count())
        ]

    def _push_undo_snapshot(self):
        if self._restoring_undo:
            return

        snapshot = self._list_snapshot()
        if self._undo_stack and self._undo_stack[-1] == snapshot:
            return

        self._undo_stack.append(snapshot)
        if len(self._undo_stack) > 100:
            self._undo_stack.pop(0)
        self._update_buttons()

    def _restore_snapshot(self, snapshot):
        selected_row = self._selected_list_row()
        self._restoring_undo = True
        try:
            self.list_widget.clear()
            for favourite in snapshot:
                self.list_widget.addItem(self._make_list_item(favourite))
            if self.list_widget.count():
                self.list_widget.setCurrentRow(
                    min(max(selected_row, 0), self.list_widget.count() - 1)
                )
        finally:
            self._restoring_undo = False
        self._update_buttons()

    def _undo(self):
        if not self._undo_stack:
            return
        self._restore_snapshot(self._undo_stack.pop())

    def _update_buttons(self):
        row = self._selected_list_row()
        has_list_selection = row >= 0
        item = self._selected_list_item()
        selected_is_separator = bool(item and is_separator(item.data(QT_USER_ROLE)))
        self.undo_button.setEnabled(bool(self._undo_stack))
        self.edit_button.setEnabled(has_list_selection and not selected_is_separator)
        self.remove_button.setEnabled(has_list_selection)
        self.up_button.setEnabled(row > 0)
        self.down_button.setEnabled(0 <= row < self.list_widget.count() - 1)
        self.add_button.setEnabled(bool(self.tree_view.selected_favourites()))

    def favourites(self):
        return normalise_favourites(
            [
                normalise_favourite(self.list_widget.item(row).data(QT_USER_ROLE))
                for row in range(self.list_widget.count())
            ]
        )
