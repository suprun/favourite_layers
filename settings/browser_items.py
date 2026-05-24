from qgis.PyQt.QtCore import QModelIndex
from qgis.core import QgsDataItem

from ..qt_compat import QT_DISPLAY_ROLE

try:
    from qgis.core import Qgis
except Exception:
    Qgis = None

try:
    from qgis.core import QgsLayerItem
except Exception:
    QgsLayerItem = None

from ..layer_tools import layer_type_to_name
from ..storage import normalise_favourite


def _safe_call(obj, method_name, default=""):
    method = getattr(obj, method_name, None)
    if not callable(method):
        return default
    try:
        value = method()
    except Exception:
        return default
    if value is None:
        return default
    return value


def _enum_name(value, enum_owner=None, aliases=None):
    if value is None:
        return ""

    aliases = aliases or {}
    if isinstance(value, str):
        return aliases.get(value, value)

    if enum_owner is not None:
        for name in dir(enum_owner):
            if name.startswith("_"):
                continue
            try:
                enum_value = getattr(enum_owner, name)
                if int(enum_value) == int(value):
                    return aliases.get(name, name)
            except Exception:
                continue

    name = str(value).split(".")[-1]
    return aliases.get(name, name)


def _data_item_type_name(item):
    item_type = _safe_call(item, "type", None)
    aliases = {"Favorites": "Favorite"}
    name = _enum_name(item_type, QgsDataItem, aliases)

    if Qgis is not None and hasattr(Qgis, "BrowserItemType"):
        name = _enum_name(item_type, Qgis.BrowserItemType, aliases) or name

    return name


def _provider_key(item):
    return str(_safe_call(item, "providerKey", "") or "")


def _item_uri(item):
    return str(_safe_call(item, "uri", "") or "")


def _item_path(item):
    return str(_safe_call(item, "path", "") or "")


def _item_icon_name(item):
    icon_name = str(_safe_call(item, "iconName", "") or "")
    if icon_name:
        return icon_name
    return str(_safe_call(item, "iconPath", "") or "")


def _item_name(item, model=None, index=QModelIndex()):
    name = str(_safe_call(item, "name", "") or "")
    if name:
        return name
    if model is not None and index.isValid():
        return str(model.data(index, QT_DISPLAY_ROLE) or "")
    return ""


def is_layer_item(item):
    if item is None:
        return False
    if QgsLayerItem is not None and isinstance(item, QgsLayerItem):
        return True
    return _data_item_type_name(item) == "Layer"


def is_filesystem_item(item):
    if item is None:
        return False

    type_name = _data_item_type_name(item)
    if type_name in ("Directory", "Favorite"):
        return True

    provider = _provider_key(item).lower()
    class_name = item.__class__.__name__.lower()
    return provider in ("file", "filesystem") or "directory" in class_name


def browser_item_to_favourite(model, index):
    item = model.dataItem(index)
    favourite = mime_uri_to_favourite(item, model, index)
    if favourite.get("uri"):
        return favourite

    layer_type = layer_type_to_name(_safe_call(item, "mapLayerType", ""))
    if not layer_type:
        layer_type = browser_layer_type_to_name(item)
    return normalise_favourite(
        {
            "name": _item_name(item, model, index),
            "uri": _item_uri(item),
            "provider_key": _provider_key(item),
            "layer_type": layer_type,
            "path": _item_path(item),
            "icon_name": _item_icon_name(item),
        }
    )


def mime_uri_layer_type_to_name(layer_type):
    values = {
        "vector": "VectorLayer",
        "raster": "RasterLayer",
        "mesh": "MeshLayer",
        "pointcloud": "PointCloudLayer",
        "point-cloud": "PointCloudLayer",
        "vector-tile": "VectorTileLayer",
        "tiled-scene": "TiledSceneLayer",
        "plugin": "PluginLayer",
    }
    return values.get(str(layer_type or "").lower(), "")


def mime_uri_to_favourite(item, model=None, index=QModelIndex()):
    mime_uris = _safe_call(item, "mimeUris", [])
    if not mime_uris:
        return normalise_favourite({})

    for mime_uri in mime_uris:
        is_valid = getattr(mime_uri, "isValid", None)
        if callable(is_valid):
            try:
                if not is_valid():
                    continue
            except Exception:
                continue

        uri = str(getattr(mime_uri, "uri", "") or "")
        if not uri:
            continue

        return normalise_favourite(
            {
                "name": str(getattr(mime_uri, "name", "") or "")
                or _item_name(item, model, index),
                "uri": uri,
                "provider_key": str(getattr(mime_uri, "providerKey", "") or "")
                or _provider_key(item),
                "layer_type": mime_uri_layer_type_to_name(
                    getattr(mime_uri, "layerType", "")
                )
                or layer_type_to_name(_safe_call(item, "mapLayerType", ""))
                or browser_layer_type_to_name(item),
                "path": _item_path(item),
                "icon_name": _item_icon_name(item),
            }
        )

    return normalise_favourite({})


def browser_layer_type_to_name(item):
    layer_type = _safe_call(item, "layerType", "")
    aliases = {
        "Vector": "VectorLayer",
        "Raster": "RasterLayer",
        "Plugin": "PluginLayer",
        "Mesh": "MeshLayer",
        "VectorTile": "VectorTileLayer",
        "PointCloud": "PointCloudLayer",
        "TiledScene": "TiledSceneLayer",
    }

    if isinstance(layer_type, str):
        return aliases.get(layer_type, layer_type_to_name(layer_type))

    def enum_layer_type_name(enum_owner):
        for enum_name, value_name in aliases.items():
            if not hasattr(enum_owner, enum_name):
                continue
            try:
                if int(getattr(enum_owner, enum_name)) == int(layer_type):
                    return value_name
            except Exception:
                continue
        return ""

    enum_owners = []
    if QgsLayerItem is not None:
        if hasattr(QgsLayerItem, "LayerType"):
            enum_owners.append(QgsLayerItem.LayerType)
        enum_owners.append(QgsLayerItem)
    if Qgis is not None and hasattr(Qgis, "BrowserLayerType"):
        enum_owners.append(Qgis.BrowserLayerType)

    for enum_owner in enum_owners:
        name = enum_layer_type_name(enum_owner)
        if name:
            return name

    return layer_type_to_name(layer_type)
