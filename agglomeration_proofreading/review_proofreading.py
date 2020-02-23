from agglomeration_proofreading.neuron_proofreader import NeuronProofreading
from pathlib import PurePath, Path
from copy import deepcopy


class ProofreaderMaster(NeuronProofreading):
    def __init__(self,
                 dir_path,
                 graph_tool,
                 base_vol,
                 raw_data,
                 data,
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
            data (dict) : data from previous review session (optional)
            initial_graph (dict) : neuron_graph of the neuron before the
                                   proofreading round
            edges_to_delete_coord (list, optional) : list with the coordinates
                                                     of the edges that should be
                                                     deleted
        """

        super(ProofreaderMaster, self).__init__(dir_path,
                                                graph_tool,
                                                base_vol,
                                                raw_data,
                                                data,
                                                timer_interval=None,
                                                remove_token=False)
        self.initial_graph = initial_graph
        self.updated_graph = None
        self.current_graph = 'updated'

        # initiate edge_lists for visiting edges set/deleted and modifying
        # edges de novo
        self.check_set_edges = [edge[0][0] for edge in self.edges_to_set]
        self.check_set_edges_ids = [edge[1] for edge in self.edges_to_set]

        self.coord_list_names = ['check_set_edges']
        if edges_to_delete_coord is not None:
            self.check_deleted_edges = edges_to_delete_coord
            self.coord_list_names.append('check_deleted_edges')
        self.mk_coord_list_maps()

    def _set_keybindings(self):
        """"""
        super(ProofreaderMaster, self)._set_keybindings()
        # custom keybindings
        # 5. set edges (batch or single)
        # 6. delete edge from active list
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
            self.graph.graph = deepcopy(self.initial_graph)
            self.graph.update_cc()
            self.initial_graph = None
            self.current_graph = 'initial'
            self._upd_viewer(clear_viewer=True)
        elif self.current_graph == 'initial':
            self.initial_graph = deepcopy(self.graph.graph)
            self.graph.graph = deepcopy(self.updated_graph)
            self.graph.update_cc()
            self.updated_graph = None
            self.current_graph = 'updated'
            self._upd_viewer(clear_viewer=True)
        else:
            raise ValueError('this should be impossible')

    # overwrite callbacks that modify the graph to prevent modifying the initial
    # graph instead of the updated
    def _get_sv1_for_merging(self):
        """"""
        if self.current_graph == 'initial':
            self.display_action_forbidden_msg()
        elif self.current_graph == 'updated':
            super()._get_sv1_for_merging()

    def _get_sv2_for_merging(self):
        """"""
        if self.current_graph == 'initial':
            self.display_action_forbidden_msg()
        elif self.current_graph == 'updated':
            super()._get_sv2_for_merging()

    def _show_connected_partners(self):
        """"""
        if self.current_graph == 'initial':
            self.display_action_forbidden_msg()
        elif self.current_graph == 'updated':
            super()._show_connected_partners()

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

    def set_current_location(self):
        """displays the base segments of the edges set or deleted"""
        super().set_current_location()
        if self.coord_list_names[self.cur_coord_list_idx] == 'check_set_edges':
            sv_ids = self.check_set_edges_ids[self.cur_coord_idx]
        elif self.coord_list_names[
            self.cur_coord_list_idx] == 'check_deleted_edges':
            sv_ids = self.edges_to_delete[self.cur_coord_idx]
        else:
            print('this should not happen')
            return
        self._upd_viewer_segments('base', sv_ids)

    def delete_cur_coord_list_item(self):
        """remove edge fom id list as well to maintain consistency for segments
        displayed"""
        super().delete_cur_coord_list_item()
        if self.coord_list_names == 'check_set_edges':
            self.check_set_edges_ids.pop(self.cur_coord_idx)
        elif self.coord_list_names == 'check_deleted_edges':
            self.edges_to_delete.pop(self.cur_coord_idx)
