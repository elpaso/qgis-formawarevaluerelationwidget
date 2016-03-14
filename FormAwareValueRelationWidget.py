# -*- coding: utf-8 -*-
"""
***************************************************************************
    Form Aware Value Relation Widget

    This plugin provides a "Form Value Relation" Widget that is a clone of
    QgsValueRelationWidgetWrapper that refreshes the related item values on
    every change in the form values and that passes the form values to the
    context. The expression is re-evaluated every time the form changes.

    An additional custom expression "CurrentFormValue" allow to read the form
    values from  the expression context.

    This plugin has been partially funded (50%) by ARPA Piemonte

    ---------------------
    Date                 : November 2015
    Copyright            : © 2015 ItOpen
    Contact              : info@itopen.it
    Author               : Alessandro Pasotti

***************************************************************************
*                                                                         *
*   This program is free software; you can redistribute it and/or modify  *
*   it under the terms of the GNU General Public License as published by  *
*   the Free Software Foundation; either version 2 of the License, or     *
*   (at your option) any later version.                                   *
*                                                                         *
***************************************************************************
"""
__author__ = 'Alessandro Pasotti'
__date__ = 'November 2015'
__copyright__ = '© 2015 ItOpen'


import os

from PyQt4.QtCore import *
from PyQt4.QtGui import *
from PyQt4 import uic

from qgis.core import *
from qgis.gui import *

DEBUG_FAVR_PLUGIN=True

def log(msg):
    if DEBUG_FAVR_PLUGIN:
        QgsMessageLog.logMessage(msg, 'FormAwareValueRelation')

def tr(text):
    # "Fixes" #3 ;-)
    return text
    #return QCoreApplication.translate('Widget', text)


def FormValueFunc(value, context, parent):
    """
    This function returns the current value of a field in the editor form.
    <h4>Example:</h4>
    <pre>
    CurrentFormValue('FIELD_NAME')
    </pre>
    <h4>Notes</h4>
    <ul>
    <li>
    This function  can only be used inside forms and it's particularly useful
    when used together with the custom widget <b>Form Value Relation</b>
    </li>
    <li>
    If the field does not exists the function returns an empty string.
    </li>
    </ul>
    """
    try:
        #log('FormValue(%s) %s' % (value, context.variable('FormValues').get(str(value), '')))
        return context.variable('FormValues').get(str(value), '')
    except (AttributeError, NameError):
        return ''


def register_functionV2(function, arg_count, group, usesgeometry=False, **kwargs):
    """
    Register a Python function to be used as a expression function.

    Functions should take (values, feature, parent) as args:

    Example:
        def myfunc(values, feature, parent):
            pass

    They can also shortcut naming feature and parent args by using *args
    if they are not needed in the function.

    Example:
        def myfunc(values, *args):
            pass

    Functions should return a value compatible with QVariant

    Eval errors can be raised using parent.setEvalErrorString("Error message")

    :param function:
    :param arg_count:
    :param group:
    :param usesgeometry:
    :return:
    """
    class QgsExpressionFunction(QgsExpression.Function):

        def __init__(self, func, name, args, group, helptext='', usesgeometry=False, expandargs=False):
            QgsExpression.Function.__init__(self, name, args, group, helptext, usesgeometry, isContextual=False)
            self.function = func
            self.expandargs = expandargs

        def funcV2(self, values, context, parent):
            try:
                if self.expandargs:
                    values.append(context)
                    values.append(parent)
                    return self.function(*values)
                else:
                    return self.function(values, context, parent)
            except Exception as ex:
                parent.setEvalErrorString(str(ex))
                return None

    helptemplate = string.Template("""<h3>$name function</h3><br>$doc""")
    name = kwargs.get('name', function.__name__)
    helptext = function.__doc__ or ''
    helptext = helptext.strip()
    expandargs = False

    if arg_count == "auto":
        # Work out the number of args we need.
        # Number of function args - 2.  The last two args are always feature, parent.
        args = inspect.getargspec(function).args
        number = len(args)
        arg_count = number - 2
        expandargs = True

    register = kwargs.get('register', True)
    if register and QgsExpression.isFunctionName(name):
        if not QgsExpression.unregisterFunction(name):
            msgtitle = QCoreApplication.translate("UserExpressions", "User expressions")
            msg = QCoreApplication.translate("UserExpressions", "The user expression {0} already exists and could not be unregistered.").format(name)
            log(msg)
            return None

    function.__name__ = name
    helptext = helptemplate.safe_substitute(name=name, doc=helptext)

    f = QgsExpressionFunction(function, name, arg_count, group, helptext, usesgeometry, expandargs)

    # This doesn't really make any sense here but does when used from a decorator context
    # so it can stay.
    if register:
        QgsExpression.registerFunction(f)
    return f



