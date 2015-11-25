# -*- coding: utf-8 -*-
"""
 This script initializes the plugin, making it known to QGIS.
"""


def classFactory(iface):
    from FormAwareValueRelationWidget import FormAwareValueRelationWidgetPlugin
    return FormAwareValueRelationWidgetPlugin(iface)

