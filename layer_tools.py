import logging

from qgis.PyQt.QtCore import QCoreApplication
from qgis.core import QgsProject, QgsRasterLayer, QgsVectorLayer

from .storage import add_transparency_slider_enabled, is_separator

try:
    from qgis.core import QgsMapLayerType
except ImportError:
    QgsMapLayerType = None

try:
    from qgis.core import Qgis
except ImportError:
    Qgis = None

try:
    from qgis.core import QgsMeshLayer
except ImportError:
    QgsMeshLayer = None

try:
    from qgis.core import QgsPointCloudLayer
except ImportError:
    QgsPointCloudLayer = None

try:
    from qgis.core import QgsVectorTileLayer
except ImportError:
    QgsVectorTileLayer = None

try:
    from qgis.core import QgsTiledSceneLayer
except ImportError:
    QgsTiledSceneLayer = None


PLUGIN_CONTEXT = "FavouriteLayers"
LOGGER = logging.getLogger(__name__)


def tr(message):
    return QCoreApplication.translate(PLUGIN_CONTEXT, message)


LAYER_TYPE_CHOICES = (
    ("VectorLayer", "Vector layer"),
    ("RasterLayer", "Raster layer"),
    ("VectorTileLayer", "Vector tile layer"),
    ("MeshLayer", "Mesh layer"),
    ("PointCloudLayer", "Point cloud layer"),
    ("AnnotationLayer", "Annotation layer"),
    ("GroupLayer", "Group layer"),
    ("TiledSceneLayer", "Tiled scene layer"),
)


def _enum_value_map():
    values = {}

    old_names = (
        "VectorLayer",
        "RasterLayer",
        "PluginLayer",
        "MeshLayer",
        "VectorTileLayer",
        "AnnotationLayer",
        "PointCloudLayer",
        "GroupLayer",
        "TiledSceneLayer",
    )
    for name in old_names:
        if QgsMapLayerType is not None and hasattr(QgsMapLayerType, name):
            try:
                values[int(getattr(QgsMapLayerType, name))] = name
            except (TypeError, ValueError, OverflowError):
                LOGGER.debug("Could not convert a legacy layer type enum")

    if Qgis is not None and hasattr(Qgis, "LayerType"):
        new_names = {
            "Vector": "VectorLayer",
            "Raster": "RasterLayer",
            "Plugin": "PluginLayer",
            "Mesh": "MeshLayer",
            "VectorTile": "VectorTileLayer",
            "Annotation": "AnnotationLayer",
            "PointCloud": "PointCloudLayer",
            "Group": "GroupLayer",
            "TiledScene": "TiledSceneLayer",
        }
        for enum_name, layer_name in new_names.items():
            if hasattr(Qgis.LayerType, enum_name):
                try:
                    values[int(getattr(Qgis.LayerType, enum_name))] = layer_name
                except (TypeError, ValueError, OverflowError):
                    LOGGER.debug("Could not convert a current layer type enum")

    return values


def layer_type_to_name(layer_type):
    if layer_type is None:
        return ""

    aliases = {
        "Vector": "VectorLayer",
        "Raster": "RasterLayer",
        "Plugin": "PluginLayer",
        "Mesh": "MeshLayer",
        "VectorTile": "VectorTileLayer",
        "Annotation": "AnnotationLayer",
        "PointCloud": "PointCloudLayer",
        "Group": "GroupLayer",
        "TiledScene": "TiledSceneLayer",
    }

    if isinstance(layer_type, str):
        return aliases.get(layer_type, layer_type)

    try:
        return _enum_value_map().get(int(layer_type), "")
    except (TypeError, ValueError, OverflowError):
        LOGGER.debug("Could not convert a layer type value")

    enum_name = str(layer_type).split(".")[-1]
    return aliases.get(enum_name, enum_name)


def _is_vector_tile_favourite(favourite):
    layer_type = layer_type_to_name(favourite.get("layer_type"))
    provider = (favourite.get("provider_key") or "").lower()
    return layer_type == "VectorTileLayer" or provider in (
        "vectortile",
        "vector_tile",
        "vector_tiles",
    )


