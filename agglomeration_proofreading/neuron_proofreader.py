import neuroglancer
import os
import pickle

from copy import deepcopy
from datetime import datetime
from threading import Lock

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
    - to jump to the last unfinished branch location press "`"
    - to tag a branch point as visited press "ctrl + r". It will be annotated
        with an ellipsoid and not be revisited when pressing "`"

    5. storing segmentation merger locations:
    - move the viewport center to the merge site (e.g. right click) and press
        "m"

    6. storing misalignment locations:
    - move the viewport center to the misaligned site (e.g. right click) and
        press "p"

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
    """

    def __init__(self,
                 dir_path,
                 graph_tool,
                 base_vol,
                 raw_data,
                 data=None,
                 timer_interval=300):
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
            data (dict) : data from previous review session (optional):
            autosave_interval (int) : autosave interval in sec (optional)
        """

        # set (default) attributes
        self.set_edge_ids = []
        self.set_edge_loc = []
        self.del_edge_ids = []
        self.dir_path = dir_path
        self.graph = LocalGraph()
        self.graph_tools = graph_tool
        self.var_names = [
            'edges_to_set', 'edges_to_delete', 'action_history',
            'branch_point', 'segmentation_merger_loc', 'misalignment_locations'
        ]
        for name in self.var_names:
            setattr(self, name, CustomList([]))
        self.lock = Lock()
        self.base_layer = 'base'
        self.aggl_layer = 'agglo'
        layers = {self.aggl_layer: base_vol, self.base_layer: base_vol}

        super(NeuronProofreading, self).__init__(raw_data=raw_data,
                                                 layers=layers,
                                                 annotation=True,
                                                 timer_interval=timer_interval)

        # initiate stuff
        with self.viewer.txn() as s:
            s.layers[self.base_layer].selectedAlpha = 0
            s.concurrent_downloads = 256
        self.timer.start_timer(func=self._auto_save)

        # load data
        if data is not None:
            self._load_data(data)
        self.action_history.max_length = 10

    # autosave upon exit
    def exit(self):
        self._auto_save()
        super().exit()

    # VIEWER SETUP
    def _set_keybindings(self):
        """Binds key board events to call back functions"""
        super()._set_keybindings()
        self.viewer.actions.add('select-custom', self._handle_select)
        self.viewer.actions.add('get_first_sv_to_merge',
                                self._first_svid_for_merging)
        self.viewer.actions.add('set_equivalence', self._merge_segments)
        self.viewer.actions.add('set_branch_point',
                                lambda s: self._store_branch_loc())
        self.viewer.actions.add('remove_branchpoint',
                                lambda s: self.remove_branch_loc())
        self.viewer.actions.add('jump_to_last_branchpoint',
                                lambda s: self._jump_to_branch_loc())
        self.viewer.actions.add('store_misalignment_loc',
                                lambda s: self._store_misalignment_loc())
        self.viewer.actions.add('store_merger_loc',
                                lambda s: self._store_merger_loc())
        self.viewer.actions.add('show_connected_partners',
                                self._show_connected_partners)
        self.viewer.actions.add('split_merger', self._split_merger)
        self.viewer.actions.add('confirm_merge_split',
                                self._confirm_merge_split)
        self.viewer.actions.add('remove_merged_group',
                                lambda s: self._remove_merged_group())
        self.viewer.actions.add('toggle_neuron_display',
                                lambda s: self._toggle_neuron())
        self.viewer.actions.add('del_sv_from_neuron', self._del_sv_from_neuron)
        self.viewer.actions.add('add_sv_to_neuron',
                                lambda s: self._add_sv_to_neuron(s))
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

        with self.viewer.config_state.txn() as s:
            s.input_event_bindings.data_view['dblclick0'] = 'select-custom'
            s.input_event_bindings.data_view['keyq'] = 'get_first_sv_to_merge'
            s.input_event_bindings.viewer['keyd'] = 'set_equivalence'
            s.input_event_bindings.viewer['keyc'] = 'show_connected_partners'
            s.input_event_bindings.viewer['control+keyx'] = 'split_merger'
            s.input_event_bindings.viewer['keyk'] = 'confirm_merge_split'
            s.input_event_bindings.viewer[
                'control+bracketright'] = 'remove_merged_group'
            s.input_event_bindings.viewer['keyn'] = 'toggle_neuron_display'
            s.input_event_bindings.viewer['control+keya'] = 'add_sv_to_neuron'
            s.input_event_bindings.viewer['shift+keyf'] = 'del_sv_from_neuron'
            s.input_event_bindings.viewer['keyy'] = 'set_branch_point'
            s.input_event_bindings.viewer['control+keyr'] = 'remove_branchpoint'
            s.input_event_bindings.viewer[
                'backquote'] = 'jump_to_last_branchpoint'
            s.input_event_bindings.viewer['control+keys'] = 'save_data'
            s.input_event_bindings.viewer['control+keyz'] = 'undo_last_action'
            s.input_event_bindings.viewer['keyp'] = 'store_misalignment_loc'
            s.input_event_bindings.viewer['keym'] = 'store_merger_loc'
            s.input_event_bindings.viewer[
                'digit2'] = 'toggle_opacity_agglomeration'
            s.input_event_bindings.viewer[
                'digit3'] = 'toggle_opacity_base'
            s.input_event_bindings.viewer['keyf'] = 'empty_base_vol'

    # VIEWER INTERACTION
    def _handle_select(self, action_state):
        """Overrides the neuroglancer response to a double click to maintain its
        default functionality: select or unselect a segment from display.

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
            segments_base = s.layers[self.base_layer].segments
            if segment_id in segments_base:
                segments_base.remove(segment_id)
            else:
                segments_base.add(segment_id)

            eqv_set = s.layers[self.aggl_layer].equivalences.sets()
            viewer_seg = s.layers[self.aggl_layer].segments
            segments_aggl = flat_list(eqv_set)

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
                agglo_id = self.graph_tools.get_agglo_id(segment_id)
                members = self.graph_tools.get_members(agglo_id)
                s.layers[self.aggl_layer].segments.add(agglo_id)
                s.layers[self.aggl_layer].equivalences.union(*members)

    def _get_sv_id(self, action_state):
        """returns id of the segment at cursor position from a neuroglancer
        action state

        Args:
            action_state : neuroglancer.viewer_config_state.ActionState

        Returns:
            segment id : int or None
        """
        try:
            selected_object = action_state.selected_values[self.base_layer]
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

    def _add_sv_to_neuron(self, action_state):
        """Adds segments to the neuron's graph and triggers a viewer update.

        Segment id at the current cursor location in the viewer is retrieved.
        The agglomerated graph of this segment is retrieved and added to the
        neuron's graph.

        Args:
            action_state: neuroglancer.viewer_config_state.ActionState
        """
        sv = self._get_sv_id(action_state)
        if type(sv) == int:
            self.action_history.append(
                {'add_segment': deepcopy(self.graph.graph)})
            edges = self.graph_tools.get_graph(sv)
            self.graph.add_edge(edges)
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
            self.action_history.append(
                {'del_segment': deepcopy(self.graph.graph)})
            idx = next(idx for idx, members in self.graph.cc.items()
                       if sv in members)
            members = self.graph.cc[idx]
            self.graph.del_node(members)
            self._upd_viewer(clear_viewer=True)

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
        for name in self.var_names:
            temp = CustomList([])
            temp += data[name]
            setattr(self, name, temp)
        self.graph.graph = data['neuron_graph']
        self.graph.update_cc()
        self._upd_viewer()
        annocount = 0
        if any(self.branch_point):
            for point in self.branch_point:
                if point[1]:
                    annocount += 1
                    self.annotation._make_ellipsoid('', point[0])
        self.annotation.anno_id = annocount
        self.set_viewer_loc(data['last_position'])

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
        fn = '{0:%y%m%d}_{0:%H%M%S}_agglomerationReview.pickle'.format(
            datetime.now())
        sv_fn = os.path.join(self.dir_path, fn)
        new_data = dict()
        for name in self.var_names:
            new_data[name] = list(getattr(self, name))
        new_data['last_position'] = self.get_viewport_loc()
        new_data['neuron_graph'] = self.graph.graph
        with open(sv_fn, 'wb') as f:
            pickle.dump(new_data, f)
        for name in self.var_names:
            setattr(getattr(self, name), 'unsaved_changes', False)

    def _store_misalignment_loc(self):
        self.misalignment_locations.append(self.get_viewport_loc())

    def _store_merger_loc(self):
        self.segmentation_merger_loc.append(self.get_viewport_loc())

    # BRANCH POINTS
    def _store_branch_loc(self):
        """ stores the current voxel location of the viewerstate as a
        branchpoint"""
        coord = self.get_viewport_loc()
        if coord not in self.branch_point:
            self.branch_point.append([coord, False])

    def remove_branch_loc(self):
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

    # MERGE FALSE SPLITS
    def _first_svid_for_merging(self, action_state):
        """For edge setting the first partner's segment id in the base volume
        and the cursor location are retrieved.

        Args:
            action_state: neuroglancer.viewer_config_state.ActionState
        """
        self.upd_msg('retrieving first segment id for edge setting...')
        self.set_edge_ids = [self._get_sv_id(action_state)]
        self.set_edge_loc = [action_state.mouse_voxel_coordinates]

    def _merge_segments(self, action_state):
        """For an edge to be set the second partner's id and location are
        retrieved and the edge information is stored.

        Args:
            action_state : neuroglancer.viewer_config_state.ActionState
        """
        if self.set_edge_loc is None:
            msg = "For merging SV retrieve the 1. segment id of the edge with" \
                  " keyq first"
            self.upd_msg(msg)
            return

        self.set_edge_loc.append(action_state.mouse_voxel_coordinates)
        self.set_edge_ids.append(self._get_sv_id(action_state))
        break_condition = [
            0 in self.set_edge_ids, None in self.set_edge_ids,
            self.set_edge_ids[0] == self.set_edge_ids[1]
        ]
        if any(break_condition):
            self.set_edge_ids = None
            self.set_edge_loc = None
            msg = 'cursor misplaced - try again by setting first edge node'
            self.upd_msg(msg)
            return
        else:
            self.upd_msg(
                'retrieving second segment id for edge setting...')  # never displays this
            self.action_history.append({'set': deepcopy(self.graph.graph)})
            # allows updating the location for an edge that is already present
            # in the list of edges to be set
            self.edges_to_set.update([edge for edge in self.edges_to_set
                                      if set(edge[1]) != set(self.set_edge_ids)
                                      ])
            self.edges_to_set.append([self.set_edge_loc, self.set_edge_ids])

            self._add_edge_to_neuron()

            msg = 'an edge was set between ' + str(self.set_edge_ids[0]) + \
                  ' and ' + str(self.set_edge_ids[1])
            self.upd_msg(msg)
            self.set_edge_ids = None
            self.set_edge_loc = None

    def _add_edge_to_neuron(self):
        """Adds an edge between segments in the temporary list set_edge_ids

        If a segment is new its agglomerated segment group is retrieved via the
        BrainMaps API and added to the neuron's graph. A viewer update is
        triggered.
        """
        novel_svs = [
            sv_id for sv_id in self.set_edge_ids
            if sv_id not in self.graph.graph.keys()
        ]
        if novel_svs:
            for node in novel_svs:
                edges = self.graph_tools.get_graph(node)
                if type(edges[0]
                        ) == int:  # segment has no partner in agglomeration
                    self.graph.add_node(edges[0])
                else:
                    self.graph.add_edge(edges)
        self.graph.add_edge(self.set_edge_ids)
        self._upd_viewer()

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
            self._upd_viewer(clear_viewer=True)
            msg = 'Check if the false merger has been successfully split. If ' \
                  'so, move the cursor to the segment that is supposed to be ' \
                  'removed from the neuron and press keyk. Otherwise search ' \
                  'for another supervoxel pair causing the false merger.'
            self.upd_msg(msg)
            self.edges_to_delete.append(self.del_edge_ids)

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
        self.del_edge_ids = []
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
