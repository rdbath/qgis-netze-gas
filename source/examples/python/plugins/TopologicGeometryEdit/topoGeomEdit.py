# -*- coding: utf-8 -*-
"""
/***************************************************************************
 TopologicGeometryEdit
                                 A QGIS plugin
 This plugin adds functions to edit topological linked geometries in one step
                              -------------------
        begin                : 2017-09-21
        git sha              : $Format:%H$
        copyright            : (C) 2017 by H.Fischer/Mettenmeier GmbH
        email                : holger.fischer@mettenmeier.de
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
from PyQt4.QtCore import QSettings, QTranslator, qVersion, QCoreApplication, QObject, SIGNAL
from PyQt4.QtGui import QAction, QIcon, QMessageBox
from qgis.core import QgsFeatureRequest, QgsDataSourceURI, QgsWKBTypes, QGis, QgsVectorLayer, QgsFeature, QgsGeometry
# Initialize Qt resources from file resources.py
import resources
# Import the code for the dialog
from topoGeomEdit_dialog import TopologicGeometryEditDialog
# Import the topology connector class
from TopologyConnector import TopologyConnector
import os.path
from qgis.utils import iface
from PyQt4.Qt import QColor


class TopologicGeometryEdit:
    """QGIS Plugin Implementation."""

    def __init__(self, iface):
        """Constructor.

        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        """
        # Save reference to the QGIS interface
        self.iface = iface
        # initialize plugin directory
        self.plugin_dir = os.path.dirname(__file__)
        # initialize locale
        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'TopologicGeometryEdit_{}.qm'.format(locale))

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)

            if qVersion() > '4.3.3':
                QCoreApplication.installTranslator(self.translator)


        # Declare instance attributes
        self.actions = []
        self.menu = self.tr(u'&Topologic Geometry Edit')
        # TODO: We are going to let the user set this up in a future iteration
        self.toolbar = self.iface.addToolBar(u'TopologicGeometryEdit')
        self.toolbar.setObjectName(u'TopologicGeometryEdit')
        # declare slot variables
        self.selectedLayer = None
        self.selectedFeature = None
        
        # check if already a layer is selected on Plugin Load (probably only during testing) 
        currentLayer = self.iface.mapCanvas().currentLayer()
        if currentLayer:
            self.listen_layerChanged(currentLayer)
        # connect to geometry changes (test)
        QObject.connect(self.iface.mapCanvas(), SIGNAL("currentLayerChanged(QgsMapLayer *)"), self.listen_layerChanged)
        
        # set db connector for topology tests
        self.topologyConnector = TopologyConnector()

    # noinspection PyMethodMayBeStatic
    def tr(self, message):
        """Get the translation for a string using Qt translation API.

        We implement this ourselves since we do not inherit QObject.

        :param message: String for translation.
        :type message: str, QString

        :returns: Translated version of message.
        :rtype: QString
        """
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return QCoreApplication.translate('TopologicGeometryEdit', message)


    def add_action(
        self,
        icon_path,
        text,
        callback,
        enabled_flag=True,
        add_to_menu=True,
        add_to_toolbar=True,
        status_tip=None,
        whats_this=None,
        parent=None):
        """Add a toolbar icon to the toolbar.

        :param icon_path: Path to the icon for this action. Can be a resource
            path (e.g. ':/plugins/foo/bar.png') or a normal file system path.
        :type icon_path: str

        :param text: Text that should be shown in menu items for this action.
        :type text: str

        :param callback: Function to be called when the action is triggered.
        :type callback: function

        :param enabled_flag: A flag indicating if the action should be enabled
            by default. Defaults to True.
        :type enabled_flag: bool

        :param add_to_menu: Flag indicating whether the action should also
            be added to the menu. Defaults to True.
        :type add_to_menu: bool

        :param add_to_toolbar: Flag indicating whether the action should also
            be added to the toolbar. Defaults to True.
        :type add_to_toolbar: bool

        :param status_tip: Optional text to show in a popup when mouse pointer
            hovers over the action.
        :type status_tip: str

        :param parent: Parent widget for the new action. Defaults None.
        :type parent: QWidget

        :param whats_this: Optional text to show in the status bar when the
            mouse pointer hovers over the action.

        :returns: The action that was created. Note that the action is also
            added to self.actions list.
        :rtype: QAction
        """

        # Create the dialog (after translation) and keep reference
        self.dlg = TopologicGeometryEditDialog()

        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            self.toolbar.addAction(action)

        if add_to_menu:
            self.iface.addPluginToMenu(
                self.menu,
                action)

        self.actions.append(action)

        return action

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""

        icon_path = ':/plugins/TopologicGeometryEdit/icon.png'
        
        self.add_action(
            icon_path,
            text=self.tr(u'Highlight topology connection'),
            callback=self.findTopology,
            parent=self.iface.mainWindow())

    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        for action in self.actions:
            self.iface.removePluginMenu(
                self.tr(u'&Topologic Geometry Edit'),
                action)
            self.iface.removeToolBarIcon(action)
        # remove the toolbar
        del self.toolbar


    def checkSelection(self):    
        
        toolname = "CoordinateList"

        # check that a layer is selected
        layer = self.iface.mapCanvas().currentLayer()
        if not layer:
          QMessageBox.information(None, toolname, "A layer must be selected")
          return
        
        # check that the selected layer is a postgis one
        if layer.providerType() != 'postgres':
          QMessageBox.information(None, toolname, "A PostGIS layer must be selected")
          return
      
        uri = QgsDataSourceURI( layer.source() )

        # get the layer schema
        schema = str(uri.schema())
        if not schema:
          QMessageBox.information(None, toolname, "Selected layer must be a table, not a view\n"
            "(no schema set in datasource " + str(uri.uri()) + ")")
          return
      
        # get the layer table
        table = str(uri.table())
        if not table:
          QMessageBox.information(None, toolname, "Selected layer must be a table, not a view\n"
            "(no table set in datasource)")
          return
        
        # get the selected features
        selected = layer.selectedFeatures()
        if not selected:
          QMessageBox.information(None, toolname, "Select the geometry you want to see the coordinate list from")
          return
        
        return selected
        
    def findTopology(self):
        '''
        find topological related geometries of selected geometry
        '''
        selected = self.checkSelection()
        
        if selected:
            aFeature = selected[0]
            #initialLayer = iface.mapCanvas().currentLayer()
            conFeaturesList = self.connectedFeatures(aFeature)
            if conFeaturesList:
                # add connected Features to selection set and change colour to red
                #iface.mapCanvas().setSelectionColor( QColor("red") )
                # we check only house connections so far
                drawLayer = None
                for aLayer in iface.mapCanvas().layers():
                    if aLayer.name() == 'anschlussltg_abschnitt':
                        #drawLayer = aLayer
                        #iface.setActiveLayer(aLayer)
                        #iface.mapCanvas().setSelectionColor( QColor("red") )
                        #iface.legendInterface().setCurrentLayer(aLayer)
                        qFeaturesList = []
                        for aSystemId in conFeaturesList:
                            request = QgsFeatureRequest().setFilterExpression(u'"system_id" = ' + str(aSystemId))
                            for aQsFeature in aLayer.getFeatures( request ):
                                qFeaturesList.append(aQsFeature.id())
                        aLayer.setSelectedFeatures(qFeaturesList)
                        break
                
                #drawLayer.setSelectedFeatures(conFeaturesList)
                #dBox = drawLayer.boundingBoxOfSelected()
                #iface.mapCanvas().setExtent(dBox)
                #iface.mapCanvas().refreshAllLayers()
                iface.mapCanvas().refresh()
                #iface.setActiveLayer(initialLayer)
                #iface.mapCanvas().setSelectionColor( QColor("yellow") )
                
        return True
                    
    def connectedFeatures(self, aFeature):
        '''
        returns all Features topological connected to AFeature
        '''
        if aFeature:
            aGeometry = aFeature.geometry()
        
            # check different geometry types
            aType = aGeometry.wkbType()
            if aType == QGis.WKBPoint:
                topoNodeId = self.topologyConnector.get_nodeid_for_point(aFeature)
                #
                if topoNodeId:
                    connectedEdgeIds = self.topologyConnector.all_edges_for_node(topoNodeId)
                    
                    relatedLineIds = self.topologyConnector.get_lines_for_edgeids(connectedEdgeIds)
                    
                    return relatedLineIds
            
    def listen_layerChanged(self, layer):
        # listens to change of current layer
        #QObject.connect(layer, SIGNAL("geometryChanged(QgsFeatureId, const QgsGeometry &)"), self.listen_geometryChange) # does not work
        if layer == self.selectedLayer:
            return
        else:
            # disconnect old listener
            if self.selectedLayer:
                self.selectedLayer.geometryChanged.disconnect(self.listen_geometryChange)
            # in any case store new selected layer (can be None)
            self.selectedLayer = layer
            
            if layer:
                # connect to signal
                layer.geometryChanged.connect(self.listen_geometryChange)
    
    def listen_geometryChange(self, fid, cGeometry):
        # listens to geometry changes
        toolname = "Geometry Changed"
        
        if not fid:
            return
        
        allSelectedFeatures = []
        for aSelectedFeature in self.selectedLayer.getFeatures(QgsFeatureRequest(fid)):
            allSelectedFeatures.append(aSelectedFeature)
        
        if allSelectedFeatures[0]:
            self.selectedFeature = allSelectedFeatures[0]
            #QMessageBox.information(None, toolname, "Geometry was changed for " + str(self.selectedFeature.id()))
            aGeometry = self.selectedFeature.geometry()
            
    def run(self):
        """Run method that performs all the real work"""
        # show the dialog
        self.dlg.show()
        # Run the dialog event loop
        result = self.dlg.exec_()
        # See if OK was pressed
        if result:
            # Do something useful here - delete the line containing pass and
            # substitute with your code.
            pass