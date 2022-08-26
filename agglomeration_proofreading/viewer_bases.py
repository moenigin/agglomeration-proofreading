import neuroglancer
import os
from agglomeration_proofreading.ap_utils import return_other
from copy import deepcopy
from configparser import ConfigParser
from selenium import webdriver
from threading import Thread, Event


# Todo: outsource to separate package? add function to retrieve selected items
#  from all visible layers (or a distinct layer)

class _ViewerBase:
    """Base class for neuroglancer viewer

    key-bindings:
        - "ctrl+delete" to exit viewer and close the browser window

    Attributes:
        _driver (selenium.webdriver.chrome.webdriver.WebDriver) : webdriver to
                                                                  run browser
        stopTimer (threading.Event) : event for autosave timer is set at
                                      interval sec
        lock (threading.Lock) : lock to ensure data is not modified while saving
        exit_event (threading.Event) : by calling wait on this event it can be
                                       used to keep the python server running.
                                       Exit functions should then set this event
        coord_list_map (dict) : dictionary that maps the coordinate lists to an
                                index. The index of the current list between
                                which coordinate entries one can jump is stored
                                in cur_coord_list_idx
        coord_list_idx_map (dict) : dictionary that maps the index of last
                                    coordinate (-> cur_coord_idx) visited for a
                                    certain list to an index
                                    (-> cur_coord_list_idx)
        cur_coord_list (list) : current list of coordinates to which one can jump
        cur_coord_list_idx (int) : index of the current list of coordinates in
                             coord_list_map and coord_list_idx_map
        cur_coord_idx (int) : index of the current coordinate entry in the
                              cur_coord_list
        coord_list_names (list) : list of attribute names, these class
                                  attributes contain the lists of coordinates
                                  which one likes to visit
        optional:
        annotation : see class Annotations
        timer : see class Timer
        """

    def __init__(self,
                 raw_data,
                 layers={},
                 annotation=False,
                 timer_interval=None,
                 remove_token=True,
                 # coordinate_lists=None,
                 **kwargs):
        """Initiates viewer base class by

        - initiating the neuroglancer viewer with a 'x-3D' layout
        - setting keyboard function
        - starting browser

        Args:
            raw_data (str) : full id of the raw data layer in form of
                             "src:projectId:datasetId:volumeId"
            layers (dict) : dict with layer names as keys and layer ids as values
            annotation (bool) : determines whether to build a viewer with
                                annotation layer, optional
            timer_interval (int) : interval between timer execution, if set
                                   adds a timer to the viewer, optional
            remove_token (bool) : determines whether to remove personalised
                                  token created during the neuroglancer
                                  authentication procedure
            coordinate_lists (dict) : dictionary with keys = list name and
                                      values = list of coordinates to which to
                                      jump to
        """
        self.dimensions = None
        self.viewer = neuroglancer.Viewer()
        if annotation:
            self.annotation_flag = True
            self.annotation = Annotations(viewer=self.viewer)
            self.get_dimensions_timer = Timer(.1)
        else:
            self.annotation_flag = False
        if timer_interval is not None:
            self.timer = Timer(timer_interval)

        # # attributes for visiting coordinates in a list and switching between
        # # coordinate lists
        # self.cur_coord_list = None
        # self.cur_coord_list_idx = None
        # self.cur_coord_idx = 0
        # self.coord_list_map = dict()
        # self.coord_list_idx_map = dict()
        #
        # if coordinate_lists is not None:
        #     for key, val in coordinate_lists.items:
        #         setattr(self, key, val)
        #     self.coord_list_names = list(coordinate_lists.keys())
        #     self.mk_coord_list_maps()

        self.remove_token = remove_token
        self.exit_event = Event()
        self._driver = None
        self._init_viewer(raw_data, layers)
        self._set_keybindings()
        self._run_browser()

    # CONTEXT MANAGER PROTOCOL
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self._clean_exit()

    # VIEWER SETUP
    def _init_viewer(self, raw_data, layers={}):
        """Initiates the neuroglancer viewer.

        The neuroglancer viewer is initiated in a 3 row layout.The first column
        displays the xy image view overlaying the raw data, the base
        segmentation volume, the agglomerated segmentation volume and an
        annotation layer. The second column displays the 3D view of the
        agglomeration volume and the annotation layer. The 3rd column displays
        the perspective view of base segmentation volume.

        Args: raw_data (str) : address to the raw_data volume
             base_vol (str) : address to the base volume
             center (list) : voxel coordinates to the volume center as a
             starting position : [x,y,z]
        """
        s = deepcopy(self.viewer.state)
        s.layers['raw'] = neuroglancer.ImageLayer(source=raw_data)
        for name, src in layers.items():
            s.layers[name] = neuroglancer.SegmentationLayer(source=src)
        if self.annotation_flag:
            name = next(iter(layers.values()))
            self.get_dimensions_timer.start_timer(self._add_annotation_layer,
                                                  name)
        s.layout = 'xy-3d'
        s.showSlices = False
        self.viewer.set_state(s)

    def _add_annotation_layer(self, name):
        """Adds an annotation layer to the viewer.

        In neuroglancer >= 2.0 the annotation layer requires an dimension
        argument. This CoordinateSpace dictionary is read out from the viewer
        state once the data has been retrieved from the server and this
        information has been written to the viewer state.
        Changes to the viewer that need to be executed after the annotation
        layer has been added can be handled by self._annotation_layer_cb()

        Args:
            name(str) : name of the annotation layer.
        """
        if any(self.viewer.state.dimensions):
            s = deepcopy(self.viewer.state)
            self.dimensions = s.dimensions
            s.layers[''] = neuroglancer.LocalAnnotationLayer(
                dimensions=self.dimensions,
                linked_segmentation_layer={'segments': name})
            self.viewer.set_state(s)
            self.get_dimensions_timer.stopTimer.set()
            self._annotation_layer_cb()

    def _annotation_layer_cb(self):
        """dummy function for code that has to be executed once the annotation
        layer has been created"""
        pass

    def _set_keybindings(self):
        """dummy to define key board events to call back functions in children"""
        pass

    def _bind_pairs(self, ini_file=None):
        """key bindings parsed from ini file"""
        if ini_file is None:
            print('no valid keybinding configuration file was specified. '
                  'Please restart and provide a valid keybinding config')
            return
        keybindings = ConfigParser()
        keybindings.read(ini_file)
        with self.viewer.config_state.txn() as s:
            for str_ in keybindings['KEYBINDINGS']:
                key = keybindings['KEYBINDINGS'][str_]
                binding_group = keybindings['BINDING_GROUP'][str_]
                if binding_group == 'viewer':
                    s.input_event_bindings.viewer[key] = str_
                elif binding_group == 'data_view':
                    s.input_event_bindings.data_view[key] = str_
                elif binding_group == 'perspective_view ':
                    s.input_event_bindings.perspective_view[key] = str_
                elif binding_group == 'slice_view':
                    s.input_event_bindings.slice_view[key] = str_
                else:
                    raise ValueError('Binding group not found')

    # BROWSER
    def _run_browser(self):
        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_experimental_option('excludeSwitches',
                                               ['enable-logging'])
        self._driver = webdriver.Chrome(options=chrome_options)
        self._driver.maximize_window()
        self._driver.get(self.viewer.get_viewer_url())

    # EXIT
    def _clean_exit(self):
        self._driver.quit()
        if self.remove_token:
            try:
                os.remove(os.path.expanduser('~/.apitools.token'))
                os.remove(os.path.expanduser('~/.apitools.token.lock'))
            except FileNotFoundError:
                print(os.path.expanduser('~/.apitools.token'),
                      ' was not found - apitoken could not be removed')

        if hasattr(self, 'timer'):
            self.timer.stopTimer.set()

    # BASIC FUNCTIONS
    def upd_msg(self, msg):
        """displays message in the neuroglancer status message bar

        Args:
            msg (str) : a message
        """
        with self.viewer.config_state.txn() as s:
            s.status_messages['status'] = msg

    def upd_viewer_segments(self, layer, segments):
        """displays segments in a particular neuroglancer layer

        Args:
            layer (str) : name of the target layer
            segments (list or set) : segments to display
        """
        if isinstance(segments, int):
            segments = [segments]
        with self.viewer.txn() as s:
            s.layers[layer].segments = segments

    def upd_segment_query(self, layer, segments):
        """enters segments in segment Query Panel for respective layer"""
        if isinstance(segments, int):
            segments = [segments]
        with self.viewer.txn() as s:
            s.layers[layer].segmentQuery = ', '.join(
                [str(seg) for seg in segments])

    def get_viewport_loc(self):
        """retrieves voxel coordinates of the viewport center"""
        return [int(x) for x in self.viewer.state.voxel_coordinates]

    def set_viewer_loc(self, coord):
        """Sets the viewport focus to voxel coordinates "coord".

        Args:
            coord (list) : voxel coordinates [x,y,z]
        """
        s = deepcopy(self.viewer.state)
        s.voxel_coordinates = coord
        self.viewer.set_state(s)

    def toggle_opacity(self, layer):
        """Allows to toggle the opacity of the segments in a layer between 0,
        0.25 and 0.5.

        Args:
            layer (str) : name of the target layer
        """
        state = deepcopy(self.viewer.state)
        cur_val = state.layers[layer].selectedAlpha
        vals = [0, .25, .5]
        val = vals[-1]
        if cur_val in vals:
            idx = vals.index(cur_val)
            idx = (idx + 1) % len(vals)
            val = vals[idx]
        state.layers[layer].selectedAlpha = val
        self.viewer.set_state(state)

    def toggle_hover_value_display(self):
        """toggles the display of item values at the cursor position in the
        layer panel"""
        with self.viewer.config_state.txn() as s:
            s.showLayerHoverValues = not s.showLayerHoverValues

    # # functions to jump to different coordinates stored in lists todo: move these to separate child class
    # def toggle_location_lists(self):
    #     """toggles between the different coordinate lists and sets the position
    #     index to the last visited coordinate in the list"""
    #     self.coord_list_idx_map[self.cur_coord_list_idx] = self.cur_coord_idx
    #     if self.cur_coord_list_idx < len(self.coord_list_map) - 1:
    #         self.cur_coord_list_idx += 1
    #     else:
    #         self.cur_coord_list_idx = 0
    #     self.cur_coord_list = self.coord_list_map[self.cur_coord_list_idx]
    #     self.cur_coord_idx = self.coord_list_idx_map[self.cur_coord_list_idx]
    #     msg = self.coord_list_names[
    #               self.cur_coord_list_idx] + ' = current coordinate list'
    #     self.upd_msg(msg)
    #     self.set_current_location()
    #
    # def mk_coord_list_maps(self):
    #     """creates maps for locations lists to enable switching between
    #     location lists
    #     """
    #     self.cur_coord_list_idx = -1
    #     for idx, list_name in enumerate(self.coord_list_names):
    #         self.coord_list_map[idx] = getattr(self, list_name)
    #         self.coord_list_idx_map[idx] = 0
    #
    # def delete_cur_coord_list_item(self):
    #     """deletes the current coordinates in the current location list and sets
    #      """
    #     msg = 'deleted {} from {}'.format(
    #         self.cur_coord_list[self.cur_coord_idx],
    #         self.coord_list_names[self.cur_coord_list_idx]
    #     )
    #     self.upd_msg(msg)
    #     self.cur_coord_list.pop(self.cur_coord_idx)
    #     self.set_current_location()
    #
    # def next_coordinate(self):
    #     """sets the viewport location to the next coordinate in the current
    #     coordinate list"""
    #     next_id = self.cur_coord_idx + 1
    #     if next_id == len(self.cur_coord_list):
    #         msg = 'reached end of the list'
    #     else:
    #         self.cur_coord_idx = next_id
    #         self.set_current_location()
    #         msg = 'displaying item {} of {}'.format(self.cur_coord_idx,
    #                                                 len(self.cur_coord_list))
    #     self.upd_msg(msg)
    #
    # def prev_coordinate(self):
    #     """sets the viewport location to the next coordinate in the current
    #     coordinate list"""
    #     self.cur_coord_idx = max(0, self.cur_coord_idx - 1)
    #     msg = 'displaying item {} of {}'.format(self.cur_coord_idx,
    #                                             len(self.cur_coord_list))
    #     self.upd_msg(msg)
    #     self.set_current_location()
    #
    # def set_current_location(self):
    #     """sets viewport to the """
    #     self.set_viewer_loc(self.cur_coord_list[self.cur_coord_idx])