class FormAwareValueRelationWidgetPlugin():
    def __init__(self, iface):
        self.my_factory = FormAwareValueRelationWidgetFactory('Form Value Relation')
        QgsEditorWidgetRegistry.instance().registerWidget( 'formawarevaluerelationwidget', self.my_factory)
        # Add to iface to not gc
        iface._FormValueFunc = FormValueFunc
        iface._FormValueFuncEntry = register_functionV2(FormValueFunc, "auto", 'Custom', name="CurrentFormValue")
        iface._WidgetPlugin = self.my_factory

    def initGui(self):
        pass

    def unload(self):
        QgsExpression.unregisterFunction("CurrentFormValue")




class FormAwareValueRelationWidgetWrapper(QgsEditorWidgetWrapper):
    """
    This widget is a clone of QgsValueRelationWidgetWrapper with some important
    differences.

    When the widget is created:

    * the whole unfiltered features are loaded and cached
    * the form values of all the attributes are added to the context
    * the filtering against the expression happens every time the
      widget is refreshed
    * a signal is bound to the form changes and if the changed field
      is present in the filter expression, the features are filtered
      against the expression and the widget is refreshed

    """

    def __init__(self, vl, fieldIdx, editor, parent):
        """
        QgsVectorLayer* vl, int fieldIdx, QWidget* editor, QWidget* parent
        """
        self.mComboBox = None
        self.mListWidget = None
        self.mLineEdit = None
        self.mLayer = vl
        self.mFeature = None
        self.mCache = None
        super(FormAwareValueRelationWidgetWrapper, self).__init__(vl, fieldIdx, editor, parent)
        self.key_index = -1
        self.value_index = -1
        self.context = None
        self.expression = None
        # Re-create the cache if the layer is modified
        self.mLayer.layerModified.connect(self.createCache)
        self.completer_list = None # Caches completer elements
        self.completer = None # Store compler instance
        self.editor = editor


    def valid(self):
        return  isinstance(self.editor, QComboBox) or \
                isinstance(self.editor, QListWidget) or \
                isinstance(self.editor, QLineEdit)


    def get_cache_v_from_k(self, k):
        for f in self.mCache:
            if f.attributes()[self.key_index] == k:
                return f.attributes()[self.value_index]
        return k


    def get_cache_k_from_v(self, v):
        for f in self.mCache:
            if f.attributes()[self.value_index] == v:
                return f.attributes()[self.key_index]
        return v


    def representValue(self, value):
        """This function knows how to represent the value"""
        v = unicode(value)
        if isinstance(self.editor, QComboBox):
            v = self.get_cache_v_from_k(v)
        elif isinstance(self.editor, QListWidget):
            v = "{%s}" % ','.join([self.get_cache_v_from_k(_v) for _v in v.replace('{', '').replace('}', '').split(',')])
        elif isinstance(self.editor, QLineEdit):
            pass
        return v


    def value(self):
        v = ''
        if isinstance(self.editor, QComboBox):
            cbxIdx = self.editor.currentIndex()
            if cbxIdx > -1:
                v = self.editor.itemData( self.editor.currentIndex() )
        elif isinstance(self.editor, QListWidget):
            item = QListWidgetItem()
            selection = []
            for i in range(self.editor.count()):
                item = self.editor.item( i )
                if item.checkState() == Qt.Checked:
                    selection.append(str(item.data( Qt.UserRole )))
            v = '{%s}' %  ",".join(selection)
        elif isinstance(self.editor, QLineEdit):
            for f in self.mCache:
                if f.attributes()[self.value_index] == self.editor.text():
                    v = str(f.attributes()[self.key_index])
        else:
            log('WARNING: no widgets!')
        log("Returning value %s" % v)
        return v


    def createWidget(self, parent):
        """Store m references but do not use them! Use self.editor set in initWidget instead"""
        if hasattr(parent, 'attributeChanged'):
            self.parent().attributeChanged.connect(self.attributeChanged)
            #QObject.connect( self.parent(), SIGNAL("attributeChanged()"), self, SLOT("attributeChanged()"))
        if self.config( "AllowMulti" ) == '1':
            self.mListWidget = QListWidget( parent )
            QObject.connect( self.mListWidget, SIGNAL( "itemChanged( QListWidgetItem* )" ), self, SLOT( "valueChanged()" ) )
            return self.mListWidget
        elif self.config( "UseCompleter" ) == '1':
            self.mLineEdit = QgsFilterLineEdit( parent )
            return self.mLineEdit
        self.mComboBox = QComboBox( parent )
        QObject.connect( self.mComboBox, SIGNAL( "currentIndexChanged( int )" ), self, SLOT( "valueChanged()" ) )
        return self.mComboBox


    def initWidget(self, editor):
        log('initWidget')
        self.editor = editor
        self.createCache()
        self.populateWidget(editor)


    def attributeChanged(self, name, value):
        """
        Something has changed in the form
        """
        log('attributeChanged %s %s' % (name, value))
        if self.expression is not None \
            and ( name in self.expression.referencedColumns() \
                or self.expression.expression().find("'%s'" % name) != -1 ):
            self.populateWidget()
        else:
            log('attributeChanged: no expression or var is not in expression')


    def populateWidget(self, editor=None):
        """
        Filter possibly cached widget values
        """
        log('populateWidget')
        #if self.context is None:
        #    return

        if editor is None:
            editor = self.widget()
        self.editor = editor

        # If caching is disabled, recreates the cache every time
        self.createCache(self.config( "DisableCache" ) == '1')

        # Add Form variables to the scope, but only in form mode or it crashes!
        # editor is deleted with deleteLater :(
        is_form = isinstance(self.parent().parent(), QDialog)
        form_vars = {}
        if is_form:
            for c in self.parent().children():
                if isinstance(c, QgsEditorWidgetWrapper) and c != self and c.field().name().lower() != self.config( "Key" ).lower():
                    form_vars[c.field().name()] = c.value()

        # Last chance to find values
        if not is_form or 0 == len(form_vars):
            self.expression = None
            # Try with the table model  (crash!!!)
            #try:
                #for c in self.parent().parent().parent().parent().parent().findChildren(QgsEditorWidgetWrapper):
                    #if c.field().name().lower() != self.config( "Key" ).lower():
                        #form_vars[c.field().name()] = c.value()
            #except:
                #self.expression = None

        self.context.lastScope().setVariable('FormValues', form_vars)

        # Makes a filtered copy of the cache, keeping only attributes
        if self.expression is not None:
            log(self.expression.dump())
            cache = []
            for f in self.mCache:
                self.context.setFeature( f )
                if self.expression.evaluate( self.context ):
                    cache.append( (unicode(f.attributes()[self.key_index]), unicode(f.attributes()[self.value_index])))
        else:
            cache = [(str(f.attributes()[self.key_index]), str(f.attributes()[self.value_index])) for f in self.mCache]

        if self.config( "OrderByValue" ) == '1':
            cache.sort(key=lambda x: x[1])
        else:
            cache.sort(key=lambda x: x[0])


        if isinstance(self.editor, QComboBox):
            self.editor.clear()
            if self.config( "AllowNull" ) == '1':
                self.editor.addItem( tr( "(no selection)" ), '')
            for k,i in cache:
                #log("Adding items: %s %s" % (i,k))
                self.editor.addItem(i, k)
        elif isinstance(self.editor, QListWidget):
            self.editor.clear()
            for k,i in cache:
                item = QListWidgetItem(i)
                item.setData(Qt.UserRole, k)
                item.setCheckState(Qt.Unchecked)
                self.editor.addItem( item )
        elif isinstance(self.editor, QLineEdit):
            self.completer_list = QStringListModel( [i[1] for i in cache] )
            self.completer = QCompleter( self.completer_list, self.mLineEdit )
            self.completer.setCaseSensitivity( Qt.CaseInsensitive )
            self.editor.setCompleter(self.completer)
        else:
            log('WARNING: unknown widget!')


    def setValue(self, value):
        if isinstance(self.editor, QListWidget):
            checkList = str(value)[1:-1].split( ',' )
            for i in range(self.editor.count()):
                item = self.editor.item( i )
                item.setCheckState(Qt.Checked if str(item.data( Qt.UserRole )) in checkList else Qt.Unchecked)
        elif isinstance(self.editor, QComboBox):
            self.editor.setCurrentIndex( self.editor.findData( value ) )
        elif isinstance(self.editor, QLineEdit):
            for f in self.mCache:
                if str(f.attributes()[self.key_index]) == str(value):
                    self.editor.setText( str(f.attributes()[self.value_index]) )
                    break

    def createCache(self, force_creation=False):
        """
        Creates the cache
        """
        log('createCache called')
        if not (force_creation or self.mCache is None):
            return
        layer = QgsMapLayerRegistry.instance().mapLayer( self.config( "Layer" ) )
        cache = []
        attributes = []

        if layer is not None:
            ki = layer.fieldNameIndex( self.config( "Key" ) )
            vi = layer.fieldNameIndex( self.config( "Value" ) )

            context = QgsExpressionContext()
            context << QgsExpressionContextUtils.globalScope()
            context << QgsExpressionContextUtils.projectScope()
            context << QgsExpressionContextUtils.layerScope( layer )

            e = None
            if  self.config( "FilterExpression" ):
                e = QgsExpression( self.config( "FilterExpression" ) )
                if e.hasParserError() or not e.prepare( context ):
                    ki = -1

            if ki >= 0 and vi >= 0:
                attributes = [ki, vi]

            flags = QgsFeatureRequest.NoGeometry

            requiresAllAttributes = False
            if e:
                if e.needsGeometry():
                    flags = QgsFeatureRequest.NoFlags

                for field in e.referencedColumns():
                    if field == QgsFeatureRequest.AllAttributes:
                        requiresAllAttributes = True
                        break
                    idx = layer.fieldNameIndex( field )
                    if idx < 0:
                        continue
                    attributes.append(idx)

            fr = QgsFeatureRequest()
            fr.setFlags( flags )

            if not requiresAllAttributes:
                fr.setSubsetOfAttributes(attributes)

            for f in layer.getFeatures( fr ):
                cache.append( f )

            self.key_index = ki
            self.value_index = vi
            self.context = context
            self.expression = e

        self.mCache = cache
        log('createCache: created!')


