from qgis.PyQt.QtCore import QCoreApplication
from qgis.core import QgsProject, QgsRasterLayer, QgsVectorLayer

from .storage import is_separator

try:
    from qgis.core import QgsMapLayerType
except Exception:
    QgsMapLayerType = None

try:
    from qgis.core import Qgis
except Exception:
    Qgis = None

try:
    from qgis.core import QgsMeshLayer
except Exception:
    QgsMeshLayer = None

try:
    from qgis.core import QgsPointCloudLayer
except Exception:
    QgsPointCloudLayer = None

try:
    from qgis.core import QgsVectorTileLayer
except Exception:
    QgsVectorTileLayer = None

try:
    from qgis.core import QgsTiledSceneLayer
except Exception:
    QgsTiledSceneLayer = None


PLUGIN_CONTEXT = "FavouriteLayers"


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
            except Exception:
                pass

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
                except Exception:
                    pass

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
    except Exception:
        pass

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
        try:
            layer = factory()
        except Exception:
            continue
        if layer and layer.isValid():
            return layer

    return None


def add_favourite_to_project(favourite):
    return add_favourite_to_project_with_iface(favourite)


def add_favourite_to_project_with_iface(favourite, iface=None):
    if is_separator(favourite):
        return None

    if _is_vector_tile_favourite(favourite) and iface is not None:
        add_vector_tile_layer = getattr(iface, "addVectorTileLayer", None)
        if callable(add_vector_tile_layer):
            try:
                layer = add_vector_tile_layer(
                    favourite.get("uri") or "",
                    favourite.get("name") or favourite.get("uri") or tr("Layer"),
                )
            except Exception:
                layer = None
            if layer and layer.isValid():
                return layer

    layer = create_map_layer(favourite)
    if layer is None:
        return None

    QgsProject.instance().addMapLayer(layer)
    return layer
