from qgis.PyQt.QtCore import QCoreApplication, Qt
from qgis.PyQt.QtWidgets import QDialog, QVBoxLayout, QTextBrowser, QDialogButtonBox
from ..qt_compat import QDIALOG_BUTTON_OK

PLUGIN_CONTEXT = "FavouriteLayers"
FAVOURITE_LAYER_MIME = "application/x-qgis-favourite-layer"


def tr(message):
    return QCoreApplication.translate(PLUGIN_CONTEXT, message)


class SourceInfoDialog(QDialog):
    def __init__(self, favourite, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Source Information"))
        self.resize(550, 380)

        layout = QVBoxLayout(self)

        self.text_browser = QTextBrowser(self)
        self.text_browser.setOpenExternalLinks(True)
        self.text_browser.setStyleSheet("background: transparent; border: none;")

        name = favourite.get("name") or favourite.get("uri") or tr("Unknown")
        uri = favourite.get("uri") or ""
        provider = favourite.get("provider_key") or tr("Unknown")
        layer_type = favourite.get("layer_type") or tr("Unknown")
        path = favourite.get("path") or ""

        # Формуємо HTML вміст
        html = f"""
        <h3>{tr("Layer Source Details")}</h3>
        <table width="100%" cellpadding="6" cellspacing="0" style="font-family: sans-serif; font-size: 13px; border-collapse: collapse;">
            <tr>
                <td style="font-weight: bold; width: 120px; border-bottom: 1px solid gray;">{tr("Name")}:</td>
                <td style="border-bottom: 1px solid gray;">{name}</td>
            </tr>
            <tr>
                <td style="font-weight: bold; border-bottom: 1px solid gray;">{tr("Layer Type")}:</td>
                <td style="border-bottom: 1px solid gray;">{layer_type}</td>
            </tr>
            <tr>
                <td style="font-weight: bold; border-bottom: 1px solid gray;">{tr("Provider")}:</td>
                <td style="border-bottom: 1px solid gray;">{provider}</td>
            </tr>
            <tr>
                <td style="font-weight: bold; border-bottom: 1px solid gray;">{tr("Path")}:</td>
                <td style="border-bottom: 1px solid gray;">{path if path else tr("None")}</td>
            </tr>
            <tr>
                <td style="font-weight: bold; vertical-align: top; border-bottom: 1px solid gray;">{tr("Source URI")}:</td>
                <td style="word-break: break-all; font-family: monospace; border-bottom: 1px solid gray;">{uri}</td>
            </tr>
        </table>
        """
        self.text_browser.setHtml(html)
        layout.addWidget(self.text_browser)

        buttons = QDialogButtonBox(QDIALOG_BUTTON_OK)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