class FormAwareValueRelationConfigDlg(QgsEditorConfigWidget):

    def __init__(self, vl, fieldIdx, parent):
        super(FormAwareValueRelationConfigDlg, self).__init__( vl, fieldIdx, parent )
        ui_path = os.path.join(os.path.dirname(__file__), 'gui/FormAwareValueRelationConfigDlg.ui')
        uic.loadUi(ui_path, self)
        self.mLayerName.setFilters( QgsMapLayerProxyModel.VectorLayer )
        QObject.connect( self.mLayerName, SIGNAL( "layerChanged( QgsMapLayer* )" ), self.mKeyColumn, SLOT( "setLayer( QgsMapLayer* )" ) )
        QObject.connect( self.mLayerName, SIGNAL( "layerChanged( QgsMapLayer* )" ), self.mValueColumn, SLOT( "setLayer( QgsMapLayer* )" ) )
        self.mEditExpression.clicked.connect(self.editExpression)


    def config(self):
        cfg = dict()
        cfg["Layer"] = self.mLayerName.currentLayer().id() if self.mLayerName.currentLayer() else ''
        cfg["Key"] = self.mKeyColumn.currentField()
        cfg["Value"] = self.mValueColumn.currentField()
        cfg["AllowMulti"] = '1' if self.mAllowMulti.isChecked() else '0'
        cfg["AllowNull"] = '1' if self.mAllowNull.isChecked() else '0'
        cfg["OrderByValue"] = '1' if self.mOrderByValue.isChecked() else '0'
        cfg["FilterExpression"] = self.mFilterExpression.toPlainText()
        cfg["UseCompleter"] = '1' if self.mUseCompleter.isChecked() else '0'
        cfg["DisableCache"] = '1' if self.mDisableCache.isChecked() else '0'

        return cfg

    def setConfig(self, config ):
        lyr = QgsMapLayerRegistry.instance().mapLayer( config.get( "Layer" ) )
        self.mLayerName.setLayer( lyr )
        self.mKeyColumn.setField( config.get( "Key" ) )
        self.mValueColumn.setField( config.get( "Value" ) )
        self.mAllowMulti.setChecked( config.get( "AllowMulti" ) == '1' )
        self.mAllowNull.setChecked( config.get( "AllowNull" ) == '1' )
        self.mOrderByValue.setChecked( config.get( "OrderByValue" ) == '1' )
        self.mFilterExpression.setPlainText( config.get( "FilterExpression" ) )
        self.mUseCompleter.setChecked( config.get( "UseCompleter" ) == '1' )
        self.mDisableCache.setChecked( config.get( "DisableCache" ) == '1' )


    def editExpression(self):
        vl = self.mLayerName.currentLayer()
        if not vl:
            return

        context = QgsExpressionContext()
        context << QgsExpressionContextUtils.globalScope()
        context << QgsExpressionContextUtils.projectScope()
        context << QgsExpressionContextUtils.layerScope( vl )

        dlg = QgsExpressionBuilderDialog( vl, self.mFilterExpression.toPlainText(), self, "generic", context )
        dlg.setWindowTitle( tr( "Edit filter expression" ) )

        if dlg.exec_() == QDialog.Accepted:
            self.mFilterExpression.setText( dlg.expressionBuilder().expressionText() )



