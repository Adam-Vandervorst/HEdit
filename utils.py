"""
This file provides utilities for handling structures made with H-EDit.
Currently, only a quite bare-bones and low-performance class is available, HDict.
After saving your structure with pressing 'S' in H-Edit, you can load it here with `HDict.load_from_path`.
In Python console, you can write help(HDict) to view the useful methods, and the README contains links to example projects.
"""
import json
from collections import UserDict


class HDict(UserDict):
    """
    A thin wrapper around builtin dicts that provides utilities for the H-Edit storage format.

    Assumes the following structure:
    {
        data: [{data: str, id: int, ...}, ...],
        conn: [(Id, Id), ...]
    }
    where Id is either integer or (Id, Id).
    """

    def get_info(self, node_ids, *fields):
        """
        Takes node ids and yields specified fields in (ordered) tuples.
        If no fields are specified, the node dict (reference) is provided instead.
        If only a single field, just the content of that field is provided.

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

        for e in self['conn']:
            src, dst = e if direction == 'outgoing' else reversed(e)

            if src != item_id:
                continue
            to_node = isinstance(dst, int)
            if (returns == 'edges' and to_node) or (returns == 'nodes' and not to_node):
                continue
            if all(any(e == e_ for e_ in self.connected(via_id, direction='outgoing'))
                   for via_id in via_ids):
                yield dst

    def as_adjacency(self, omit_empty=True, direction='outgoing'):
        """
        Returns a generalized adjacency dict with tuple-id's for edges.
        What should be considered adjacency can be controlled with 'direction'.
        If 'omit_empty' is true, items with no adjacent items are not included.
        """
        adjacency = {}
        node_ids, edge_ids = [n['id'] for n in self['data']], self['conn']
        for i in node_ids + edge_ids:
            nbs = list(self.connected(i, direction=direction))
            if omit_empty and not nbs:
                continue
            adjacency[i] = nbs
        return adjacency

    def as_hypergraph(self, remove_subsumed=True):
        """
        Returns a list of directed hyper-edges.
        For example, T-edge (0 -> (1 <-> 2)) gets converted to hyper-edges (0, 1, 2) and (0, 2, 1).
        If 'remove_subsumed' is true, a T-edge is only converted if there is no T-edge pointing to it.
        Alternatively, subsumed can be interpreted on hyper-edges as conforming to the following function:

        def subsumed(enclosing, e):
            start_i = len(enclosing) - len(e)
            if start_i < 0:  # <= would be strictly subsumed
                return False
            return enclosing[start_i:] == e
        """
        if 'mode' in self and self['mode'] == 'H':
            raise ValueError("H's can not be sensibly interpreted as hypergraphs.")

        def tedge_to_hyperedge(e):
            yield e[0]
            if isinstance(e[1], tuple):
                yield from tedge_to_hyperedge(e[1])
            else:
                yield e[1]

        return [tuple(tedge_to_hyperedge(e)) for e in self['conn']
                if not remove_subsumed or next(self.connected(e, direction='incoming'), None) is None]

    def split_node_types(self):
        """
        For some property graphs - a digraph where every edge is tagged with a set of nodes - a nice interpretation exists.
        Namely nodes can have categories, labels, and certain kinds of neighbors.
        This function returns three useful node types for this interpretation if every nodes falls into one of these cases:
        1. only connect to other nodes with exactly 1 tag and is either a source or a sink node
        2. only connect to regular edges and have no incoming connections
        3. be connected to the same number of 1. nodes as the other nodes in 3. (not enforced)
        """
        if 'mode' in self and self['mode'] != 'property_graph':
            raise ValueError("Node types are a feature of property-graphs only.")

        match_zero = lambda way, node: next(self.connected(node['id'], **way), None) is None
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

        for dct in map(dict.copy, self.get_info(type_3)):
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

        Raises file errors or JSONDecodeError for 1. ValueError for 2. and prints a warning for 3.
        """
        modes = ['H', 'T', 'property_graph', 'edge_colored_graph', 'graph']

        with open(path) as f:
            dct = json.load(f)

        if not ('data' in dct and 'conn' in dct):
            raise ValueError("HEdit json at least contains 'data' and 'conn' fields.")

        if ('version' in dct and dct['version'] < 2) or ('version' not in dct and dct['conn'] and isinstance(dct['conn'][0], dict)):
            raise ValueError(f"Please load {path} into H-Edit and save it again, it's outdated.")

        if 'mode' in dct and not modes.index(mode) <= modes.index(dct['mode']):
            print(f"Required mode {mode!r} is stricter than found mode {dct['mode']!r}.")

        def to_tuple(list_id):
            if isinstance(list_id, list):
                return tuple(to_tuple(t) for t in list_id)
            return list_id

        dct['conn'] = list(map(to_tuple, dct['conn']))
        return cls(dct)


def maybe_self_loop(it):
    """
    If there's a pair (a, a) in `it`, returns a, else returns None.
    """
    for i, o in it:
        if i == o:
            return i
    return None


def maybe_duplicate(it, sink=False):
    """
    Returns the a duplicate value in the source or sink position, if it exists.
    """
    extrema = set()
    for e in map(itemgetter(sink), it):
        if e in extrema:
            return e
        extrema.add(e)
    return None


def maybe_single(it, sink=False):
    """
    Returns the value of the sole source or sink, if it exists.
    """
    ss_it = map(itemgetter(sink), it)
    value = next(ss_it, None)
    for e in ss_it:
        if e != value:
            return None
    return value


def maybe_cycle_elem(it):
    """
    Returns pair that completes a cycle, if there are cycles.
    """
    reachable = defaultdict(set)

    for s, d in it:
        reachable[s].add(d)

        for a, bs in list(reachable.items()):
            if s in bs:
                if a == d or a in reachable[d]:
                    return s, d
                bs.add(d)
                bs.update(reachable[d])
    return None
