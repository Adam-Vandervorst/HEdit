"""
This file provides utilities for handling structures made with H-EDit.
Currently, only a quite bare-bones and low-performance class is available, HDict.
After saving your structure with pressing 'S' in H-Edit, you can load it here with `HDict.load_from_path`.
In Python console, you can write help(HDict) to view the useful methods, and the README contains links to example projects.
"""
from collections import UserDict, defaultdict
from operator import itemgetter
from itertools import chain, tee
from functools import wraps
import dataclasses
import json


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
    def allow_in(*modes):
        def wrapper(method):
            @wraps(method)
            def safe_method(ins, *args, **kwargs):
                if 'mode' not in ins or ins['mode'] in modes:
                    return method(ins, *args, **kwargs)
                raise ValueError(f"{method.__name__} is only defined if the mode is any of {modes}.")
            return safe_method
        return wrapper

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
            n = next(self.find_nodes(id=node_id), None)
            if n is None:
                raise KeyError(f"No node with id {node_id} found.")
            yield itemgetter(*fields)(n) if fields else n

    def find_nodes(self, fits=lambda n: True, **criteria):
        """
        Yields all nodes matching 'fits' and satisfying each of the criteria fields.
        """
        for node in self['data']:
            if fits(node) and all(name in node and node[name] == value
                                  for name, value in criteria.items()):
                yield node

    def get_node_id(self, data, allowed=None, disallowed=()):
        """
        Unambiguously retrieves the id of a node matching data.
        Allowed and disallowed id lists may be provided to uniquify the result.

        Raises KeyError if no matches are found and ValueError if more than one match is found.
        """
        considered = lambda n: (allowed is None or n['id'] in allowed) and n['id'] not in disallowed
        result_it = map(itemgetter('id'), self.find_nodes(considered, data=data))

        result = next(result_it, None)
        if result is None:
            raise KeyError(f"No node with data {data!r} found.")
        conflict = next(result_it, None)
        if conflict is not None:
            raise ValueError(f"Ambiguous id retrieval for {data!r}: id {result} and {conflict}.")
        return result

    def connected(self, item_id, *via_ids, returns='both', direction='outgoing'):
        """
        Yields all connected ids of an item if they're connected via all via_ids.
        If direction is 'outgoing' or 'incoming', yields all destinations/children or sources/parent respectively.
        When direction is 'either', returns all items connected to given item.
        The item_id can be either the id of a node or an edge.
        The returned items can be filtered to to contain 'nodes', 'edges', or 'both'.
        """
        if direction == 'either':
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
        for i in chain(map(itemgetter('id'), self['data']), self['conn']):
            nbs = list(self.connected(i, direction=direction))
            if omit_empty and not nbs:
                continue
            adjacency[i] = nbs
        return adjacency

    @allow_in('T', 'property_graph', 'edge_colored_graph', 'graph')
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
        def tedge_to_hyperedge(s, d):
            yield s
            if isinstance(d, tuple):
                yield from tedge_to_hyperedge(*d)
            else:
                yield d

        return [tuple(tedge_to_hyperedge(*e)) for e in self['conn']
                if not remove_subsumed or next(self.connected(e, direction='incoming'), None) is None]

    @allow_in('property_graph', 'edge_colored_graph')
    def split_node_types(self):
        """
        For some property graphs - a digraph where every edge is tagged with a set of nodes - a nice interpretation exists.
        Namely nodes can have categories, labels, and certain kinds of neighbors.
        This function returns three useful node types for this interpretation if every nodes falls into one of these cases:
        1. only connect to other nodes with exactly 1 tag and is either a source or a sink node
        2. only connect to regular edges and have no incoming connections
        3. be connected to the same number of 1. nodes as the other nodes in 3. (not enforced)
        """
        match_zero = lambda **way: lambda node: next(self.connected(node['id'], **way), None) is None
        id_set = lambda it: set(map(itemgetter('id'), it))

        no_incoming = id_set(self.find_nodes(match_zero(direction='incoming')))
        no_outgoing = id_set(self.find_nodes(match_zero(direction='outgoing')))
        only_to_nodes = id_set(self.find_nodes(match_zero(returns='edges', direction='outgoing')))
        only_to_edges = id_set(self.find_nodes(match_zero(returns='nodes', direction='outgoing')))

        type_1 = (no_incoming | no_outgoing) & only_to_nodes
        type_2 = no_incoming & only_to_edges
        type_3 = id_set(self['data']) - type_1 - type_2

        assert type_1 | type_2 | type_3 == id_set(self['data'])
        assert type_1 & type_2 == type_2 & type_3 == type_3 & type_1 == set()
        return type_1, type_2, type_3

    @allow_in('property_graph', 'edge_colored_graph')
    def get_structure(self, type_1, type_2, type_3):
        name = f"{self.get('name', '')}Item"
        fs = [('id', 'int'), ('data', 'str')]

        for i, data in self.get_info(type_2, 'id', 'data'):
            es = list(self.connected(i))
            ss, ds = map(set, zip(*es))
            s_items = bool(ss & type_3)
            d_items = bool(ds & type_3)
            between_items = s_items and d_items
            item_direction = 'either' if between_items else ('outgoing' if d_items else 'incoming')
            sole = maybe_duplicate(es, direction=item_direction) is None
            field_info = dataclasses.field(init=False, metadata=dict(id=i, between_items=between_items, sole=sole))
            field_type = {(1, 1): name, (1, 0): f"List[{name}]", (0, 1): "str", (0, 0): "List[str]"}[(between_items, sole)]
            fs.append((data, field_type, field_info))
        return dataclasses.make_dataclass(name, fs)

    @allow_in('property_graph', 'edge_colored_graph')
    def as_objects(self, item_ids, constructor):
        id_object = {i: constructor(i, d) for i, d in self.get_info(item_ids, 'id', 'data')}

        for i, o in id_object.items():
            for f in dataclasses.fields(constructor):
                if f.init: continue
                ids = self.connected(o.id, f.metadata['id'], direction='outgoing')
                ins = map(id_object.__getitem__, ids) if f.metadata['between_items'] else self.get_info(ids, 'data')
                prs = next(ins) if f.metadata['sole'] else list(ins)
                setattr(o, f.name, prs)
        return list(id_object.values())

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


def maybe_duplicate(it, direction='incoming'):
    """
    Returns the a duplicate value in the source or sink position, if it exists.
    """
    if direction == 'either':
        it_in, it_out = tee(it)
        return maybe_duplicate(it_in, 'incoming') or maybe_duplicate(it_out, 'outgoing')

    ss_it = map(itemgetter(0 if direction == 'incoming' else 1), it)
    extrema = set()
    for e in ss_it:
        if e in extrema:
            return e
        extrema.add(e)
    return None


def maybe_single(it, direction='incoming'):
    """
    Returns the value of the sole source or sink, if it exists.
    """
    if direction == 'either':
        it_in, it_out = tee(it)
        return maybe_single(it_in, 'incoming') or maybe_single(it_out, 'outgoing')

    ss_it = map(itemgetter(0 if direction == 'incoming' else 1), it)
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
