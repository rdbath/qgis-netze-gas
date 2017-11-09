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
from qgis.core import QgsFeatureRequest, QgsDataSourceURI, QgsWKBTypes, QGis, QgsVectorLayer, QgsFeature, QgsGeometry, QgsMessageLog, QgsMapLayerRegistry
# Initialize Qt resources from file resources.py
import resources
# Import the code for the dialog
from topoGeomEdit_dialog import TopologicGeometryEditDialog
# Import the topology connector class
from TopologyConnector import TopologyConnector
from LayerDbInfo import LayerDbInfo
import os.path
from qgis.utils import iface
from PyQt4.Qt import QColor
# time to check performance issues
import time

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
        self.insideTopoEdit = False # dynamic handling of geometry change listener
        self.rollBackStarted = False # prevent geometry change triggered by rollback action
        self.nodeLayer = None
        self.edgeLayer = None
        self.layerInfo = None # holds information of current selected layer
        
        # set db connector for topology tests
        self.topologyConnector = TopologyConnector()
        # check if already a layer is selected on Plugin Load (probably only during testing) 
        currentLayer = self.iface.mapCanvas().currentLayer()
        if currentLayer:
            self.listen_layerChanged(currentLayer)
        # connect to geometry changes (test)
        QObject.connect(self.iface.mapCanvas(), SIGNAL("currentLayerChanged(QgsMapLayer *)"), self.listen_layerChanged)

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
        
        toolname = "TopologicEdit"

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
          QMessageBox.information(None, toolname, "Select a point object to highlight topological connected line object(s)")
          return
        
        return selected
        
    def findTopology(self):
        '''
        find topological related geometries of selected geometry
        '''
        selected = self.checkSelection()
        
        if selected:
            aFeature = selected[0]
            qFeaturesList = []
            
            if aFeature:
                aGeometry = aFeature.geometry()
            
                # check different geometry types
                aType = aGeometry.wkbType()
                if aType == QGis.WKBPoint:
                    #initialLayer = iface.mapCanvas().currentLayer()
                    conFeaturesResult = self.connectedLineFeatures(aFeature)
                    if conFeaturesResult:
                        qFeaturesData = self.findLineFeatures(None, conFeaturesResult['relatedLineIds'])
                        qFeaturesList = qFeaturesData['lineFeaturesList']
                    
                if aType == QGis.WKBLineString:
                    conFeaturesResult = self.connectedPointFeatures(aFeature)
                    if conFeaturesResult:
                        qFeaturesData = self.findPointFeatures(None, conFeaturesResult['relatedPointIds'])
                        qFeaturesList = qFeaturesData['pointFeaturesList']
            
            if len(qFeaturesList) > 0:
                for aLayer in self.iface.mapCanvas().layers():
                    if aLayer.shortName() in qFeaturesList:
                        #aLayer.setSelectedFeatures(qFeaturesList[aLayer.shortName()])
                        aLayer.selectByIds(qFeaturesList[aLayer.shortName()], QgsVectorLayer.AddToSelection )
            
                #drawLayer.setSelectedFeatures(conFeaturesList)
                #dBox = drawLayer.boundingBoxOfSelected()
                #iface.mapCanvas().setExtent(dBox)
                #iface.mapCanvas().refreshAllLayers()
                #iface.setActiveLayer(initialLayer)
                #iface.mapCanvas().setSelectionColor( QColor("red") )
                self.iface.mapCanvas().refresh()
                #iface.mapCanvas().setSelectionColor( QColor("yellow") )
        return True
    
    def findPointFeatures(self, aNodeLayer, topoPoints):
        '''
        identifies a list of point features on aNodeLayer by a list of ids
        '''
        # save start time
        start = time.time()
        
        qFeaturesList = {}
        qNodeFeaturesList = []
        
        for aTopoPoint in topoPoints:
            pointLayerName = aTopoPoint.getTableName()
            pointLayer = None
            for aLayer in QgsMapLayerRegistry.instance().mapLayers().values():
                if aLayer.shortName() == pointLayerName:
                    pointLayer = aLayer
                    if pointLayerName not in qFeaturesList:
                        qFeaturesList[pointLayerName] = []
                    break
            if pointLayer:
                request = QgsFeatureRequest().setFilterExpression(u'"system_id" = ' + str(aTopoPoint.getSystemId()))
                request.setFlags(QgsFeatureRequest.NoGeometry).setSubsetOfAttributes(['id'], pointLayer.fields())
                for aQsFeature in pointLayer.getFeatures( request ):
                    if aQsFeature.id() not in qFeaturesList[pointLayerName]:
                        qFeaturesList[pointLayerName].append(aQsFeature.id())
            if aNodeLayer:
                request = QgsFeatureRequest().setFilterExpression(u'"node_id" = ' + str(aTopoPoint.getNodeId()))
                request.setFlags(QgsFeatureRequest.NoGeometry).setSubsetOfAttributes(['id'], aNodeLayer.fields())
                for aQsNodeFeature in aNodeLayer.getFeatures( request ):
                    qNodeFeaturesList.append(aQsNodeFeature.id())
        
        self.showTimeMessage('findPointFeatures', time.time() - start)        
        return {'pointFeaturesList': qFeaturesList, 'nodeFeaturesList': qNodeFeaturesList}
    
    def findLineFeatures(self, aEdgeLayer, topoLines):
        '''
        identifies a list of line features on aEdgeLayer by a list of ids
        '''
        # save start time
        start = time.time()
        
        qFeaturesList = {}
        qEdgeFeaturesList = []
        
        for aTopoLine in topoLines:
            lineLayerName = aTopoLine.getTableName() #'g_anschlussltg_abschnitt'
            lineLayer = None
            for aLayer in self.iface.mapCanvas().layers():
                if aLayer.shortName() == lineLayerName:
                    lineLayer = aLayer
                    if lineLayerName not in qFeaturesList:
                        qFeaturesList[lineLayerName] = []
                    break
            if lineLayer:
                request = QgsFeatureRequest().setFilterExpression(u'"system_id" = ' + str(aTopoLine.getSystemId()))
                request.setFlags(QgsFeatureRequest.NoGeometry).setSubsetOfAttributes(['id'], lineLayer.fields())
                for aQsFeature in lineLayer.getFeatures( request ):
                    if aQsFeature.id() not in qFeaturesList[lineLayerName]:
                        qFeaturesList[lineLayerName].append(aQsFeature.id())
            if aEdgeLayer:
                request = QgsFeatureRequest().setFilterExpression(u'"edge_id" = ' + str(aTopoLine.getEdgeId()))
                request.setFlags(QgsFeatureRequest.NoGeometry).setSubsetOfAttributes(['id'], aEdgeLayer.fields())
                for aQsEdgeFeature in aEdgeLayer.getFeatures( request ):
                    qEdgeFeaturesList.append(aQsEdgeFeature.id())
        
        self.showTimeMessage('findLineFeatures', time.time() - start)        
        return {'lineFeaturesList': qFeaturesList, 'edgeFeaturesList': qEdgeFeaturesList}
                    
    def findNodeFeature(self, aNodeLayer, aTopoNodeId):
        '''
        identify node on aNodeLayer by node_id ATopoNodeId
        '''
        qNodeFeatureId = None
        
        if aNodeLayer:        
            # get node feature
            request = QgsFeatureRequest().setFilterExpression(u'"node_id" = ' + str(aTopoNodeId))
            request.setFlags(QgsFeatureRequest.NoGeometry).setSubsetOfAttributes(['id'], aNodeLayer.fields())
            qNodeFeaturesList = []
            for aQsNodeFeature in aNodeLayer.getFeatures( request ):
                qNodeFeaturesList.append(aQsNodeFeature.id())
        
            if len(qNodeFeaturesList) > 0:
                qNodeFeatureId = qNodeFeaturesList[0]
                
        return qNodeFeatureId 
                    
    def connectedLineFeatures(self, aFeature):
        '''
        returns all Features topological connected to aFeature
        '''
        # save start time
        #start = time.time()
        
        if aFeature:
            topoNodeData = self.topologyConnector.get_nodeData_for_point(aFeature)
            #
            if topoNodeData:
                try:
                    # topoNodeWkt = self.topologyConnector.get_geometry_for_nodeid(topoNodeId) # False! Node could have been moved already so node geometry has to come from the Qgis layer.
                    connectedEdgeData = self.topologyConnector.all_edges_for_node(topoNodeData)
                    connectedEdgeIds = []
                    for aEdgeData in connectedEdgeData:
                        connectedEdgeIds.append(aEdgeData['edgeId'])
                    relatedLineIds = self.topologyConnector.get_lines_for_edgeids(connectedEdgeIds, topoNodeData)
                    self.topologyConnector.db_connection_close()
                    
                    return {'relatedLineIds': relatedLineIds, 'connectedEdgeData': connectedEdgeData, 'topoNodeData': topoNodeData}
                except:
                    # ensure connection to database is closed
                    self.topologyConnector.db_connection_close()
                    
        #self.showTimeMessage('connectedLineFeatures', time.time() - start)
            
    def connectedPointFeatures(self, aFeature):
        '''
        returns all Point Features topological connected to aFeature
        '''
        if aFeature:
            topoEdgeData = self.topologyConnector.get_edgeData_for_line(aFeature) 
                
            if topoEdgeData:
                try:
                    connectedNodeData = self.topologyConnector.all_nodes_for_edges(topoEdgeData)
                    connectedNodeIds = []
                    for aNodeData in connectedNodeData:
                        connectedNodeIds.append(aNodeData['nodeId'])
                    relatedPointIds = self.topologyConnector.get_points_for_nodeids(connectedNodeIds, topoEdgeData)
                    self.topologyConnector.db_connection_close()
                    
                    return {'relatedPointIds': relatedPointIds, 'connectedNodeData': connectedNodeData, 'topoEdgeData': topoEdgeData}
                except:
                    # ensure connection to database is closed
                    self.topologyConnector.db_connection_close()                
            
    def listen_layerChanged(self, layer):
        # listens to change of current layer
        #QObject.connect(layer, SIGNAL("geometryChanged(QgsFeatureId, const QgsGeometry &)"), self.listen_geometryChange) # does not work
        layerSourceInfo = None
        # set up layer to be used in geometry changes
        if not (self.nodeLayer and self.edgeLayer):
            for aLayer in QgsMapLayerRegistry.instance().mapLayers().values():
                if aLayer.name() == u'edge':
                    self.edgeLayer = aLayer
                if aLayer.name() == u'node':
                    self.nodeLayer = aLayer
        
        '''disconnect old listener for topological layer'''
        if self.selectedLayer and self.selectedLayer.shortName():
            self.selectedLayer.geometryChanged.disconnect(self.listen_geometryChange)
            self.selectedLayer.layerModified.disconnect(self.listen_layerModified)
            self.selectedLayer.beforeRollBack.disconnect(self.listen_beforeRollBack)
        
        if layer and layer.shortName():
            '''connect to signal'''
            layer.geometryChanged.connect(self.listen_geometryChange)
            layer.layerModified.connect(self.listen_layerModified)
            layer.beforeRollBack.connect(self.listen_beforeRollBack)
            
            layerSourceInfo = str(layer.source())
            
        '''in any case store new selected layer (can be None)'''
        self.selectedLayer = layer
        '''store layer info'''
        if layerSourceInfo:
            self.topologyConnector.setLayerInfo(LayerDbInfo(layerSourceInfo))
        else:
            self.topologyConnector.setLayerInfo(None)
    
    def listen_geometryChange(self, fid, cGeometry):
        '''
        listens to geometry changes
        '''
        toolname = "Geometry Changed"
                
        if not fid or self.insideTopoEdit == True:
            return
        
        if self.rollBackStarted == True:
            # the geometry changes are beeing rolled back so do not adjust topology layers
            # NOTE: We always use 'Rollback all Layers' for this topology model
            return
        
        # save start time
        #start = time.time()
        msg = 'Listen Geometry Change started'
        QgsMessageLog.logMessage( msg, 'TopoPlugin')
        
        aSelectedFeature = next(self.selectedLayer.getFeatures(QgsFeatureRequest(fid)))
            
        if aSelectedFeature:
            self.selectedFeature = aSelectedFeature
            #QMessageBox.information(None, toolname, "Geometry was changed for " + str(self.selectedFeature.id()))
            aGeometry = self.selectedFeature.geometry() # not the original geometry but the already changed one!
            
            aType = aGeometry.wkbType()
            if aType == QGis.WKBPoint:
                conFeaturesResult = self.connectedLineFeatures(self.selectedFeature)
                #oriGeometry = QgsGeometry.fromWkt(conFeaturesResult['topoNodeGeom'])
                #oriGeometry = conFeaturesResult['topoNodeGeom']
                if conFeaturesResult:
                    self.adjustCoordinates(cGeometry, conFeaturesResult)
            
        #self.showTimeMessage('listen_geometryChange', time.time() - start)
    
    def listen_layerModified(self):
        '''
        listens do modifications done to the layer
        '''
        if self.selectedLayer.isModified() == False and self.rollBackStarted == True:
            self.rollBackStarted = False
    
    def listen_beforeRollBack(self):
        '''
        listens to RollBack on the current layer
        '''
        if self.selectedLayer and self.selectedLayer.isModified() == True:
            self.rollBackStarted = True
            
    def adjustCoordinates(self, changedGeom, conFeaturesResult):
        '''
        find changed coordinates in all features from connected features and update them to the new coordinates
        '''
        # save start time
        #start = time.time()
        aTopoNode = conFeaturesResult['topoNodeData']
        request = QgsFeatureRequest().setFilterExpression(u'"node_id" = ' + str(aTopoNode.getNodeId()))
        request.setSubsetOfAttributes(['geom'], self.nodeLayer.fields())
        qNodeList = []
        for aQsNodeFeature in self.nodeLayer.getFeatures( request ):
            qNodeList.append(aQsNodeFeature)
        
        if len(qNodeList) > 0:
            originalGeom = qNodeList[0].geometry()
        
        if originalGeom.wkbType() == QGis.WKBPoint:
            # a point was moved, the connected features should be polygons (for now)
            oPoint = originalGeom.asPoint()
            cPoint = changedGeom.asPoint()

            if not (self.edgeLayer and self.nodeLayer):
                # something wrong
                return
            
            success = True
            
            if not self.edgeLayer.isEditable():
                self.edgeLayer.startEditing()
            if not self.nodeLayer.isEditable():
                self.nodeLayer.startEditing()
            
            conFeaturesList = conFeaturesResult['relatedLineIds']
            if conFeaturesList:
                
                self.insideTopoEdit = True

                qFeaturesData = self.findLineFeatures(self.edgeLayer, conFeaturesList)
                qLineFeaturesList = qFeaturesData['lineFeaturesList']
                qEdgeFeaturesList = qFeaturesData['edgeFeaturesList']
                
                for lineLayer in self.iface.mapCanvas().layers():
                    if lineLayer.shortName() in qLineFeaturesList:
                
                        if not lineLayer.isEditable():
                            lineLayer.startEditing()
                
                        lineLayer.beginEditCommand("Topological Geometry Edit Line")
                
                        for aConFeatureId in qLineFeaturesList[lineLayer.shortName()]:
                            for qFeature in lineLayer.getFeatures(QgsFeatureRequest(aConFeatureId)):
                                aConPoly = qFeature.geometry().asPolyline()
                                newPoly = []
                                for aCoord in aConPoly:
                                    if aCoord.x() == oPoint.x() and aCoord.y() == oPoint.y():
                                        newPoly.append(cPoint)
                                    else:
                                        newPoly.append(aCoord)
                                newGeom = QgsGeometry.fromPolyline(newPoly)
                                #lineLayer.changeGeometry(qFeature.id(), newGeom)
                                changeDone = lineLayer.changeGeometry(qFeature.id(), newGeom)
                                success = success and changeDone

                        if success == False:
                            lineLayer.destroyEditCommand()
                            break
                        else:
                            lineLayer.endEditCommand()
                
                self.edgeLayer.beginEditCommand("Topological Geometry Edit Edge")
                            
                for aConEdgeId in qEdgeFeaturesList:
                    for qFeature in self.edgeLayer.getFeatures(QgsFeatureRequest(aConEdgeId)):
                        aEdgePoly = qFeature.geometry().asPolyline()
                        newPoly = []
                        for aCoord in aEdgePoly:
                            if aCoord.x() == oPoint.x() and aCoord.y() == oPoint.y():
                                newPoly.append(cPoint)
                            else:
                                newPoly.append(aCoord)
                        newGeom = QgsGeometry.fromPolyline(newPoly)
                    
                        changeDone = self.edgeLayer.changeGeometry(qFeature.id(), newGeom)
                        success = success and changeDone            
                            
                aNodeFeatureId = self.findNodeFeature(self.nodeLayer, aTopoNode.getNodeId())

                self.nodeLayer.beginEditCommand("Topological Geometry Edit Node")
                            
                for qFeature in self.nodeLayer.getFeatures(QgsFeatureRequest(aNodeFeatureId)):
                    newGeom = QgsGeometry.fromPoint(cPoint)
                    changeDone = self.nodeLayer.changeGeometry(qFeature.id(), newGeom)
                    success = success and changeDone
                
                if success == False:
                    self.nodeLayer.destroyEditCommand()
                    self.edgeLayer.destroyEditCommand()
                    self.insideTopoEdit = False
                    QgsMessageLog.logMessage( 'adjust coordinates not successfull', 'TopoPlugin', 2)
                    return
                
                self.nodeLayer.endEditCommand()
                self.edgeLayer.endEditCommand()
                self.insideTopoEdit = False
                
            #lineLayer.beginEditCommand("edit")
            #lineLayer.endEditCommand()
        #self.showTimeMessage('adjustCoordinates', time.time() - start)
            
    def showTimeMessage(self, aMethodName, elapsedTime):
        '''
        write QGis log for current plugin
        '''
        msg = '{Name} took {elapsed} seconds'.format(elapsed = elapsedTime, Name = aMethodName).strip()
        QgsMessageLog.logMessage( msg, 'TopoPlugin')
            
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
