import neuroglancer
from copy import deepcopy
from selenium import webdriver
from threading import Thread, Event


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
        exit_event (threading.Event) : while this event is not set the server is
                                        running
        optional:
        annotation : see class Annotations
        timer : see class Timer
        """

    def __init__(self,
                 raw_data,
                 layers={},
                 annotation=False,
                 timer_interval=None,
                 **kwargs):
        """Initiates viewer base class by

        - initiating the neuroglancer viewer with a 'x-3D' layout
        - setting keyboard function
        - starting browser

        Args:
            raw_data (str) : full id of the raw data layer in form of
                        "src:projectId:datasetId:volumeId"
            layers (dict) : dict with layer names as keys and layer ids as values
            annotation(Boolean) : determines whether to build a viewer with
                                annotation layer, optional
            timer_interval (int) : interval betweenn timer execution, if set
                                adds a timer to the viewer, optional
        """
        self.viewer = neuroglancer.Viewer()
        if annotation:
            self.annotation_flag = True
            self.annotation = Annotations(viewer=self.viewer)
        else:
            self.annotation_flag = False
        if timer_interval is not None:
            self.timer = Timer(timer_interval)

        self.exit_event = Event()
        self._driver = None
        self._init_viewer(raw_data, layers)
        self._set_keybindings()
        self._run_browser()

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
            s.layers[''] = neuroglancer.AnnotationLayer(
                linked_segmentation_layer=name)
        s.layout = 'xy-3d'
        s.perspectiveZoom = 54.59815003314426
        s.showSlices = False
        self.viewer.set_state(s)

    def _set_keybindings(self):
        """Binds key board events to call back functions"""
        self.viewer.actions.add('exit_revision',
                                lambda s: self.exit())

        with self.viewer.config_state.txn() as s:
            s.input_event_bindings.viewer['control+delete'] = 'exit_revision'

    # BROWSER
    def _run_browser(self):
        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_argument("--disable-infobars")
        chrome_options.add_experimental_option('excludeSwitches',
                                               ['enable-logging'])
        self._driver = webdriver.Chrome(options=chrome_options)
        self._driver.get(self.viewer.get_viewer_url())

    # EXIT
    def exit(self):
        self._driver.quit()
        self.exit_event.set()
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

    def _upd_viewer_segments(self, layer, segments):
        """displays segments in a particular neuroglancer layer

        Args:
            layer (str) : name of the target layer
            segments (list or set) : segments to display
        """
        # the neuroglancer viewer freezes when trying to modify display settings
        # through key callbacks while layer options interface is open
        # - request user to close if this is the case
        if not self.viewer.state.selectedLayer.visible:
            with self.viewer.txn() as s:
                s.layers[layer].segments = segments
        else:
            msg = 'Close layer option window before changing segment display.'
            self.upd_msg(msg)

    def get_viewport_loc(self):
        """retrieves voxel coordinates of the viewport center"""
        return list(self.viewer.state.voxel_coordinates)

    def set_viewer_loc(self, coord):
        """Sets the viewport focus to voxel coordinates "coord".

        Args:
            coord (list) : voxel coordinates [x,y,z]
        """
        s = deepcopy(self.viewer.state)
        s.voxel_coordinates = coord
        self.viewer.set_state(s)

    def _toggle_opacity(self, layer):
        """Allows to toggle the opacity of the segments in a layer between 0,
        0.25 and 0.5.

        Args:
            layer (str) : name of the target layer
        """

        # the neuroglancer viewer freezes when trying to modify display settings
        # through key callbacks while layer options interface is open
        # - request user to close if this is the case
        state = deepcopy(self.viewer.state)
        if not state.selectedLayer.visible:
            cur_val = state.layers[layer].selectedAlpha
            vals = [0, .25, .5]
            val = vals[-1]
            if cur_val in vals:
                idx = vals.index(cur_val)
                idx = (idx + 1) % len(vals)
                val = vals[idx]
            state.layers[layer].selectedAlpha = val
            self.viewer.set_state(state)
        else:
            msg = 'Close layer option window before changing opacity via key ' \
                  'board.'
            self.upd_msg(msg)


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
                 **kwargs):
        """Initiates ViewerBase class with neuroglancer in 2 column layout

        Args:
            raw_data (str) : image data volume id :
                            data_src:project:dataset:volume_name
            layers (dict) : dict with layer names as keys and layer ids as values
        """
        self.layer_names = ['raw'] + list(layers.keys())
        self.seg_vol1 = [self.layer_names[1]]
        self._first_layer = True
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
        # create lists of layer names for the row_layout LayerGroupViewer
        # settings
        if self.annotation_flag:
            self.layer_names += ['']
            self.seg_vol1 += ['']

        self._toggle_layout(n_rows=3)

    def _toggle_layout(self, n_rows=None):
        """toggles viewer layout between 2 column (xy + agglomerated volume
        layer 3D) and 3 column layout (xy + agglomerated volume layer 3D + base
        volume layer)

        Args:
            n_rows (int) : number of rows of the viewer
        """
        s = deepcopy(self.viewer.state)
        if not n_rows:
            if len(s.layout) == 3:
                n_rows = 2
            elif len(s.layout) == 2 and not self._first_layer:
                n_rows = 2
            else:
                n_rows = 3

        if n_rows == 3:
            s.layout = neuroglancer.row_layout([
                neuroglancer.LayerGroupViewer(layout='xy',
                                              layers=self.layer_names),
                neuroglancer.LayerGroupViewer(
                    layout='3d', layers=self.seg_vol1),
                neuroglancer.LayerGroupViewer(layout='3d',
                                              layers=[self.layer_names[2]]),
            ])
        else:
            if self._first_layer:
                layer = neuroglancer.LayerGroupViewer(layout='3d',
                                                      layers=self.seg_vol1)
                self._first_layer = False
            else:
                layer = neuroglancer.LayerGroupViewer(layout='3d',
                                                      layers=[
                                                          self.layer_names[2]])
                self._first_layer = True
            s.layout = neuroglancer.row_layout(
                [neuroglancer.LayerGroupViewer(layout='xy',
                                               layers=self.layer_names), layer])
        self.viewer.set_state(s)

    def _set_keybindings(self):
        """Binds key board events to call back functions"""
        super()._set_keybindings()
        self.viewer.actions.add('toggle_layout',
                                lambda s: self._toggle_layout())

        with self.viewer.config_state.txn() as s:
            s.input_event_bindings.data_view['keyw'] = 'toggle_layout'


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
    def __init__(self, interval, _func=None):
        """

        Args:
            interval (int) : time in sec between timer function execution
        """
        self.stopTimer = Event()
        self.interval = interval
        self._func = _func

    def start_timer(self, func=None):
        self._func = func
        Thread(target=self._timer_fcn, args=(self.interval,),
               daemon=True).start()

    def _timer_fcn(self):
        """timer function to trigger function at interval sec
        """
        while not self.stopTimer.wait(self.interval):
            self._func()
