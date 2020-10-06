import json

from copy import deepcopy
from datetime import datetime
from pathlib import PurePath, Path

from agglomeration_proofreading.neuron_proofreader import NeuronProofreading
from agglomeration_proofreading.ap_utils import flat_list


class ProofreaderMaster(NeuronProofreading):
    def __init__(self,
                 dir_path,
                 graph_tool,
                 base_vol,
                 raw_data,
                 data,
                 edge_clusters,
                 initial_graph,
                 edges_to_delete_coord=None):
        """
        Args:
            dir_path (str) : path to directory for file saving
            graph_tool(neuron_graph.GraphTool) : functions to retrieve
                                                information about the
                                                agglomeration graph
            base_vol (str) : base segmentation volume id in form of
                             data_src:project:dataset:volume_name
            raw_data (str) : image data volume id in form of
                             data_src:project:dataset:volume_name
            data (dict) : data from previous review session
            edge_clusters (dict) : edges to set from previous

            initial_graph (dict) : neuron_graph of the neuron before the
                                   proofreading round
            edges_to_delete_coord (list, optional) : list of the edges that
                                                    should be deleted. Contains
                                                    a sublist with edge voxel
                                                    coordinates [x, y, z] at
                                                    position 0 and a sublist
                                                    with corresponding ids at
                                                    position 1
        """

        super(ProofreaderMaster, self).__init__(dir_path,
                                                graph_tool,
                                                base_vol,
                                                raw_data,
                                                data,
                                                timer_interval=None,
                                                remove_token=False)
        # empty attributes from latest revision round
        for attr in ['edges_to_set', 'edges_to_delete', 'action_history',
                     'branch_point']:
            setattr(self, attr, [])

        self.initial_graph = initial_graph
        self.graph_before_update = None
        self.updated_graph = None
        self.current_graph = 'updated'

        # initiate edge_lists for visiting edges set/deleted and modifying
        # edges de novo
        self.edge_clusters = edge_clusters
        self.cluster_centroids = [centroid for centroid in edge_clusters.keys()]
        # list in which the individual edges centers in a cluster get placed
        self.single_edge_list = []
        self.single_edge_list_ids = []

        self.coord_list_names = ['cluster_centroids', 'single_edge_list']
        if edges_to_delete_coord is not None:
            self.check_deleted_edges = edges_to_delete_coord[0]
            self.check_deleted_edges_ids = edges_to_delete_coord[1]
            self.coord_list_names.append('check_deleted_edges')
        self.mk_coord_list_maps()
        self.toggle_location_lists()

    def _set_keybindings(self):
        """"""
        super(ProofreaderMaster, self)._set_keybindings()
        self.viewer.actions.add('toggle_old_new_graph',
                                lambda s: self.toggle_old_new_graph())
        self.viewer.actions.add('toggle_location_lists',
                                lambda s: self.toggle_location_lists())
        self.viewer.actions.add('next_coordinate',
                                lambda s: self.next_coordinate())
        self.viewer.actions.add('prev_coordinate',
                                lambda s: self.prev_coordinate())
        self.viewer.actions.add('delete_cur_coord_list_item',
                                lambda s: self.delete_cur_coord_list_item())

        _DEFAULT_DIR = PurePath(Path(__file__).resolve()).parent
        fn = 'KEYBINDINGS_master.ini'
        config_file = _DEFAULT_DIR.joinpath(fn)
        if not Path(config_file).is_file():
            raise FileNotFoundError
        self._bind_pairs(config_file)

    def toggle_old_new_graph(self):
        """"""
        if self.current_graph == 'updated':
            self.updated_graph = deepcopy(self.graph.graph)
            self.graph.graph = deepcopy(self.graph_before_update)
            self.graph.update_cc()
            self.graph_before_update = None
            self.current_graph = 'initial'
            self._upd_viewer(clear_viewer=True)
        elif self.current_graph == 'initial':
            self.graph_before_update = deepcopy(self.graph.graph)
            self.graph.graph = deepcopy(self.updated_graph)
            self.graph.update_cc()
            self.updated_graph = None
            self.current_graph = 'updated'
            self._upd_viewer(clear_viewer=True)
        else:
            raise ValueError('this should be impossible')

    # overwrite callbacks that modify the graph to prevent modifying the initial
    # graph instead of the updated
    def _get_sv1_for_merging(self, action_state):
        """"""
        if self.current_graph == 'initial':
            self.display_action_forbidden_msg()
        elif self.current_graph == 'updated':
            super()._get_sv1_for_merging(action_state)

    def _get_sv2_for_merging(self, action_state):
        """"""
        if self.current_graph == 'initial':
            self.display_action_forbidden_msg()
        elif self.current_graph == 'updated':
            super()._get_sv2_for_merging(action_state)

    def _show_connected_partners(self, action_state):
        """"""
        if self.current_graph == 'initial':
            self.display_action_forbidden_msg()
        elif self.current_graph == 'updated':
            super()._show_connected_partners(action_state)

    def _remove_merged_group(self):
        """"""
        if self.current_graph == 'initial':
            self.display_action_forbidden_msg()
        elif self.current_graph == 'updated':
            super()._remove_merged_group()

    def display_action_forbidden_msg(self):
        """messages that action is forbidden because current graph is the
        initial neuron graph before proofreading"""
        msg = 'The current graph loaded is the initial graph before review ' \
              'which cannot be modified. Toggle graphs to edit'
        self.upd_msg(msg)

    def toggle_location_lists(self):
        """"""
        # single edges lists corresponding to current cluster should only ever
        # start at idx 0
        if self.coord_list_names[
            self.cur_coord_list_idx] == 'single_edge_list':
            self.cur_coord_idx = 0
        super().toggle_location_lists()
        if self.coord_list_names[
            self.cur_coord_list_idx] == 'check_deleted_edges':
            self.graph_before_update = self.initial_graph

    def set_current_location(self):
        """displays the base segments of the edges set or deleted"""
        super().set_current_location()
        self._handle_next_list_item()

    def delete_cur_coord_list_item(self):
        """remove edge fom id list as well to maintain consistency for segments
        displayed"""
        if self.coord_list_names[
            self.cur_coord_list_idx] == 'cluster_centroids':
            msg = 'Current list = check_edges_to_set! Clusters cannot be ' \
                  'deleted'
            self.upd_msg(msg)
            return

        super().delete_cur_coord_list_item()
        if self.coord_list_names[self.cur_coord_list_idx] == 'single_edge_list':
            self.single_edge_list_ids.pop(self.cur_coord_idx)
            # remove edge from the cluster lists as well
            curr_cluster_idx = self.coord_list_idx_map[0]
            current_key = list(self.edge_clusters.keys())[curr_cluster_idx]
            self.edge_clusters[current_key][2].pop(self.cur_coord_idx)
        elif self.coord_list_names[
            self.cur_coord_list_idx] == 'check_deleted_edges':
            self.edges_to_delete_ids.pop(self.cur_coord_idx)

    def _handle_next_list_item(self):
        """"""
        if self.coord_list_names[
            self.cur_coord_list_idx
        ] == 'cluster_centroids':
            current_key = list(self.edge_clusters.keys())[self.cur_coord_idx]
            edge_ids = self.edge_clusters[current_key][1]
            edge_center_coord = self.edge_clusters[current_key][0]

            # segment ids of the current cluster
            sv_ids = set(flat_list(self.edge_clusters[current_key][1]))
            # prepare lists for single edges of this cluster
            self.single_edge_list = edge_center_coord
            self.single_edge_list_ids = edge_ids
            map_idx = self.coord_list_names.index('single_edge_list')
            self.coord_list_map[map_idx] = self.single_edge_list

            # print('Edges to be deleted:', edge_ids)

            # calculate the fake initial graph in which only the edges of the
            # cluster are missing
            self._mk_fake_initial_graph(edge_ids)

        elif self.coord_list_names[
            self.cur_coord_list_idx
        ] == 'check_deleted_edges':
            sv_ids = self.edges_to_delete_ids[self.cur_coord_idx]
        elif self.coord_list_names[
            self.cur_coord_list_idx] == 'single_edge_list':
            sv_ids = self.single_edge_list_ids[self.cur_coord_idx]
        else:
            print('this should not happen')
            return
        self.upd_viewer_segments('base', sv_ids)

    def _mk_fake_initial_graph(self, edges):
        """Calculates fake initial graph

        In the faked initial graph only those edges set in the
        current cluster are missing from the updated post review graph

        Args:
            edges (list) :  list of edges (segment ids) of the current cluster
        """
        # ensure that the updated graph is loaded to the current graph
        # representation to calculate graph before local update
        if self.current_graph == 'initial':
            self.toggle_old_new_graph()
        # store updated graph in temp variable:
        temp = deepcopy(self.graph.graph)
        # delete edges in list to calculate graph before update
        self.graph.del_edge(edges)
        self.graph_before_update = self.graph.graph
        self.graph.graph = temp

    def _auto_save(self):
        """"""
        self._save_data()

    def _save_data(self):
        """"""
        fn = '{0:%y%m%d}_{0:%H%M%S}_ProofreadingReview.json'.format(
            datetime.now())
        sv_fn = Path(self.dir_path).joinpath(fn)
        # store edges to set in with coordinates and ids in different sublist
        edges_ids = []
        edge_coord = []
        for edge_list in self.edge_clusters.values():
            edges_ids.append(edge_list[1])
            edge_coord.append(edge_list[2])
        if any(self.edges_to_set):
            for edge in self.edges_to_set:
                edge_coord.append(edge[0])
                edges_ids.append(edge[1])

        edges_to_delete = []
        if hasattr(self, 'check_deleted_edges_ids'):
            edges_to_delete.append(self.check_deleted_edges_ids)

        if any(self.edges_to_delete):
            edges_to_delete.append(list(self.edges_to_delete))

        reviewed_data = dict()
        reviewed_data['edges_to_set'] = [edge_coord, edges_ids]
        reviewed_data['edges_to_delete'] = edges_to_delete

        with open(sv_fn, 'w') as f:
            json.dump(reviewed_data, f, sort_keys=False, indent=3,
                      separators=(',', ': '))
