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

    def find_nodes(self, data, fits=lambda provided, other: provided == other):
        """
        Yields all nodes matching data with some definition of matching 'fits'.
        By default this is equality.
        """
        for node in self['data']:
            if fits(data, node['data']):
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
            if all(any(conn == edge for conn in self.connected(via_id, direction=direction))
                   for via_id in via_ids):
                yield edge[to_label]

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

        if 'mode' in dct and not modes.index(mode) >= modes.index(dct['mode']):
            print(f"Required mode {mode!r} is stricter than found mode {dct['mode']!r}.")
        return cls(dct)
