from qgis.PyQt.QtCore import QCoreApplication


PLUGIN_CONTEXT = "FavouriteLayers"
FAVOURITE_LAYER_MIME = "application/x-qgis-favourite-layer"


def tr(message):
    return QCoreApplication.translate(PLUGIN_CONTEXT, message)
