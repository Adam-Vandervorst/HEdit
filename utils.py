"""
This file provides utilities for handling structures made with H-EDit.
Currently, only a quite bare-bones and low-performance class is available, HDict.
After saving your structure with pressing 'S' in H-Edit, you can load it here with `HDict.load_from_path`.
In Python console, you can write help(HDict) to view the useful methods, and the README contains links to example projects.
"""
import typing
from collections import UserDict, defaultdict
from operator import itemgetter
from itertools import chain, tee, starmap
from functools import wraps
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
        return [tuple(edge_ids(e)) for e in self['conn']
                if not remove_subsumed or next(self.connected(e, direction='incoming'), None) is None]

    @allow_in('property_graph', 'edge_colored_graph')
    def node_types(self):
        """
        For some property graphs - a digraph where every edge is tagged with a set of nodes - a nice interpretation exists.
        Namely nodes can have categories, labels, and certain kinds of neighbors.
        This function returns three useful node types for this interpretation if every nodes falls into one of these cases:
        1. only connect to other nodes with exactly 1 tag and is either a source or a sink node
        2. only connect to regular edges and have no incoming connections
        3. be connected to the same number of 1. nodes as the other nodes in 3. (not enforced)
        Nodes that are not connected to other items are ignored.
        """
        match_zero = lambda **way: lambda node: next(self.connected(node['id'], **way), None) is None
        id_set = lambda it: set(map(itemgetter('id'), it))

        no_incoming = id_set(self.find_nodes(match_zero(direction='incoming')))
        no_outgoing = id_set(self.find_nodes(match_zero(direction='outgoing')))
        only_to_nodes = id_set(self.find_nodes(match_zero(returns='edges', direction='outgoing')))
        only_to_edges = id_set(self.find_nodes(match_zero(returns='nodes', direction='outgoing')))
        disconnected_nodes = id_set(self.find_nodes(match_zero(returns='both', direction='either')))

        type_1 = ((no_incoming | no_outgoing) & only_to_nodes) - disconnected_nodes
        type_2 = (no_incoming & only_to_edges) - disconnected_nodes
        type_3 = id_set(self['data']) - type_1 - type_2 - disconnected_nodes

        assert type_1 & type_2 == type_2 & type_3 == type_3 & type_1 == set()
        return type_1, type_2, type_3

    @allow_in('property_graph', 'edge_colored_graph')
    def synthesize_structure(self, type_1, type_2, type_3):
        """
        Uses the node types from `node_types` to interpret type 3 nodes as items.
        A dataclass is returned with outgoing type 2 nodes as property names and type 1 or type 3 nodes as values.
        """
        from dataclasses import field, make_dataclass
        name = f"{self.get('name', '')}Item"
        fs = [('id', 'int'), ('data', 'str')]

        for i, data in self.get_info(type_2, 'id', 'data'):
            es = list(self.connected(i))
            s_items, d_items = map(type_3.intersection, zip(*es))
            between_items = s_items and d_items
            item_direction = 'either' if between_items else ('outgoing' if d_items else 'incoming')
            sole = maybe_duplicate(es, direction=item_direction) is None
            base_type = name if between_items else "str"
            field_type = base_type if sole else f"List[{base_type}]"
            fs.append((data, field_type, field(init=False)))
        return make_dataclass(name, fs)

    @allow_in('property_graph', 'edge_colored_graph')
    def as_objects(self, type_1, type_2, type_3, cls):
        """
        Uses the node types from `node_types` and a class to construct objects as implied by the graph.
        """
        prop_id = dict(self.get_info(type_2, 'data', 'id'))
        id_object = dict(zip(type_3, starmap(cls, self.get_info(type_3, 'id', 'data'))))

        for d, T in typing.get_type_hints(cls, vars(typing), {cls.__name__: cls}).items():
            if d not in prop_id: continue
            for i, o in id_object.items():
                ids = self.connected(o.id, prop_id[d], direction='outgoing')
                ins = map(id_object.__getitem__, ids) if collection_of(T, cls) else self.get_info(ids, 'data')
                prs = list(ins) if proper_collection(T) else next(ins)
                setattr(o, d, prs)
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

        dct['conn'] = list(map(convert, dct['conn']))
        return cls(dct)


def proper_collection(C):
    """
    Checks if type `C` is a collection (not including `str`).
    """
    C = typing.get_origin(C) or C
    return issubclass(C, typing.Collection) and not issubclass(C, str)


def collection_of(C, T):
    """
    Checks if type `C` is a collection (not including `str`) containing type `T`.
    """
    if not proper_collection(C): return False
    t, = typing.get_args(C)
    return issubclass(t, T)


def convert(maybe_container, to_type=tuple):
    """
    Convert some container recursively to some other container `to_type`.
    """
    if proper_collection(type(maybe_container)):
        return to_type(convert(t, to_type) for t in maybe_container)
    return maybe_container


def edge_ids(e, flatten='outgoing'):
    """
    Yields the id's of an edge.
    The flatten argument can be used to flatten the incoming or outgoing recursive sides, or both.
    """
    s, d = e
    if flatten in ('incoming', 'both') and isinstance(s, tuple):
        yield from edge_ids(s)
    else:
        yield s
    if flatten in ('outgoing', 'both') and isinstance(d, tuple):
        yield from edge_ids(d)
    else:
        yield d


def maybe_self_loop(it):
    """
    If there's a pair (a, a) in `it`, returns a, else returns None.
    """
    for s, d in it:
        if s == d:
            return s
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