def _create_vector_tile_layer(uri, name):
    if QgsVectorTileLayer is None:
        return None
    try:
        return QgsVectorTileLayer(uri, name)
    except Exception:
        LOGGER.debug("Could not construct a vector tile layer")
        return None


def create_map_layer(favourite):
    if is_separator(favourite):
        return None

    name = favourite.get("name") or favourite.get("uri") or tr("Layer")
    uri = favourite.get("uri") or ""
    provider_key = favourite.get("provider_key") or ""
    layer_type = layer_type_to_name(favourite.get("layer_type"))

    factories = []
    if layer_type == "VectorLayer":
        factories.append(lambda: QgsVectorLayer(uri, name, provider_key))
    elif layer_type == "RasterLayer":
        factories.append(lambda: QgsRasterLayer(uri, name, provider_key))
    elif layer_type == "VectorTileLayer" and QgsVectorTileLayer is not None:
        factories.append(lambda: _create_vector_tile_layer(uri, name))
    elif layer_type == "MeshLayer" and QgsMeshLayer is not None:
        factories.append(lambda: QgsMeshLayer(uri, name, provider_key))
    elif layer_type == "PointCloudLayer" and QgsPointCloudLayer is not None:
        factories.append(lambda: QgsPointCloudLayer(uri, name, provider_key))
    elif layer_type == "TiledSceneLayer" and QgsTiledSceneLayer is not None:
        factories.append(lambda: QgsTiledSceneLayer(uri, name, provider_key))

    provider = provider_key.lower()
    if not factories:
        if provider in ("wms", "gdal", "arcgismapserver"):
            factories.append(lambda: QgsRasterLayer(uri, name, provider_key))
        elif provider in ("vectortile", "vector_tile", "vector_tiles"):
            if QgsVectorTileLayer is not None:
                factories.append(lambda: _create_vector_tile_layer(uri, name))
        elif provider in ("ept", "pdal") and QgsPointCloudLayer is not None:
            factories.append(lambda: QgsPointCloudLayer(uri, name, provider_key))
        else:
            factories.append(lambda: QgsVectorLayer(uri, name, provider_key))
            factories.append(lambda: QgsRasterLayer(uri, name, provider_key))

    for factory in factories:
        layer = None
        try:
            layer = factory()
        except Exception:
            LOGGER.debug("A map layer factory could not construct the layer")
        if layer and layer.isValid():
            return layer

    return None


def add_favourite_to_project(favourite):
    return add_favourite_to_project_with_iface(favourite)


def _add_transparency_slider(layer, iface=None):
    try:
        count = int(layer.customProperty("embeddedWidgets/count", 0) or 0)
        for index in range(max(0, count)):
            if layer.customProperty("embeddedWidgets/{}/id".format(index)) == (
                "transparency"
            ):
                break
        else:
            count = max(0, count)
            layer.setCustomProperty("embeddedWidgets/count", count + 1)
            layer.setCustomProperty(
                "embeddedWidgets/{}/id".format(count),
                "transparency",
            )
    except Exception:
        LOGGER.debug("Could not configure the layer transparency widget")
        return

    node = QgsProject.instance().layerTreeRoot().findLayer(layer.id())
    if node is not None:
        node.setExpanded(True)

    if iface is None:
        return
    layer_tree_view = getattr(iface, "layerTreeView", None)
    if not callable(layer_tree_view):
        return
    try:
        refresh_layer = getattr(layer_tree_view(), "refreshLayerSymbology", None)
        if callable(refresh_layer):
            refresh_layer(layer.id())
    except Exception:
        LOGGER.debug("Could not refresh layer symbology")


def _load_vector_tile_default_style(layer):
    try:
        layer.loadDefaultStyle()
    except Exception:
        LOGGER.debug("Could not load the vector tile default style")


def add_favourite_to_project_with_iface(favourite, iface=None):
    if is_separator(favourite):
        return None

    layer = create_map_layer(favourite)
    if layer is None:
        return None

    if _is_vector_tile_favourite(favourite):
        _load_vector_tile_default_style(layer)

    QgsProject.instance().addMapLayer(layer)
    if add_transparency_slider_enabled(favourite):
        _add_transparency_slider(layer, iface)
    return layer
