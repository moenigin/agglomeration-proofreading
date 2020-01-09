import json
import neuroglancer
import os

import numpy as np

from copy import deepcopy
from datetime import datetime
from threading import Lock, Thread

from .viewer_bases import _ViewerBase2Col
from .neuron_graph import isolate_set, LocalGraph
from .ap_utils import CustomList, flat_list


class NeuronProofreading(_ViewerBase2Col):
    """Class for proofreading individual neurons in an agglomerated segmentation
    volume.

    Description:
    This class allows to reconstruct and proofread individual neurons in an
    agglomerated segmentation volume in neuroglancer. It provides functions to
    fix agglomeration splits and false agglomeration mergers by either targeting
    falsely merged segments individually or splitting of an entire group of
    segments falsely merged to the neuron under reconstruction in the
    agglomeration procedure.
    The agglomeration graph is thereby modified locally and stored in a graph
    dictionary (see class LocalGraph). Information about the agglomeration graph
    is retrieved through the BrainMapsAPI (see class GraphTools). Decisions
    about equivalences/edges between segments in the base volume that should be
    added or removed are stored and saved to disc.

    Instructions:
    1. merging false splits
    - move the cursor to the falsely split segment while pressing "control", try
        to target a location close to the target branch!
    - move the cursor above the target branch close to the falsely split segment
        and press "d"

    2. splitting false agglomeration mergers:
    - Empty the base volume viewport with "f".
    - Move the cursor to one of the segments that is likely to be involved in
        the false merger and press "c". All segments connected to this segment
        are displayed:
        - If the segment is not merged to one in the wrong branch, hover over
            the next segment in the base volume and press "c"again.
        - If a merged segment is found, move the cursor to this segment and
            split edges by pressing "ctrl + x". The viewer will refresh.
        - If the merged branches were successfully, hover over the
            segment/branch that does not belong to the target neuron and confirm
            the merge split by pressing "k".

    3. removing groups of falsely merged segments:
    This serves to remove larger groups of segments that should be split from
    the target branch. It does not preserve the connections of the segments to
    any other branch! This can be helpful to remove larger groups of segments
    covering membranes or ECS that are merged to the target neuron.
    IMPORTANT: before using this, first make sure to empty the base volume
    viewport ("f")
    - Select any segment in the base volume that should be removed. Press
        "ctrl+bracketright" to split off the merged segments. The viewer updates
        and shows the segments in the neuron graph
    - segments that do not belong to the neuron that is reconstructed can be
        removed by moving the cursor to the segment and pressing "shift+f"

    4. branch points:
    - to set a branch point move the viewport location to the merge site (e.g.
        right click) and press "y"
    - to jump to the last unfinished branch location press "7"
    - to tag a branch point as visited press "ctrl + r". It will be annotated
        with an ellipsoid and not be revisited when pressing "7"
    - to remove a branch point annotation by hovering the cursor over the
    ellipsoid and press '0'

    5. storing segmentation merger locations:
    - move the viewport center to the merge site (e.g. right click) and press
        "m"

    Helpful functions, press:
    - "ctrl + a" while hovering over a target segment will add the segment and
        its agglomerated partners to the graph without adding an edge.
    - "shift + f" while hovering over a target segment will remove the segment
        and its agglomerated partners from the neuron graph
    - "ctrl + z" undo function for merging edges, splitting edges, splitting of
        segment groups, adding segments to the
        neuron graph and deleting segments from the neuron graph. Only the last
        10 actions can be undone
    - "w": toggle viewer layout between xy + 3d view agglomeration & xy + 3d
        view agglomeration + 3d view base volume
    - "2"/"3": toggle segmentation layer opacity: "2" for the base volume and
        "3" for the agglomerated volume
    - "4": toggle visibility of the (branch point) annotation layer with
    - "f" : to remove all selected segments from viewer of base volume
    - "n": to toggle the neuron display in the 3D agglomeration viewport
    - "ctrl+delete" to exit review and close the browser window

    Attributes:
        graph (NeuronGraph.LocalGraph) : see class LocalGraph
        graph_tools (NeuronGraph.GraphTools) : see class GraphTools
        viewer (neuroglancer.Viewer) : see neuroglancer documentation
        set_edge_ids (list) : temporarily stores the ids of an edge that should
                                be set
        set_edge_loc (list) : temporarily stores the voxel location between
                                which an edge should be set
        del_edge_ids (list) : temporarily stores the ids of an edge that should
                                be deleted
        edges_to_set (ap_utils.Customlist) : stores the information about the
                                        edges to be set via the BrainMaps API:
                                        [[segment_location1, segment_location2],
                                        [segment_id1, segment_id2]]
        edges_to_delete (ap_utils.Customlist)  : stores the edges to be deleted
                                            via the BrainMaps API :
                                            [[segment_id1, segment_id2], ...]
        action_history (ap_utils.Customlist)  : stores the ten past actions
                                            modifying the neuron's graph:
                                        [{'action_type': [edge_information]}]
        branch_point (ap_utils.Customlist)  : stores branch locations and their
                                            revision status:
                                            [[[x,y,z], Boolean], ...]
        segmentation_merger_loc (ap_utils.Customlist)  : stores locations of
                                                true segmentation mergers:
                                                [[x,y,z], ...]
        misalignment_locations (ap_utils.Customlist)  : stores location of
                                                    interruptions in the
                                                    segmentation due to
                                                    misalignment: [[x,y,z], ...]
        var_names (list) : list of attribute names for ease of setting and
                            saving these attributes
        dir_path (str) : path to the directory to save revision data
        anno_id (int) : counter to give an index to ellipsoid annotations
        remove_token (boolean) : flag that decides whether to remove api-token
                                upon exit of the program
    """

    def __init__(self,
                 dir_path,
                 graph_tool,
                 base_vol,
                 raw_data,
                 data=None,
                 timer_interval=300,
                 remove_token=True):
        """Initiates NeuronProofreading class by:

        - initiating attributes, if available loading data from previous
        revision rounds
         - starting autosave timer

        Args:
            dir_path (str) : path to directory for file saving
            graph_tool(neuron_graph.GraphTool) : functions to retrieve
                                                information about the
                                                agglomeration graph
            base_vol (str) : base segmentation volume id :
                            data_src:project:dataset:volume_name
            raw_data (str) : image data volume id :
                            data_src:project:dataset:volume_name
            data (dict) : data from previous review session (optional)
            timer_interval (int) : autosave interval in sec (optional)
            remove_token (boolean) : flag that decides whether to remove
                                    api-token upon exit of the program
                                    (optional)
        """

        # set (default) attributes
        self.set_edge_ids_temp = []
        self.set_edge_loc_temp = []
        self.del_edge_ids = []
        self.dir_path = dir_path
        self.graph = LocalGraph()
        self.graph_tools = graph_tool
        self.var_names = [
            'edges_to_set', 'edges_to_delete', 'action_history',
            'branch_point', 'segmentation_merger_loc'
        ]
        for name in self.var_names:
            setattr(self, name, CustomList([]))
        self.lock = Lock()
        self.base_layer = 'base'
        self.aggl_layer = 'agglo'
        layers = {self.aggl_layer: base_vol, self.base_layer: base_vol}

        # load data
        self.load_data_msg = ''
        if data is not None:
            self._load_data(data)
        self.action_history.max_length = 10

        super(NeuronProofreading, self).__init__(raw_data=raw_data,
                                                 layers=layers,
                                                 annotation=True,
                                                 timer_interval=timer_interval,
                                                 remove_token=remove_token)

        # initiate stuff
        with self.viewer.txn() as s:
            s.layers[self.base_layer].selectedAlpha = 0
            s.concurrent_downloads = 256
        self.timer.start_timer(func=self._auto_save)
        self.toggle_hover_value_display()
        self._upd_viewer()
        self.set_viewer_loc(data['last_position'])
        self.upd_msg(self.load_data_msg)

        # load data
        if data is not None:
            self._load_data(data)
        self.action_history.max_length = 10

    # autosave upon exit
    def exit(self):
        self._auto_save()
        self.exit_event.set()

    # VIEWER SETUP
    def _set_keybindings(self):
        """Binds key board events to call back functions"""
        super()._set_keybindings()
        self.viewer.actions.add('select', self._handle_select)
        self.viewer.actions.add('select_base', self._handle_select_base)
        self.viewer.actions.add('get_first_sv_to_merge',
                                self._get_sv1_for_merging)
        self.viewer.actions.add('set_equivalence', self._get_sv2_for_merging)
        self.viewer.actions.add('custom_toggle_xy3d',
                                lambda s: self._custom_toggle_layout())
        self.viewer.actions.add('set_branch_point',
                                lambda s: self._store_branch_loc())
        self.viewer.actions.add('remove_branchpoint',
                                lambda s: self._remove_branch_loc())
        self.viewer.actions.add('jump_to_last_branchpoint',
                                lambda s: self._jump_to_branch_loc())
        self.viewer.actions.add('store_merger_loc',
                                lambda s: self._store_merger_loc())
        self.viewer.actions.add('show_connected_partners',
                                self._show_connected_partners)
        self.viewer.actions.add('split_merger', self._split_merger)
        self.viewer.actions.add('confirm_merge_split',
                                self._confirm_merge_split)
        self.viewer.actions.add('remove_merged_group',
                                lambda s: self._remove_merged_group())
        self.viewer.actions.add('toggle_neuron',
                                lambda s: self._toggle_neuron())
        self.viewer.actions.add('del_sv_from_neuron', self._del_sv_from_neuron)
        self.viewer.actions.add('add_sv_to_neuron',
                                lambda s: self._add_unconnected_sv_to_neuron(s))
        self.viewer.actions.add('undo_last_action',
                                lambda s: self._undo_last_action())
        self.viewer.actions.add('save_data', lambda s: self._save_data())
        self.viewer.actions.add('toggle_opacity_base',
                                lambda s: self._toggle_opacity(self.base_layer))
        self.viewer.actions.add('toggle_opacity_agglomeration',
                                lambda s: self._toggle_opacity(self.aggl_layer))
        self.viewer.actions.add('empty_base_vol',
                                lambda s: self._upd_viewer_segments(
                                    self.base_layer, []))
        self.viewer.actions.add('delete_closest_annotation',
                                self._delete_closest_annotation)
        self.viewer.actions.add('exit_revision', lambda s: self.exit())
        self.viewer.actions.add('toggle_hover_values', lambda s: self.toggle_hover_value_display())

        _DEFAULT_DIR = os.path.dirname(os.path.abspath(__file__))
        fn = 'KEYBINDINGS_proofreader.ini'
        config_file = os.path.join(_DEFAULT_DIR, fn)
        if not os.path.exists(config_file):
            raise FileNotFoundError
        self._bind_pairs(config_file)

    def _annotation_layer_cb(self):
        """Triggers column layout setting and loads annotation from previous
        revisions"""
        super()._annotation_layer_cb()
        annocount = 0
        if any(self.branch_point):
            for point in self.branch_point:
                if point[1]:
                    annocount += 1
                    self.annotation._make_ellipsoid('', point[0])

    # VIEWER INTERACTION
    def _handle_select(self, action_state):
        """Overrides the neuroglancer response to a double click maintaining its
        default functionality vastly: select or unselect a segment in the
        agglomerated volume from display.

        To select or unselect a segment of the agglomerated volume when
        displaying the agglomeration through the neuroglancer dictionary the
        segment id at the cursor position is retrieved from the action state.
        The members of the agglomerated supervoxel to this segment are then
        retrieved through the Brainmaps API and the viewer state is updated
        accordingly.

        Args:
            action_state : neuroglancer.viewer_config_state.ActionState
        """
        segment_id = self._get_sv_id(action_state)
        if segment_id is None or segment_id == 0:
            return

        with self.viewer.txn() as s:
            # agglomeration viewer: retrieve segments and equivalences set
            eqv_set = s.layers[self.aggl_layer].equivalences.sets()
            viewer_seg = s.layers[self.aggl_layer].segments
            segments_aggl = flat_list(eqv_set)

            # Remove the agglomerated parent of segment_id from viewer and
            # equivalence dictionary if it is already in the viewer and/or
            # equivalence dictionary
            if (any(viewer_seg) and segment_id in segments_aggl) \
                    or segment_id in viewer_seg:
                if segment_id in segments_aggl:
                    agglo_id = next(
                        min(seg) for seg in eqv_set if segment_id in seg)
                else:  # single segment that will not appear in the viewer
                    # equivalence dict
                    agglo_id = segment_id
                s.layers[self.aggl_layer].segments.remove(agglo_id)
                s.layers[self.aggl_layer].equivalences.delete_set(segment_id)
            else:
                # otherwise get the graph of the neuron
                agglo_id = self.graph_tools.get_agglo_id(segment_id)
                members = self.graph_tools.get_members(agglo_id)
                # if edges to delete have already been identified, check whether
                # segment_id is part of merged segment and make sure that the
                # display reflects already performed correction locally
                if any(flat_list(self.edges_to_delete)):
                    edges_to_delete = [edge for edge in self.edges_to_delete
                                       if edge[0] in members]
                    if any(edges_to_delete):
                        members, agglo_id = self._update_merger_locally(
                            segment_id, members, edges_to_delete)

                # add to both viewer segment list and equivalence dictionary
                s.layers[self.aggl_layer].segments.add(agglo_id)
                s.layers[self.aggl_layer].equivalences.union(*members)

    def _update_merger_locally(self, segment_id, members, edges_to_delete):
        """Updates display of merged segment locally

        When selecting a segment that has already been split off locally but
        not in the remote agglomeration graph this ensures the updated display.

        Args:
            segment_id (int) : id of the selected segments
            members (list) : list of segment that belong to the agglomerated
                            supervoxel
            edges_to_delete(list): list of edges that were deleted locally

        Returns:
            members(list) : list of segment ids of that belong to the same
                            connected component as segment_id considering the
                            local correction
            agglo_id(int) : updated id of the agglomerated parent
        """
        edge_list = self.graph_tools.get_edges(members)
        temp_graph = LocalGraph()
        temp_graph.add_edge(edge_list)
        temp_graph.del_edge(edges_to_delete)
        for cc_members in temp_graph.cc.values():
            if segment_id in cc_members:
                members = cc_members
                break
        agglo_id = min(members)
        return members, agglo_id

    def _handle_select_base(self, action_state):
        """Overrides the neuroglancer response to a double click maintaining its
        default functionality vastly: select or unselect a segment from display.

        Args:
            action_state : neuroglancer.viewer_config_state.ActionState
        """
        segment_id = self._get_sv_id(action_state)
        if segment_id is None or segment_id == 0:
            return

        with self.viewer.txn() as s:
            segments_base = s.layers[self.base_layer].segments
            if segment_id in segments_base:
                segments_base.remove(segment_id)
            else:
                segments_base.add(segment_id)

    def _custom_toggle_layout(self):
        """Overrides the neuroglancer toggle_layout default:

        Pressing space will only toggle between 3d and xy-3d layout since
        orthogonal viewparts are not neededfor the proofreading
        """
        s = deepcopy(self.viewer.state)
        if s.layout.type == 'xy-3d':
            s.layout.type = '3d'
        elif s.layout.type == '3d':
            s.layout.type = 'xy-3d'
        elif s.layout.type == 'row':
            msg = 'cannot toggle between xy-3D and 3D fullscreen mode when the ' \
                  'viewer is in column layout'
            self.upd_msg(msg)
        else:
            print('unexpected layout', s.layout)
        self.viewer.set_state(s)

    def _get_sv_id(self, action_state):
        """returns id of the segment at cursor position from a neuroglancer
        action state

        Args:
            action_state : neuroglancer.viewer_config_state.ActionState

        Returns:
            segment id : int or None
        """
        try:
            # get first active segmentation layer
            layer = next(layer.name for layer in
                         action_state.viewer_state.layers
                         if layer.type == "segmentation")
            selected_object = action_state.selected_values[layer]
        except KeyError:
            msg = 'Cursor misplaced - try again'
            self.upd_msg(msg)
            return
        # When equivalences are set via the neuroglancer equivalence dictionary
        # the selected_values objects retrieved in the action state is of type
        # MapEntrys with the first entry being the segment id and the second the
        # mapped/agglomerated id. Otherwise the segment id is an int.
        if type(selected_object) == neuroglancer.viewer_config_state.MapEntry:
            return selected_object[0]
        elif type(selected_object) == int:
            return selected_object
        else:
            return None

    def _toggle_neuron(self):
        """Allows to toggle the display of the neuron that is reconstructed in
         the agglomeration layer viewport"""
        segments = self.viewer.state.layers[self.aggl_layer].segments
        if segments:
            self._upd_viewer_segments(self.aggl_layer, [])
        else:
            self._upd_viewer()

    def _upd_viewer(self, clear_viewer=False):
        """Updates display of neuron in the viewer based on the neuron's graph

        Args:
            clear_viewer (Boolean) : flag to decide on clearance of neuroglancer
                                    equivalence dictionary and the agglomeration
                                    layer segment list. This is necessary to
                                     display changes after an edge has been
                                     split (optional).
        """
        s = deepcopy(self.viewer.state)
        if clear_viewer:
            # force clearance of neuroglancer equivalence dictionary to
            # visualize changes after split action
            s.layers[self.aggl_layer].equivalences.clear()
            s.layers[self.aggl_layer].segments = []
        for cmp in self.graph.cc.values():
            s.layers[self.aggl_layer].equivalences.union(*cmp)
            s.layers[self.aggl_layer].segments.add(min(cmp))
        self.viewer.set_state(s)

    def _add_unconnected_sv_to_neuron(self, action_state):
        """Adds segments to the neuron's graph without adding an edge

        Segment id at the current cursor location in the viewer is retrieved.
        The agglomerated graph of this segment is retrieved and added to the
        neuron's graph.

        Args:
            action_state: neuroglancer.viewer_config_state.ActionState
        """
        sv = self._get_sv_id(action_state)
        msg = 'retrieving agglomeration information  for segment ' + str(sv)
        self.upd_msg(msg)
        if type(sv) == int:
            self.action_history.append(
                {'add_segment': deepcopy(self.graph.graph)})

            Thread(target=self._add_to_graph, args=(sv,), daemon=True).start()

    def _add_to_graph(self, sv):
        """Adds a segment to neuron graph

        Args:
            sv(int) : segment id
        """
        self._add_novel_sv_to_graph(sv)
        self._upd_viewer()

    def _del_sv_from_neuron(self, action_state):
        """Deletes segments to the neuron's graph and triggers a viewer update.

       Segment id at the current cursor location in the viewer is retrieved. The
        connected component containing the segment

       Args:
           action_state: neuroglancer.viewer_config_state.ActionState
       """
        sv = self._get_sv_id(action_state)
        if type(sv) == int:
            if sv not in self.graph.graph.keys():
                msg = 'Cursor misplaced. Segment' + str(sv) + \
                      'was not found in the graph'
                self.upd_msg(msg)
                return
            self.action_history.append(
                {'del_segment': deepcopy(self.graph.graph)})
            idx = next(idx for idx, members in self.graph.cc.items()
                       if sv in members)
            members = self.graph.cc[idx]
            self.graph.del_node(members)
            self._upd_viewer(clear_viewer=True)

    def toggle_hover_value_display(viewer_item):
        with viewer_item.viewer.config_state.txn() as s:
            s.showLayerHoverValues = not s.showLayerHoverValues

    # DATA HANDLING
    def _load_data(self, data):
        """function to load data from previous revision session and set viewer
        state to continue revision

        Args:
            data (dict) :
                keys : 'edges_to_set', 'edges_to_delete', 'action_history',
                          'branch_point', 'segmentation_merger_loc',
                          'misalignment_locations'
                values : list
        """
        try:
            for name in self.var_names:
                temp = CustomList([])
                temp += data[name]
                setattr(self, name, temp)
            self.graph.graph = data['neuron_graph']
            self.graph.update_cc()
        except:
            self.load_data_msg = 'Data from previous review could not be ' \
                                 'loaded. Start review from scratch or check ' \
                                 'latest review file.'

    def _auto_save(self):
        """Checks whether variables that need to be stored have been modified
        during the last autosave interval and triggers data saving accordingly
        """
        changes = [
            getattr(getattr(self, name), 'unsaved_changes')
            for name in self.var_names
        ]
        if any(changes):
            with self.lock:
                self._save_data()

    def _save_data(self):
        """Transforms revision data dictionary and saves it to a pickle file.

        All Customlist attributes are converted to regular lists. The current
        viewport position is saved to allow continuation of revision from there.
        """
        fn = '{0:%y%m%d}_{0:%H%M%S}_agglomerationReview.json'.format(
            datetime.now())
        sv_fn = os.path.join(self.dir_path, fn)
        new_data = dict()
        for name in self.var_names:
            new_data[name] = list(getattr(self, name))
        new_data['last_position'] = self.get_viewport_loc()
        new_data['neuron_graph'] = self.graph.graph
        new_data['ts'] = datetime.timestamp(datetime.now())
        with open(sv_fn, 'w') as f:
            json.dump(new_data, f)
        for name in self.var_names:
            setattr(getattr(self, name), 'unsaved_changes', False)

    def _store_merger_loc(self):
        self.segmentation_merger_loc.append(self.get_viewport_loc())

    # BRANCH POINTS
    def _store_branch_loc(self):
        """ stores the current voxel location of the viewerstate as a
        branchpoint"""
        coord = self.get_viewport_loc()
        if coord not in self.branch_point:
            self.branch_point.append([coord, False])

    def _remove_branch_loc(self):
        """Flags last branch point location as visited and annotates it with
        an ellipsoid."""
        if any(self.branch_point):
            # get the last branchpoint set that has not been marked as visited
            # (=>point[1] == False)
            idx = max([i for i, point in enumerate(self.branch_point[:])
                       if not point[1]])
            self.annotation._make_ellipsoid('', self.branch_point[idx][0])
            self.branch_point[idx][1] = True

    def _jump_to_branch_loc(self):
        """Retrieves the last branch location that was set and sets the viewer
        position to that location."""
        if any(self.branch_point):
            idx = max([i for i, point in enumerate(self.branch_point[:])
                       if not point[1]])
            coord = self.branch_point[idx][0]
            self.set_viewer_loc(coord)
        else:
            msg = 'no branch point found'
            self.upd_msg(msg)

    def _delete_closest_annotation(self, action_state):
        s = deepcopy(self.viewer.state)
        annotations = s.layers[''].annotations
        id_loc_map = list()
        for item in annotations:
            id_loc_map.append(item.center)
        try:
            picked_coord = np.array(action_state.mouseVoxelCoordinates)
            idx = np.linalg.norm(picked_coord - np.array(id_loc_map),
                                 axis=1).argmin()

            annotations.pop(idx)
            self.viewer.set_state(s)
        except KeyError:
            self.upd_msg('could not delete annotation')
            return

    # MERGE FALSE SPLITS
    def _get_edge_information(self, action_state):
        """Adds segment id and cursor position to temporary edge attributes

        Args:
            action_state: neuroglancer.viewer_config_state.ActionState
        """
        self.set_edge_ids_temp.append(self._get_sv_id(action_state))
        if action_state.mouse_voxel_coordinates is not None:
            self.set_edge_loc_temp.append(
                [int(x) for x in action_state.mouse_voxel_coordinates])

    def _get_sv1_for_merging(self, action_state):
        """Retrieves information of the first segment to fix a false split

        Args:
            action_state: neuroglancer.viewer_config_state.ActionState
        """
        self.upd_msg('retrieving first segment id for edge setting...')
        # reset temporary attributes for edge setting
        self.set_edge_ids_temp = []
        self.set_edge_loc_temp = []
        self._get_edge_information(action_state=action_state)

    def _get_sv2_for_merging(self, action_state):
        """Retrieves information of the second segment to fix a false split and
        calls _direct_merging

        Args:
            action_state : neuroglancer.viewer_config_state.ActionState
        """
        if not self.set_edge_loc_temp:
            msg = "For merging SV retrieve the 1. segment id of the edge with" \
                  " keyq first"
            self.upd_msg(msg)
            return
        self.upd_msg('retrieving second segment id for edge setting...')
        self._get_edge_information(action_state=action_state)
        self._direct_merging()

    def _direct_merging(self):
        """Directs merging of segments to fix a false agglomeration split

        Temporary attributes for edge setting are checked. The action history is
         updated and the setting of the edge directed.
        """
        break_condition = [0 in self.set_edge_ids_temp,
                           None in self.set_edge_ids_temp,
                           self.set_edge_ids_temp[0] == self.set_edge_ids_temp[
                               1]
                           ]
        if any(break_condition):
            msg = 'cursor misplaced - try again by setting first edge node'
            self.upd_msg(msg)
            return
        else:
            self.action_history.append({'set': deepcopy(self.graph.graph)})

            # ensure only one edge can be set between a given pair of svs and
            # allow updating the location entry for a pair in edge_to_set
            self.edges_to_set.update([edge for edge in self.edges_to_set
                                      if set(edge[1]) != set(
                                        self.set_edge_ids_temp)])
            self.edges_to_set.append(
                [self.set_edge_loc_temp, self.set_edge_ids_temp])

            self._direct_edge_setting()

    def _direct_edge_setting(self):
        """Directs setting of an edge

        If a segment is new its agglomerated segment group is retrieved via the
        BrainMaps API and added to the neuron's graph.
        """
        novel_svs = [sv_id for sv_id in self.set_edge_ids_temp
                     if sv_id not in self.graph.graph.keys()]
        if novel_svs:
            Thread(target=self._add_edge_to_novel_sv,
                   args=(novel_svs, deepcopy(self.set_edge_ids_temp),),
                   daemon=True).start()
        else:
            self._set_edge(deepcopy(self.set_edge_ids_temp))

    def _add_edge_to_novel_sv(self, novel_svs, edge):
        """Adds an edge when at least one of the segments is not yet part of the
        neuron graph.

        Args:
            novel_svs(list) : list of segment ids that should be added to the
                              neuron graph
            edge(list) : edge to set
        """
        for sv in novel_svs:
            self._add_novel_sv_to_graph(sv)
        self._set_edge(edge)

    def _add_novel_sv_to_graph(self, sv):
        """Retrieves the agglomeration graph of sv via the BrainMapsApi and adds
         it to the neuron, displays msg upon finishing

        The lengthy API request that should run on a separate thread to free the
        main thread

        Args:
            sv (int) : segment id
        """
        edges = self.graph_tools.get_graph(sv)
        if type(edges[0]
                ) == int:  # segment has no partner in agglomeration
            self.graph.add_node(edges[0])
        else:
            self.graph.add_edge(edges)

        msg = 'segment ' + str(sv) + ' was added to the neuron graph'
        self.upd_msg(msg)

    def _set_edge(self, edge):
        """Sets an edge, updates viewer and displays according message

        Args:
            edge(list) : pair of segment ids between which an edge should be set
        """
        self.graph.add_edge(edge)
        self._upd_viewer()
        msg = 'an edge was set between ' + str(self.set_edge_ids_temp[0]) + \
              ' and ' + str(self.set_edge_ids_temp[1])
        self.upd_msg(msg)

    # SPLIT FALSE MERGER
    def _show_connected_partners(self, action_state):
        """Retrieves all segments connected to the base volume segment at the
        cursor location and displays them.

        Args:
            action_state : neuroglancer.viewer_config_state.ActionState
        """
        segment = self._get_sv_id(action_state)
        if segment is not None and segment != 0:
            self.upd_msg('retrieving segments connected to ' + str(segment))
            self.del_edge_ids = [segment]
            # retrieve partners locally if segment is already in the graph
            # -> allows to split edges that were only set locally (should be
            # undone with crtl+z though)
            if segment in self.graph.graph.keys():
                partners = self.graph.graph[segment] + [segment]
            else:
                partners = set(flat_list(self.graph_tools.get_edges(segment)))
            self._upd_viewer_segments(self.base_layer, partners)
            msg = 'Move cursor to falsely merged partner and press ctrl+x to ' \
                  'split'
            self.upd_msg(msg)
        else:
            msg = 'cursor misplaced'
            self.upd_msg(msg)

    def _split_merger(self, action_state):
        """Splits the edge between the segments in the temporary del_edge_ids,
        updates the neuron's graph & the viewer.

        Args:
            action_state : neuroglancer.viewer_config_state.ActionState
        """
        if not self.del_edge_ids:
            return
        segment = self._get_sv_id(action_state)
        if not (self.del_edge_ids[0] in self.graph.graph.keys()
                and segment in self.graph.graph.keys()):
            msg = 'The segments to split have to be both part of the neuron\'s' \
                  ' graph'
            self.upd_msg(msg)
            return
        if segment is not None and segment != 0:
            self.upd_msg('splitting edge between ' + str(segment) + ' and ' +
                         str(self.del_edge_ids[0]))
            self.del_edge_ids.append(segment)
            self.action_history.append({'del': deepcopy(self.graph.graph)})
            self.graph.del_edge(self.del_edge_ids)
            self.edges_to_delete.append(self.del_edge_ids)
            self.del_edge_ids = []
            self._upd_viewer(clear_viewer=True)
            msg = 'Check if the false merger has been successfully split. If ' \
                  'so, move the cursor to the segment that is supposed to be ' \
                  'removed from the neuron and press keyk. Otherwise search ' \
                  'for another supervoxel pair causing the false merger.'
            self.upd_msg(msg)

    def _confirm_merge_split(self, action_state):
        """Cleans up neuron's graph after a false agglomeration merger has been
         resolved and updates viewer.

        The segment id at the cursor position is retrieved and it's connected
        partners in the agglomeration are identified in the connected component
        dictionary. These segments are removed from the neuron's graph.

        Args:
            action_state : neuroglancer.viewer_config_state.ActionState
        """
        sv_id = self._get_sv_id(action_state)
        if sv_id == 0:
            msg = 'cursor misplaced'
            self.upd_msg(msg)
            return
        self.upd_msg('updating neuron graph after merge split')
        cc_id = next(idx for idx, members in self.graph.cc.items()
                     if sv_id in members)
        self.graph.del_node(self.graph.cc[cc_id])
        self._upd_viewer(clear_viewer=True)
        self.upd_msg('Done!')

    # SPLIT GROUP
    def _remove_merged_group(self):
        """Splits equivalences of a group of segments displayed in the base
        volume viewport to all other segments."""
        segments = list(self.viewer.state.layers[self.base_layer].segments)
        self.upd_msg('removing segments ')
        if all([sv in self.graph.graph.keys() for sv in segments]):
            edge_list = self.graph.return_edge_list(segments)
        else:
            edge_list = self.graph_tools.get_edges(segments)
        edges_to_remove = isolate_set(segments, edge_list)
        self.action_history.append(
            {'split': [edges_to_remove,
                       deepcopy(self.graph.graph)]})
        self.edges_to_delete += edges_to_remove
        self.graph.del_node(segments)
        self._upd_viewer(clear_viewer=True)
        self.upd_msg('Done!')

    # UNDO FUNCTIONS
    def _undo_last_action(self):
        """Revokes last action modifying the neuron's graph."""
        if any(self.action_history):
            last_action = [*self.action_history[-1].keys()][0]
            self.graph.graph = self.action_history[-1][last_action]
            sv = None
            if last_action == 'set':
                self.edges_to_set.pop()
            elif last_action == 'del':
                self.edges_to_delete.pop()
            elif last_action == 'split':
                self.graph.graph = self.action_history[-1][last_action][-1]
                edges_removed = self.action_history[-1][last_action][0]
                self.edges_to_delete -= edges_removed

            if self.graph.graph.keys():
                self.graph.update_cc()
            else:
                self.graph.cc = dict()
            self._upd_viewer(clear_viewer=True)
            self.action_history.pop(-1)
