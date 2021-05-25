import json
from collections import UserDict


class HDict(UserDict):
    """
    A thin wrapper around builtin dicts that provides utilities for the H-Edit storage format.

    Assumes the following structure:
    {
        data: [{data: str, id: int, ...}, ...],
        conn: [{src: Id, dst: Id}, ...]
    }
    where Id is either integer or {src: Id, dst: Id}.
    """

    def get_info(self, node_ids, *fields):
        """
        Takes a node id and yield specified fields in the order they are provided.
        If no fields are specified, the node is returned.

        Raises KeyError if a node id is not present.
        """
        if isinstance(node_ids, int):
            node_ids = [node_ids]

        for node_id in node_ids:
            for node in self['data']:
                if node['id'] == node_id:
                    if not fields:
                        yield node
                    elif len(fields) == 1:
                        yield node[fields[0]]
                    else:
                        yield tuple(map(node.get, fields))
                    break
            else:
                raise KeyError(f"No node with id {node_id} found.")

    def find_nodes(self, prop, fits=lambda prop, node: prop == node['data']):
        """
        Yields all nodes matching data with some definition of matching 'fits'.
        By default this is equality to the nodes' data.
        """
        for node in self['data']:
            if fits(prop, node):
                yield node

    def get_node_id(self, data, allowed=None, disallowed=()):
        """
        Unambiguously retrieves the id of a node matching data.
        Allowed and disallowed id lists may be provided to uniquify the result.

        Raises KeyError if no matches are found and ValueError if more than one match is found.
        """
        results = [n['id'] for n in self.find_nodes(data)
                   if (allowed is None or n['id'] in allowed) and n['id'] not in disallowed]
        if not results:
            raise KeyError(f"No node with data {data!r} found.")
        if len(results) > 1:
            raise ValueError(f"Ambiguous id retrieval for {data!r},"
                             "following nodes have this data:\n" + '\n'.join(map(str, results)))
        return results[0]

    def connected(self, item_id, *via_ids, returns='both', direction='outgoing'):
        """
        Yields all connected ids of an item if they're connected via all via_ids.
        If direction is 'outgoing' or 'incoming', yields all destinations/children or sources/parent respectively.
        When direction is 'both', returns all items connected to given item.
        The item_id can be either the id of a node or an edge.
        The returned items can be filtered to to contain 'nodes', 'edges', or 'both'.
        """
        if direction == 'both':
            yield from self.connected(item_id, *via_ids, returns=returns, direction='incoming')
            yield from self.connected(item_id, *via_ids, returns=returns, direction='outgoing')
            return

        from_label, to_label = ('src', 'dst') if direction == 'outgoing' else ('dst', 'src')

        for edge in self['conn']:
            if edge[from_label] != item_id:
                continue
            is_node = isinstance(edge[to_label], int)
            if (returns == 'edges' and is_node) or (returns == 'nodes' and not is_node):
                continue
            if all(any(conn == edge for conn in self.connected(via_id, direction='outgoing'))
                   for via_id in via_ids):
                yield edge[to_label]

    def split_node_types(self):
        """
        For some property graphs - where every edge is tagged with a (possibly empty) set of nodes - a nice interpretation exists.
        Namely nodes can have categories, labels, and certain kinds of neighbors.
        This function returns three useful node types for this interpretation if every nodes falls into one of these cases:
        1. only connect to other nodes with exactly 1 tag and is either a source or a sink node
        2. only connect to regular edges and have no incoming connections
        3. be connected to the same number of 1. nodes as the other nodes in 3 (not enforced)
        """
        if 'mode' in self and self['mode'] != 'property_graph':
            raise ValueError("Object list creation only possible with property-graphs.")

        match_zero = lambda way, node: all(False for _ in self.connected(node['id'], **way))
        id_set = lambda it: {n['id'] for n in it}

        no_incoming = id_set(self.find_nodes({'direction': 'incoming'}, match_zero))
        no_outgoing = id_set(self.find_nodes({'direction': 'outgoing'}, match_zero))
        only_to_nodes = id_set(self.find_nodes({'returns': 'edges', 'direction': 'outgoing'}, match_zero))
        only_to_edges = id_set(self.find_nodes({'returns': 'nodes', 'direction': 'outgoing'}, match_zero))

        type_1 = (no_incoming | no_outgoing) & only_to_nodes
        type_2 = no_incoming & only_to_edges
        type_3 = id_set(self['data']) - type_1 - type_2

        assert type_1 | type_2 | type_3 == id_set(self['data'])
        assert type_1 & type_2 == type_2 & type_3 == type_3 & type_1 == set()

        return type_1, type_2, type_3

    def as_object_adjacency(self, type_1, type_2, type_3):
        """
        Uses the types from `split_node_types` to return an adjacency structure with the implied objects.
        Specifically this function produces a id-object of where each object is a type 3 node with the following structure:
        {
            **type_3 node,
            type_2 node data: type_1 node data, ...,
            type_2 node data: [type_3 node id, ...], ...,
            type_2 node data: [type_1 node data, ...], ...,
        }
        """
        adjacency = {}

        for dct in self.get_info(type_3):
            i = dct['id']

            for pi in type_2:
                p, = self.get_info(pi, 'data')
                maybe_vi = set(self.connected(i, pi, direction='incoming')) & type_1
                for v in self.get_info(maybe_vi, 'data'):
                    dct[p] = v
                    break
                else:
                    vs = set(self.connected(i, pi, direction='outgoing'))
                    dct[p] = list(vs if vs <= type_3 else self.get_info(vs & type_1, 'data'))
            adjacency[i] = dct
        return adjacency

    @classmethod
    def load_from_path(cls, path, mode='T'):
        """
        Load an H-Edit file from the given path and constructs the object if:
        1. it can be read and parsed as a json
        2. contains the necessary 'data' and 'conn' fields
        3. complies to the restrictions implied by mode

        Raises ValueError for 2. and prints a warning for 3.
        """
        modes = ['H', 'T', 'property_graph', 'edge_colored_graph', 'graph']

        with open(path) as f:
            dct = json.load(f)

        if not ('data' in dct and 'conn' in dct):
            raise ValueError("HEdit json at least contains 'data' and 'conn' fields.")

        if 'mode' in dct and not modes.index(mode) <= modes.index(dct['mode']):
            print(f"Required mode {mode!r} is stricter than found mode {dct['mode']!r}.")
        return cls(dct)
