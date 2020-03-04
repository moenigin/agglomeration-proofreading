from brainmaps_api_fcn.basic_requests import EmptyResponse

from agglomeration_proofreading.ap_utils import int_to_list, return_other


def connected_components(graph):
    """Calculates connected components in a graph

    Args:
        graph (dict):
            keys : graph nodes
            values: list of connected partners, these nodes have to be in
                    graph.keys()

    Returns:
        cc (dict) :
            keys : component index
            values: list with node members of the component
    """
    visited = {sv: False for sv in graph.keys()}
    cc = {}
    idx = 0
    component = []
    queue = []

    sv_id = next(iter(graph.keys()))
    while False in visited.values():
        visited[sv_id] = True
        component.append(sv_id)

        queue.extend([sv for sv in graph[sv_id] if not visited[sv]])

        while visited[sv_id] and queue:
            sv_id = queue.pop(0)

        if not queue and visited[sv_id]:
            cc[idx] = (list(component))
            component = []
            idx += 1
            try:
                sv_id = next(sv for sv in graph.keys() if not visited[sv])
            except StopIteration:
                assert all(visited.values())
                break
    return cc


def isolate_set(sv_ids, edges):
    """ Returns all edges of sv_ids with exception to those among members of
    sv_ids.

    mimics the BrainMaps API function isolate_set with
    excludeEdgesWithinSet=True, i.e. it determines edges to split
    to isolate the group of segments in sv_ids from their (shared)
    agglomerated segment

    Args:
        sv_ids (int or list) : segment ids of the segment(s) that should be
                                isolated
        edges (list) : list of all edges of the segment(s) in sv_ids

    Returns:
        edges_to_split (list) : edges to split to isolate sv_ids from other
        segments.
    """
    edges_to_split = []
    for edge in edges:
        if edge[0] not in sv_ids or edge[1] not in sv_ids:
            edges_to_split.append(edge)
    return edges_to_split


class LocalGraph:
    """Class to represent neuron as a graph of agglomerated segments

    Nodes or edges can be added to or removed from the neuron's graph via the
    respective functions. The connected component attribute is automatically
    updated when the graph is changed.

    Attributes:
        graph (dict) : graph representing the neuron in the segmentation
            keys : graph nodes
            values: list of connected partners
        cc (dict) : connected components representation of the graph
            keys : component index
            values: list with member nodes of the component
        """

    def __init__(self):
        """Initiates attributes as empty dictionaries."""
        self.graph = dict()
        self.cc = dict()

    def add_node(self, node):
        """Adds node(s) to graph and updates connected components.

        Args:
            node (int or list) : node or list of node to add as key to the graph dict
        """
        for idx_ in int_to_list(node):
            self.graph[idx_] = []
            self._add_to_cc([idx_])

    def del_node(self, node):
        """Deletes node(s) from graph and updates connected component attribute.

        Args:
            node (int or list) : node or list of node to delete from the graph
                                dict
        """
        for idx_ in int_to_list(node):
            self.graph.pop(idx_, None)
            for sv_id, partner in self.graph.items():
                if idx_ in partner:
                    self.graph[sv_id].remove(idx_)
        self.update_cc()

    def add_edge(self, edge):
        """Checks edge input and prompts addition to the graph

        Args:
            edge (list) : list with single edge  or list of edges
        """
        if any(isinstance(item, list) for item in edge):
            for edge_ in edge:
                self.add_single_edge(edge_)
        else:
            self.add_single_edge(edge)

    def add_single_edge(self, edge):
        """Adds single edges to the graph and updates the connected component
        attribute. Edge members not present in the graph keys will be added.

        Args:
            edge (list) : list with edge members
        """
        for node in edge:
            if node not in self.graph.keys():
                self.add_node(node)
            partner = return_other(edge, node)
            if partner not in self.graph[node]:
                self.graph[node].append(partner)
        self._add_to_cc(edge)

    def check_in_graph(self, nodes):
        """checks whether nodes are in the graph

        Args:
            nodes (int, list) : id of nodes to check graph membership
        Returns:
            bool : True if all nodes are members in the graph
        """
        return all([node in self.graph.keys() for node in int_to_list(nodes)])

    def del_edge(self, edge):
        """Deletes edges from the graph and updates the connected component
        attribute.

        Args:
            edge (list) : list with single edge or list of edges
        """
        if any(isinstance(item, list) for item in edge):
            for edge_ in edge:
                self.del_single_edge(edge_)
        else:
            self.del_single_edge(edge)
        self.update_cc()

    def del_single_edge(self, edge):
        """Deletes a single edge from the graph"""
        if self.check_in_graph(edge):
            for node in edge:
                self.graph[node].remove(return_other(edge, node))
        else:
            print('not all nodes of', edge, 'are in the graph')

    def _add_to_cc(self, edge):
        """Updates connected component by adding edge

        If edge contains a single segment id, this is added as a separate
        component.

        Args:
            edge (list) : list with "edge", can be a single segment id
        """
        _map = {}
        for node in edge:
            _map.update({
                node: idx
                for idx, members in self.cc.items() if node in members
            })

        if not _map:
            if self.cc.keys():
                idx = max(list(self.cc.keys())) + 1
            else:
                idx = 0
            self.cc[idx] = edge.copy()

        elif len(_map) == 1:
            self.cc[list(_map.values())[0]].append(return_other(edge, *_map))

        elif len(_map) == 2 and _map[edge[0]] != _map[edge[1]]:
            combined_comp = self.cc[_map[edge[0]]] + self.cc[_map[edge[1]]]
            self.cc[_map[edge[0]]] = combined_comp
            self.cc.pop(_map[edge[1]])
            self.cc = {
                i: members
                for i, members in enumerate(self.cc.values())
            }

    def update_cc(self):
        """calculates connected component analysis for the graph"""
        self.cc = connected_components(self.graph)

    def return_edge_list(self, node):
        """Returns a list of edges for nodes in node

        Args:
            node (int or list) : node or list of nodes for which edge list
                                should be returned

        Returns:
            edges (list) : list of all edges nodes in node are part of
                            [[node1, node2], ...]
        """
        edges = []
        for sv_id in int_to_list(node):
            if sv_id in self.graph.keys():
                edges += [[sv_id, partner_id] for partner_id in
                          self.graph[sv_id]]
        return edges


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
