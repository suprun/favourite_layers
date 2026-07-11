import os

from qgis.PyQt.QtGui import QIcon, QPalette
from qgis.PyQt.QtWidgets import QApplication
from qgis.core import QgsApplication


PLUGIN_DIR = os.path.dirname(__file__)


def local_icon(name):
    paths = (
        os.path.join(PLUGIN_DIR, "icons", name),
        os.path.join(PLUGIN_DIR, name),
    )
    for path in paths:
        if os.path.exists(path):
            icon = QIcon(path)
            if icon and not icon.isNull():
                return icon
    return QIcon()


def qgis_icon(*names):
    for name in names:
        if not name:
            continue
        if name.startswith(":") or os.path.exists(name):
            icon = QIcon(name)
            if icon and not icon.isNull():
                return icon
        candidates = [name]
        if not name.startswith("/"):
            candidates.append("/{}".format(name))
        for candidate in candidates:
            icon = QgsApplication.getThemeIcon(candidate)
            if icon and not icon.isNull():
                return icon
    return QIcon()


def _palette_role(name):
    color_role = getattr(QPalette, "ColorRole", None)
    if color_role is not None and hasattr(color_role, name):
        return getattr(color_role, name)
    return getattr(QPalette, name)


def is_dark_interface():
    app = QApplication.instance()
    if app is None:
        return False

    palette = app.palette()
    window = palette.color(_palette_role("Window"))
    text = palette.color(_palette_role("WindowText"))
    return window.lightness() < text.lightness()


def plugin_icon():
    icon = local_icon("icon.png")
    if icon and not icon.isNull():
        return icon
    return toolbar_icon()


def toolbar_icon():
    from qgis.core import QgsSettings
    settings = QgsSettings()
    icon_theme = settings.value("favourite_layers/icon_theme", "default")

    if icon_theme in ("yellow", "orange", "lime", "jade", "violet", "pink"):
        names = []
        if is_dark_interface():
            names.append("icon_{}-dark.svg".format(icon_theme))
        names.append("icon_{}.svg".format(icon_theme))
        
        for name in names:
            icon = local_icon(name)
            if icon and not icon.isNull():
                return icon

    names = ("icon-dark.svg", "icon.svg") if is_dark_interface() else ("icon.svg",)
    for name in names:
        icon = local_icon(name)
        if icon and not icon.isNull():
            return icon

    return qgis_icon(
        "/mActionAddLayer.svg",
        "/mActionAdd.svg",
        "/mIconLayerTree.svg",
    )


def settings_icon():
    return qgis_icon(
        "/mActionOptions.svg",
        "/propertyicons/settings.svg",
        "/mIconProperties.svg",
    )


def separator_icon():
    names = (
        ("separator-dark.svg", "separator.svg")
        if is_dark_interface()
        else ("separator.svg",)
    )
    for name in names:
        icon = local_icon(name)
        if icon and not icon.isNull():
            return icon

    return qgis_icon(
        "/mActionFormSeparator.svg",
        "/mActionSplitFeatures.svg",
        "/mActionAddBasicRectangle.svg",
    )


def add_separator_icon():
    names = (
        ("add_separator-dark.svg", "add_separator.svg")
        if is_dark_interface()
        else ("add_separator.svg",)
    )
    for name in names:
        icon = local_icon(name)
        if icon and not icon.isNull():
            return icon

    return separator_icon()


def layer_type_icon(layer_type):
    icons = {
        "VectorLayer": ("/mIconVectorLayer.svg", "/mIconVector.svg"),
        "RasterLayer": ("/mIconRasterLayer.svg", "/mIconRaster.svg"),
        "VectorTileLayer": ("/mIconVectorTileLayer.svg", "/mIconVectorTile.svg"),
        "MeshLayer": ("/mIconMeshLayer.svg",),
        "PointCloudLayer": ("/mIconPointCloudLayer.svg",),
        "AnnotationLayer": ("/mIconAnnotationLayer.svg",),
        "GroupLayer": ("/mIconLayerTree.svg",),
        "TiledSceneLayer": ("/mIconTiledSceneLayer.svg",),
    }
    return qgis_icon(*icons.get(layer_type, ("/mIconLayerTree.svg",)))


def layer_icon(favourite):
    provider_key = (favourite.get("provider_key") or "").lower()
    uri = (favourite.get("uri") or "").lower()
    layer_type = favourite.get("layer_type")

    if _is_vector_tile(provider_key, uri, layer_type):
        return vector_tile_icon()
    if _is_raster_tile(provider_key, uri):
        return raster_tile_icon()

    icon = qgis_icon(favourite.get("icon_name", ""))
    if icon and not icon.isNull():
        return icon

    provider_icons = {
        "wfs": ("/mIconWfs.svg",),
        "wcs": ("/mIconWcs.svg",),
        "wms": ("/mIconWms.svg", "/mIconRasterLayer.svg"),
        "arcgismapserver": (
            "/mIconArcGisMapServer.svg",
            "/mIconAms.svg",
            "/mIconRasterLayer.svg",
        ),
        "arcgisfeatureserver": (
            "/mIconArcGisFeatureServer.svg",
            "/mIconAfs.svg",
            "/mIconVectorLayer.svg",
        ),
        "postgres": ("/mIconPostgis.svg", "/mIconVectorLayer.svg"),
        "spatialite": ("/mIconSpatialite.svg", "/mIconVectorLayer.svg"),
        "mssql": ("/mIconMssql.svg", "/mIconVectorLayer.svg"),
        "oracle": ("/mIconOracle.svg", "/mIconVectorLayer.svg"),
        "ogr": ("/mIconVectorLayer.svg",),
        "gdal": ("/mIconRasterLayer.svg",),
    }

    icon = qgis_icon(*provider_icons.get(provider_key, ()))

    if icon and not icon.isNull():
        return icon

    return layer_type_icon(layer_type)


def _is_vector_tile(provider_key, uri, layer_type):
    return (
        layer_type == "VectorTileLayer" or
        provider_key in ("vectortile", "vector_tile", "vector_tiles") or
        "type=vector" in uri or
        "type=vector-tile" in uri or
        "vectortile" in uri or
        "vector_tile" in uri
    )


def _is_raster_tile(provider_key, uri):
    return (
        provider_key in ("xyz", "wmts") or
        "type=xyz" in uri or
        "type=wmts" in uri or
        "zmax=" in uri or
        "{z}" in uri
    )


def raster_tile_icon():
    icon = qgis_icon(
        ":/images/themes/default/mIconVectorTileLayer.svg",
        "/mIconVectorTileLayer.svg",
    )
    if icon and not icon.isNull():
        return icon

    icon = local_icon("raster_tiles.svg")
    if icon and not icon.isNull():
        return icon

    return qgis_icon(
        "/mIconXyz.svg",
        "/mIconXyzTiles.svg",
        "/mIconWms.svg",
        "/mIconRasterLayer.svg",
    )


def vector_tile_icon():
    icon = qgis_icon(
        ":/images/themes/default/mIconXyz.svg",
        "/mIconXyz.svg",
    )
    if icon and not icon.isNull():
        return icon

    icon = local_icon("vector_tiles.svg")
    if icon and not icon.isNull():
        return icon

    return qgis_icon(
        "/mIconVectorTileLayer.svg",
        "/mIconVectorTile.svg",
        "/mIconVectorLayer.svg",
    )