class _ViewerBase2Col(_ViewerBase):
    """Class for neuroglancer viewer with a 2 column layout

    key-bindings:
        - "w": toggle viewer layout between xy + 3d view agglomeration & xy + 3d
        view agglomeration + 3d view base volume
        - "ctrl+delete" to exit viewer and close the browser window

        Attributes:
            layer_names (list) : list of layer names
            seg_vol1(list) : list of layer names for the first layer (to which
                            the optional annotation gets linked)
            _first_layer : flag to toggle between first and second segmentation
            layer
    """

    def __init__(self,
                 raw_data,
                 layers={},
                 ini_dir=None,
                 **kwargs):
        """Initiates ViewerBase class with neuroglancer in 2 column layout

        Args:
            raw_data (str) : image data volume id :
                            data_src:project:dataset:volume_name
            layers (dict) : dict with layer names as keys and layer ids as values
        """
        if len(layers) != 2:
            raise ValueError('Layer input must be a dictionary with two '
                             'entries of "layer": <path to data>')
        self.layer_names = ['raw'] + list(layers.keys())
        self.seg_vols = [[self.layer_names[1]], [self.layer_names[2]]]

        if ini_dir == None:
            self.ini_dir = os.path.dirname(os.path.abspath(__file__))
        else:
            self.ini_dir = ini_dir

        super().__init__(raw_data, layers, **kwargs)

    def _init_viewer(self, raw_data, layers={}):
        """Initiates the neuroglancer viewer.

        The neuroglancer viewer is initiated in a 3 row layout.The first column
        displays the xy image view overlaying the raw data, the base
        segmentation volume, the agglomerated segmentation volume and an
        annotation layer. The second column displays the 3D view of the
        agglomeration volume and the annotation layer. The 3rd column displays
        the perspective view of base segmentation volume.

        Args: raw_data (str) : address to the raw_data volume
             base_vol (str) : address to the base volume
             center (list) : voxel coordinates to the volume center as a
             starting position : [x,y,z]
        """
        super()._init_viewer(raw_data, layers)
        # update lists of layer names for the row_layout LayerGroupViewer
        # settings if an annotation layer is added
        if self.annotation_flag:
            self.layer_names += ['']
            self.seg_vols[0] += ['']
        else:
            self._toggle_layout(self.layer_names[1])

    def _annotation_layer_cb(self):
        """creates 2 column layout after an annotation layer has been added"""
        self._toggle_layout(self.layer_names[1])

    def _toggle_layout(self, layer_to_show):
        """switches between 2 column and one column layout of the viewer
        """
        layer_to_hide = return_other(self.layer_names[1:], layer_to_show)
        viewer_state = deepcopy(self.viewer.state)
        if type(
                viewer_state.layout) == neuroglancer.viewer_state.DataPanelLayout:
            viewer_state.layers[layer_to_show].visible = True
            viewer_state.layers[layer_to_hide].visible = True
            viewer_state.layout = neuroglancer.row_layout([
                neuroglancer.LayerGroupViewer(layout='xy',
                                              layers=self.layer_names),
                neuroglancer.LayerGroupViewer(layout='3d',
                                              layers=self.seg_vols[0]),
                neuroglancer.LayerGroupViewer(layout='3d',
                                              layers=self.seg_vols[1]),
            ])

        elif type(viewer_state.layout) == neuroglancer.viewer_state.StackLayout:
            viewer_state.layers[layer_to_hide].visible = False
            viewer_state.layout = neuroglancer.row_layout([
                neuroglancer.LayerGroupViewer(layout='xy-3d',
                                              layers=self.layer_names)])

        self.viewer.set_state(viewer_state)

    def _set_keybindings(self):
        """Binds strings to call back functions"""
        self.viewer.actions.add('toggle_segmentation_layer1',
                                lambda s: self._toggle_layout(
                                    self.layer_names[1]))
        self.viewer.actions.add('toggle_segmentation_layer2',
                                lambda s: self._toggle_layout(
                                    self.layer_names[2]))

        fn = 'KEYBINDINGS_viewerbase2col.ini'
        config_file = os.path.join(self.ini_dir, fn)
        if not os.path.exists(config_file):
            raise FileNotFoundError
        self._bind_pairs(config_file)