class  FormAwareValueRelationWidgetFactory( QgsEditorWidgetFactory ):

    def __init__(self, name):
        super(FormAwareValueRelationWidgetFactory, self).__init__( name )
        self.wrapper = None
        self.dlg = None


    def create(self, vl, fieldIdx, editor, parent):
        # QgsVectorLayer* vl, int fieldIdx, QWidget* editor, QWidget* parent
        self.wrapper = FormAwareValueRelationWidgetWrapper( vl, fieldIdx, editor, parent )
        return self.wrapper


    def configWidget(self, vl, fieldIdx, parent ):
        self.dlg = FormAwareValueRelationConfigDlg( vl, fieldIdx, parent )
        return self.dlg


    def representValue(self, vl, fieldIdx, config, cache, value ):
        if self.wrapper is not None:
            return self.wrapper.representValue(value)
        return value


    def writeConfig(self, config, configElement, doc, layer, fieldIdx):
        configElement.setAttribute( "Layer", config.get( "Layer" ))
        configElement.setAttribute( "Key", config.get( "Key" ))
        configElement.setAttribute( "Value", config.get( "Value" ))
        configElement.setAttribute( "FilterExpression", config.get( "FilterExpression" ))
        configElement.setAttribute( "OrderByValue", config.get( "OrderByValue" ))
        configElement.setAttribute( "AllowMulti", config.get( "AllowMulti" ))
        configElement.setAttribute( "AllowNull", config.get( "AllowNull" ))
        configElement.setAttribute( "UseCompleter", config.get( "UseCompleter" ))
        configElement.setAttribute( "DisableCache", config.get( "DisableCache" ))


    def readConfig( self, configElement, layer, fieldIdx ):
        cfg = dict()
        cfg["Layer"] = configElement.attribute("Layer")
        cfg["Key"] = configElement.attribute("Key")
        cfg["Value"] = configElement.attribute("Value")
        cfg["AllowMulti"] = configElement.attribute("AllowMulti")
        cfg["AllowNull"] = configElement.attribute("AllowNull")
        cfg["OrderByValue"] = configElement.attribute("OrderByValue")
        cfg["FilterExpression"] = configElement.attribute("FilterExpression")
        cfg["UseCompleter"] = configElement.attribute("UseCompleter")
        cfg["DisableCache"] = configElement.attribute("DisableCache")
        return cfg

