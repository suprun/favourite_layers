import os

from qgis.PyQt.QtCore import QCoreApplication, QLocale, QTranslator
from qgis.PyQt.QtWidgets import QMenu, QToolButton

from .icons import layer_icon, settings_icon, toolbar_icon
from .layer_tools import add_favourite_to_project_with_iface
from .qt_compat import QAction, QTOOL_BUTTON_INSTANT_POPUP, exec_qt
from .settings_dialog import SettingsDialog
from .storage import FavouriteLayerStore, is_separator


PLUGIN_CONTEXT = "FavouriteLayers"


def tr(message):
    return QCoreApplication.translate(PLUGIN_CONTEXT, message)


class FavouriteLayersPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.store = FavouriteLayerStore()
        self.toolbar = None
        self.toolbar_action = None
        self.tool_button = None
        self.menu = None
        self.layer_menu = None
        self.layer_menu_action = None
        self.translator = None
        self.favourites = []

    def initGui(self):
        self._load_translator()
        self.favourites = self.store.load()

        self.toolbar = self.iface.addToolBar(tr("Favourite Layers"))
        self.toolbar.setObjectName("FavouriteLayersToolBar")

        self.menu = QMenu(tr("Favourite Layers"), self.iface.mainWindow())
        self.tool_button = QToolButton(self.toolbar)
        self.tool_button.setIcon(toolbar_icon())
        self.tool_button.setToolTip(tr("Favourite layers"))
        self.tool_button.setPopupMode(QTOOL_BUTTON_INSTANT_POPUP)
        self.tool_button.setMenu(self.menu)
        self.toolbar_action = self.toolbar.addWidget(self.tool_button)

        self._add_layer_menu()
        self._rebuild_menu()

    def unload(self):
        self._remove_layer_menu()

        if self.translator is not None:
            QCoreApplication.removeTranslator(self.translator)
            self.translator = None

        if self.layer_menu is not None:
            self.layer_menu.deleteLater()
            self.layer_menu = None

        if self.menu is not None:
            self.menu.deleteLater()
            self.menu = None

        if self.toolbar_action is not None and self.toolbar is not None:
            try:
                self.toolbar.removeAction(self.toolbar_action)
            except Exception:
                pass
            self.toolbar_action.deleteLater()
            self.toolbar_action = None

        if self.tool_button is not None:
            try:
                self.tool_button.setParent(None)
                self.tool_button.deleteLater()
            except Exception:
                pass
            self.tool_button = None

        if self.toolbar is not None:
            try:
                self.iface.mainWindow().removeToolBar(self.toolbar)
            except Exception:
                pass
            self.toolbar.clear()
            self.toolbar.setParent(None)
            self.toolbar.deleteLater()
            self.toolbar = None

    def _add_layer_menu(self):
        qgis_layer_menu = self._qgis_layer_menu()
        if qgis_layer_menu is None:
            return

        self.layer_menu = QMenu(tr("Favourite Layers"), self.iface.mainWindow())
        self.layer_menu.setIcon(toolbar_icon())
        self.layer_menu_action = self.layer_menu.menuAction()

        before_action = self._fourth_layer_menu_action(qgis_layer_menu)
        if before_action is not None:
            qgis_layer_menu.insertMenu(before_action, self.layer_menu)
        else:
            qgis_layer_menu.addMenu(self.layer_menu)

    def _remove_layer_menu(self):
        if self.layer_menu_action is None:
            return

        qgis_layer_menu = self._qgis_layer_menu()
        if qgis_layer_menu is not None:
            try:
                qgis_layer_menu.removeAction(self.layer_menu_action)
            except Exception:
                pass
        self.layer_menu_action = None

    def _qgis_layer_menu(self):
        layer_menu_getter = getattr(self.iface, "layerMenu", None)
        if callable(layer_menu_getter):
            try:
                layer_menu = layer_menu_getter()
                if layer_menu is not None:
                    return layer_menu
            except Exception:
                pass

        menu_bar = self.iface.mainWindow().menuBar()
        for action in menu_bar.actions():
            text = action.text().replace("&", "").lower()
            if text == "layer":
                return action.menu()
        return None

    def _fourth_layer_menu_action(self, qgis_layer_menu):
        actions = qgis_layer_menu.actions()
        if len(actions) >= 4:
            return actions[3]
        return None

    def _load_translator(self):
        locale = QLocale.system().name()
        try:
            from qgis.core import QgsSettings

            user_locale = QgsSettings().value("locale/userLocale", "")
            if user_locale:
                locale = str(user_locale)
        except Exception:
            pass

        locale_candidates = []
        if locale:
            locale_candidates.append(locale)
            locale_candidates.append(locale.split("_")[0])

        for candidate in locale_candidates:
            path = os.path.join(
                self.plugin_dir,
                "i18n",
                "favourite_layers_{}.qm".format(candidate),
            )
            if os.path.exists(path):
                translator = QTranslator()
                if translator.load(path):
                    QCoreApplication.installTranslator(translator)
                    self.translator = translator
                    break

    def _rebuild_menu(self):
        self._populate_menu(self.menu)
        if self.layer_menu is not None:
            self._populate_menu(self.layer_menu)

    def _populate_menu(self, menu):
        menu.clear()

        if self.favourites:
            for favourite in self.favourites:
                if is_separator(favourite):
                    menu.addSeparator()
                    continue

                action = QAction(
                    layer_icon(favourite),
                    favourite.get("name") or favourite.get("uri"),
                    menu,
                )
                action.setToolTip(favourite.get("uri", ""))
                action.triggered.connect(
                    lambda checked=False, value=favourite: self._add_layer(value)
                )
                menu.addAction(action)
        else:
            empty_action = QAction(tr("No favourite layers"), menu)
            empty_action.setEnabled(False)
            menu.addAction(empty_action)

        menu.addSeparator()
        settings_action = QAction(settings_icon(), tr("Configure..."), menu)
        settings_action.triggered.connect(self._open_settings)
        menu.addAction(settings_action)

    def _open_settings(self):
        dialog = SettingsDialog(self.iface, self.favourites, self.iface.mainWindow())
        if exec_qt(dialog):
            self.favourites = dialog.favourites()
            self.store.save(self.favourites)
            self._rebuild_menu()

    def _add_layer(self, favourite):
        layer = add_favourite_to_project_with_iface(favourite, self.iface)
        if layer is not None:
            return

        self.iface.messageBar().pushWarning(
            tr("Favourite Layers"),
            tr("Could not add layer: {name}").format(
                name=favourite.get("name") or favourite.get("uri")
            ),
        )