class SegmentBrowser(_ViewerBase):
    """Class for browsing through segments in lists"""

    def __init__(self, items, raw_data, layers, coord_lst=None, cur_idx=None,
                 ini_dir=None, remove_token=False):
        """
        Args:
            items (dict) : dictionary that maps lists of segments to browse
                           through (value) to layer name (key). If item lists
                           of all individual layers differ in length, layers
                           with shorter lists will be left empty at the end
            raw_data (str) : image data volume id :
                            data_src:project:dataset:volume_name
            layers (dict) : dict with layer names as keys and layer ids as
                            values
            coord_lst (list) : list of coordinates to set the viewport to.
                               Needs to have at least as many entries as the
                               longest item list. Optional
            cur_idx (int) : List index to start browsing. Optional
            ini_dir (str) : Path to directory of ini file for key bindings
            remove_token (bool) : determines whether to remove personalised
                                  token created during the neuroglancer
                                  authentication procedure. Optional
        """
        # check and set directory of key bindings ini file
        if ini_dir == None:
            self.ini_dir = os.path.dirname(os.path.abspath(__file__))
        else:
            self.ini_dir = ini_dir

        super(SegmentBrowser, self).__init__(raw_data=raw_data, layers=layers,
                                             remove_token=remove_token)


        # create attributes for browsing through segment items
        self.lst_max = max([len(v) for v in items.values()])
        self.items = items

        self.coords = coord_lst
        if self.coords:
            if len(self.coords) < self.lst_max:
                msg = 'coordinate list is shorter than item list'
                self.upd_msg(msg)
                print(msg)
                self.exit()

        self.current_idx = 0
        if cur_idx is not None:
            self.current_idx = cur_idx
        self.display_current()

    def _set_keybindings(self):
        """Binds strings to call back functions"""
        self.viewer.actions.add('next_item',
                                lambda s: self.next_item())
        self.viewer.actions.add('previous_item',
                                lambda s: self.prev_item())
        self.viewer.actions.add('exit',
                                lambda s: self.exit())

        fn = 'KEYBINDINGS_browse_segments.ini'
        config_file = os.path.join(self.ini_dir, fn)
        if not os.path.exists(config_file):
            raise FileNotFoundError
        self._bind_pairs(config_file)

    def next_item(self):
        """increments neuron index and triggers viewer update"""
        if self.current_idx + 1 >= self.lst_max:
            self.current_idx = 0
        else:
            self.current_idx += 1

        self.display_current()

    def prev_item(self):
        """decrements neuron index and triggers viewer update"""
        if self.current_idx == 0:
            self.current_idx = self.lst_max - 1
        else:
            self.current_idx -= 1

        self.display_current()

    def display_current(self):
        """triggers display of current neuron and neuron group in the viewer"""
        for layer in self.items.keys():
            print(layer)
            if len(self.items[layer]) <= self.current_idx:
                segments = []
            else:
                segments = self.items[layer][self.current_idx]
            print(segments)
            self.upd_viewer_segments(layer, segments)
            self.upd_segment_query(layer, segments)

        if self.coords:
            self.set_viewer_loc(self.coords[self.current_idx])

        self.display_info()

    def display_info(self):
        """displays current group and neuron idx in the neuroglancer message
        panel"""
        msg = 'displaying items {} of {}'.format(self.current_idx, self.lst_max)
        self.upd_msg(msg)

    def exit(self):
        """exits program"""
        self.exit_event.set()


