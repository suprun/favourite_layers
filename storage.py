import json
import logging

from qgis.core import QgsSettings


SETTINGS_KEY = "favourite_layers/items"
ITEM_TYPE_LAYER = "layer"
ITEM_TYPE_SEPARATOR = "separator"
ADD_TRANSPARENCY_SLIDER_KEY = "add_transparency_slider"
DEFAULT_OSM_TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
DEFAULT_FAVOURITES = (
    {
        "item_type": ITEM_TYPE_LAYER,
        "name": "OpenStreetMap",
        "uri": "type=xyz&url={}".format(DEFAULT_OSM_TILE_URL),
        "provider_key": "wms",
        "layer_type": "RasterLayer",
        "path": DEFAULT_OSM_TILE_URL,
        "icon_name": "",
        ADD_TRANSPARENCY_SLIDER_KEY: False,
    },
)
LOGGER = logging.getLogger(__name__)


def is_separator(item):
    return isinstance(item, dict) and item.get("item_type") == ITEM_TYPE_SEPARATOR


def separator_item():
    return {
        "item_type": ITEM_TYPE_SEPARATOR,
        "name": "",
        "uri": "",
        "provider_key": "",
        "layer_type": "",
        "path": "",
        "icon_name": "",
    }


def add_transparency_slider_enabled(item):
    value = (item or {}).get(ADD_TRANSPARENCY_SLIDER_KEY, False)
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)


def normalise_favourite(item):
    item = item or {}
    if is_separator(item):
        return separator_item()

    return {
        "item_type": ITEM_TYPE_LAYER,
        "name": str(item.get("name") or ""),
        "uri": str(item.get("uri") or ""),
        "provider_key": str(item.get("provider_key") or ""),
        "layer_type": str(item.get("layer_type") or ""),
        "path": str(item.get("path") or ""),
        "icon_name": str(item.get("icon_name") or ""),
        ADD_TRANSPARENCY_SLIDER_KEY: add_transparency_slider_enabled(item),
    }


def normalise_favourites(items):
    values = []
    previous_was_separator = False

    for item in items or []:
        if not isinstance(item, dict):
            continue

        value = normalise_favourite(item)
        if is_separator(value):
            if previous_was_separator:
                continue
            values.append(value)
            previous_was_separator = True
            continue

        if not value.get("uri"):
            continue

        values.append(value)
        previous_was_separator = False

    while values and is_separator(values[-1]):
        values.pop()

    return values


def default_favourites():
    return normalise_favourites(DEFAULT_FAVOURITES)


class FavouriteLayerStore:
    def __init__(self):
        self.settings = QgsSettings()

    def load(self):
        if not self._settings_has_key():
            return default_favourites()

        raw = self.settings.value(SETTINGS_KEY, "[]")
        if not isinstance(raw, str):
            raw = "[]"

        try:
            values = json.loads(raw)
        except (TypeError, ValueError):
            values = []

        if not isinstance(values, list):
            return []

        return normalise_favourites(values)

    def save(self, favourites):
        values = normalise_favourites(favourites)
        self.settings.setValue(SETTINGS_KEY, json.dumps(values, ensure_ascii=False))

    def _settings_has_key(self):
        contains = getattr(self.settings, "contains", None)
        if callable(contains):
            try:
                return bool(contains(SETTINGS_KEY))
            except TypeError:
                LOGGER.debug("QgsSettings.contains rejected the settings key")

        all_keys = getattr(self.settings, "allKeys", None)
        if callable(all_keys):
            try:
                return SETTINGS_KEY in all_keys()
            except Exception:
                LOGGER.debug("Could not enumerate QgsSettings keys")

        return self.settings.value(SETTINGS_KEY, None) is not None
