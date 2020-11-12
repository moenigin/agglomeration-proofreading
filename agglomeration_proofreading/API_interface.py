from ap_utils import int_to_list
from brainmaps_api_fcn.basic_requests import EmptyResponse


class GraphTools:
    """retrieves agglomeration information necessary to build the neuron graph
    via BrainMaps API"""

    def __init__(self, api_fcn):
        """initiates class, creates API access

        Args:
            api_fcn (BrainMapsAPI.BrainMapsRequest object) : see class
                                                            BrainMapsRequest
        """
        self.API_fcn = api_fcn

    def get_agglo_id(self, sv_id):
        """retrieves the id of the agglomerated segment to which sv_id belongs

        Args:
            sv_id (int) : segment id

        Returns:
            int: segment id in the agglomerated volume"""
        return self.API_fcn.get_map(sv_id)[0]

    def get_members(self, sv_id):
        """retrieves all members of the agglomerated segment to which sv_id
        belongs

        Args:
            sv_id (int or list) : segment id (list)

        Returns:
            dict : key = segment, values = members of the agglomerated parent
                   segments to sv_id


        """
        return self.API_fcn.get_groups(sv_id)

    def get_edges(self, ids):
        """retrieves all edges of all segments in ids

        Args:
            ids (int or list) : segment ids

        Returns:
            edges (list) : list of edges"""
        try:
            edges = self.API_fcn.get_equivalence_list(ids)
        # if ids is an isolated segment, the edge response is empty, downstream
        # needs to allow single segment in the returned edges list.
        except EmptyResponse:
            edges = int_to_list(ids)
        return edges

    def get_graph(self, sv_id):
        """returns all edges in the agglomerated segment to which sv_id belongs

        Args:
            sv_id (int, list) : segment id (list) for which the graph should be
                                fetched

        Returns:
            edges (dict) : key = segment id, values = list of all edges of the
                           agglomerated segment/parent of a given segment_id
            """
        members = self.get_members(sv_id)
        edges = {sv: self.get_edges(members[sv]) for sv in int_to_list(sv_id)}
        return edges