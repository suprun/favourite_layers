from qgis.PyQt.QtCore import QSortFilterProxyModel

from .browser_items import browser_item_to_favourite, is_layer_item


class BrowserLayerProxyModel(QSortFilterProxyModel):
    def filterAcceptsRow(self, row, parent):
        source_model = self.sourceModel()
        source_index = source_model.index(row, 0, parent)
        if not source_index.isValid():
            return False

        if parent.isValid():
            parent_item = source_model.dataItem(parent)
            if is_layer_item(parent_item):
                return False

        item = source_model.dataItem(source_index)
        if item is None:
            return False
        if is_layer_item(item):
            return True

        if self._may_have_layer_children(source_index):
            return True

        for child_row in range(source_model.rowCount(source_index)):
            if self.filterAcceptsRow(child_row, source_index):
                return True

        return False

    def _may_have_layer_children(self, source_index):
        source_model = self.sourceModel()
        try:
            if source_model.canFetchMore(source_index):
                return True
        except Exception:
            pass

        try:
            if source_model.hasChildren(source_index):
                return True
        except Exception:
            pass

        try:
            if source_model.rowCount(source_index) > 0:
                return True
        except Exception:
            pass

        item = source_model.dataItem(source_index)
        try:
            if item and item.hasChildren():
                return True
        except Exception:
            pass

        return False

    def data_item(self, proxy_index):
        if not proxy_index.isValid():
            return None
        source_index = self.mapToSource(proxy_index)
        return self.sourceModel().dataItem(source_index)

    def is_addable(self, proxy_index):
        if not proxy_index.isValid():
            return False
        return is_layer_item(self.data_item(proxy_index))

    def favourite_from_proxy_index(self, proxy_index):
        source_index = self.mapToSource(proxy_index)
        return browser_item_to_favourite(self.sourceModel(), source_index)