class Annotations:
    """Class that adds functionality to add annotations in neuroglancer
    """

    def __init__(self, anno_id=0, viewer=None):
        """initiates Annotations class

        Args:
            anno_id (int): id of the next annotation
            viewer: viewer (neuroglancer.viewer)
        """
        self.anno_id = anno_id
        self.viewer = viewer

    def _make_ellipsoid(self, layer, location):  # Todo
        """Sets an ellipsoid annotation

        Args:
            layer (str) : name of the target layer
            location (list) : ellipsoid center in voxel coordinates [x,y,z]
            radii (list) :  ellipsoid radii [x,y,z] (optional)
        """
        self.anno_id += 1
        with self.viewer.txn() as s:
            annotations = s.layers[layer].annotations
            annotations.append(
                neuroglancer.EllipsoidAnnotation(id=str(self.anno_id),
                                                 center=location,
                                                 radii=[25, 25, 10]))

    def _make_point(self, layer, location):
        """Sets a point annotation

        Args:
            layer (str) : name of the target layer
            location (list) : voxel coordinates [x,y,z]
        """
        self.anno_id += 1
        with self.viewer.txn() as s:
            annotations = s.layers[layer].annotations
            annotations.append(
                neuroglancer.PointAnnotation(id=str(self.anno_id),
                                             point=location))

    def _make_line(self, layer, pointa, pointb):
        """makes a line annotation

        Args:
            layer (str) : name of the target layer
            pointa (list) : voxel coordinates [x,y,z]
            pointb (list) : voxel coordinates [x,y,z]
        """
        self.anno_id += 1
        with self.viewer.txn() as s:
            annotations = s.layers[layer].annotations
            annotations.append(
                neuroglancer.LineAnnotation(id=str(self.anno_id),
                                            point_a=pointa), point_b=pointb)


class Timer:
    """Timer that executes function at defined time intervals

    Attributes:
        stopTimer (threading.Event)
        interval (int) : interval between function execution
        _func = function to execute
    """

    def __init__(self, interval):
        """

        Args:
            interval (int) : time in sec between timer function execution
        """
        self.stopTimer = Event()
        self.interval = interval
        self._func = None

    def start_timer(self, func, *args, **kwargs):
        self._func = func
        Thread(target=self._timer_fcn, args=args, kwargs=kwargs,
               daemon=True).start()

    def _timer_fcn(self, *args, **kwargs):
        """timer function to trigger function at interval sec
        """
        while not self.stopTimer.wait(self.interval):
            self._func(*args, **kwargs)
