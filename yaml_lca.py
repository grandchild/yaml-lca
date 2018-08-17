# CC0 - free software.
# To the extent possible under law, all copyright and related or neighboring
# rights to this work are waived. See the LICENSE file for more information.

"""
This module provides functions to find the range of a common ancestor in a
YAML-formatted document.

Consider the following YAML document:

>>> doc = '''---
... a key: content
... a mapping:
...   key: value
... a list:
...   - one red:   "#f00"
...     one blue:  "#08f"
...   - two red:   "#f31"
...     two green: "#3d6"
... '''

And imagine a selection inside the sequence "a list" from the start of the
first list entry before "one" on line 6 to inside "blue" on line 7:

>>> a = doc.find("one")
>>> b = doc.find("lue:")
>>> print(a, b)
55 82

Selecting the lowest common ancestor will return the range of the first entry
of the "a list" sequence:

>>> yaml_lca_range(doc, a, b)
(55, 97)


Selecting between "value" and "one" will select the whole document:

>>> a = doc.find("value")
>>> b = doc.find("one") + 2
>>> print(a, b)
37 57
>>> yaml_lca_range(doc, a, b)
(4, 139)

You can also use find the node containing a single position with
yaml_lca_range():

>>> yaml_lca_range(doc, b)
(55, 62)

yaml_lca_range() with a single position searches forward in the document, if
the position is in whitespace (or inside comments). It uses
yaml_find_node_forward(). If you think your chances are better looking
backward, then it's also possible to use yaml_find_node_backward() and inspect
the node:

>>> in_indent_before_one = doc.find("one") - 4
>>> node = yaml_find_node_backward(yaml.compose(doc), in_indent_before_one)
>>> print(node.start_mark.index, node.end_mark.index)
43 49

yaml_find_node_forward() works the same, except that you need to provide the
length of the document as a search limit:

>>> node = yaml_find_node_forward(yaml.compose(doc), in_indent_before_one, len(doc))
>>> print(node.start_mark.index, node.end_mark.index)
55 62

It can be useful to not select key nodes on its own, because they aren't very
meaningful entities beyond their literal scalar value. Therefore you can set
extend_keys=True in yaml_lca_range() (and yaml_lca()) to expand to the mapping
they belong to.

>>> a = doc.find("one")
>>> yaml_lca_range(doc, a)
(55, 62)
>>> yaml_lca_range(doc, a, extend_keys=True)
(55, 97)
>>> b = doc.find("f00")
>>> yaml_lca_range(doc, b, extend_keys=True)
(66, 72)

Refer to the PyYAML documentation for the API around PyYAML Node objects:
 - http://pyyaml.org/wiki/PyYAMLDocumentation#Nodes
 - http://pyyaml.org/wiki/PyYAMLDocumentation#Mark


Debugging:

>>> a = doc.find("value")
>>> b = doc.find("one") + 2
>>> node = yaml_lca(yaml.compose(doc), a, b, len(doc), debug=True)
[(37, 'value (str)'), (32, 'key (map)'), (4, 'a key (map)'), (4, 'a key (map)')]
[(55, 'one red (str)'), (55, 'one red (map)'), (53, ' (seq)'), (4, 'a key (map)'), (4, 'a key (map)')]

"""
import yaml


def yaml_lca_range(document, begin, end=None, extend_keys=False):
    """
    Return the range (as (begin,end)-tuple) of the lowest common ancestor yaml
    node between two selection points.
    """
    tree = yaml.compose(document)
    if begin == end or end is None:
        lca_node = yaml_find_node_forward(tree, begin, len(document), extend_keys=extend_keys)
    else:
        lca_node = yaml_lca(tree, begin, end, len(document), extend_keys=extend_keys)
    return lca_node.start_mark.index, lca_node.end_mark.index

def yaml_lca(tree, begin, end, input_length, extend_keys=False, debug=False):
    """
    Return the lowest common ancestor for a given yaml parse tree and two
    selection points.
    """
    if begin > end:
        tmp = begin
        begin = end
        end = tmp
    begin_path = _yaml_find_node_path_forward(tree, begin, input_length)
    end_path = _yaml_find_node_path_backward(tree, end)
    if debug:
        print([(node.start_mark.index, _dbg_node(node)) for node in begin_path])
        print([(node.start_mark.index, _dbg_node(node)) for node in end_path])

    search_path = begin_path
    second_path = end_path
    begin_path_len = len(begin_path)
    end_path_len = len(end_path)
    if begin_path_len > end_path_len:
        search_path = end_path
        second_path = begin_path
    if extend_keys:
        search_path = _extend_key(search_path)
    for node1 in second_path:
        for node2 in search_path:
            if (type(node1) == type(node2)
                    and node1.start_mark.index == node2.start_mark.index
                    and node1.end_mark.index == node2.end_mark.index):
                return node1
    return None

def yaml_find_node_forward(node, index, length, extend_keys=False):
    return _yaml_find_node_path_forward(node, index, length, extend_keys=extend_keys)[0]

def yaml_find_node_backward(node, index, extend_keys=False):
    return _yaml_find_node_path_backward(node, index, extend_keys=extend_keys)[0]


def _yaml_find_node_path_forward(node, index, length, extend_keys=False):
    path = _yaml_find_node(node, index, length, search_step=2)
    if path is None:
        raise ValueError("Index {} not in any token.".format(index))
    if extend_keys:
        path = _extend_key(path)
    return path + [node]

def _yaml_find_node_path_backward(node, index, extend_keys=False):
    path = _yaml_find_node(node, index, 0, search_step=-2)
    if path is None:
        raise ValueError("Index {} not in any token.".format(index))
    if extend_keys:
        path = _extend_key(path)
    return path + [node]

def _yaml_find_node(node, index, search_end=0, search_step=0):
    """
    Recursively searches the parsed yaml document given by tree for a node
    that ultimately contains the given index, i.e. the node found does not
    have children. The path of nodes leading to that node is returned, in
    bottom-to-top ordering.
    
    Given a YAML document and its tree:
    >>> doc = '''---
    ...   key: [1, 2]
    ... '''
    >>> tree = yaml.compose(doc)
    
    Searching for the Node at the 15th position (the '2') gives:
    >>> [type(node).__name__ for node in _yaml_find_node(tree, 15)]
    ['ScalarNode', 'ScalarNode', 'SequenceNode', 'MappingNode']
    
    Positions inside whitespace and comments would return no node and thus
    need the search functionality, through the "search_end" and "search_step"
    parameters. A positive search_step value searches forward, a negative
    backward. The search is limited to a maximum position of search_end
    (usually 0 for negative search_step values and the length of the YAML
    string for positive ones).
    
    >>> _yaml_find_node(tree, 5, len(doc), search_step=2)
    [ScalarNode(tag='tag:yaml.org,2002:str', value='key')]
    >>> print(_yaml_find_node(tree, 5, search_step=-2))
    None
    
    Note: A search_step of less than 2 is unnecessary, since no two different
    tokens are less than 2 steps apart.
    """
    if index in range(node.start_mark.index, node.end_mark.index+1):
        if isinstance(node, yaml.MappingNode):
            for key, value in node.value:
                if index in range(key.start_mark.index, key.end_mark.index+1):
                    return [key]
                elif index in range(value.start_mark.index, value.end_mark.index+1):
                    result = _yaml_find_node(value, index, search_end, search_step)
                    if result is not None:
                        return result + [node]
        elif isinstance(node, yaml.SequenceNode):
            for n in node.value:
                if index in range(n.start_mark.index, n.end_mark.index+1):
                    result = _yaml_find_node(n, index, search_end, search_step)
                    if result is not None:
                        return result + [n, node]
        else:
            return [node]
    if search_step > 0:  # forward
        search_end = min(node.end_mark.index, search_end)
        if index < search_end:
            return _yaml_find_node(node, min(search_end, index + search_step), search_end, search_step)
        else:
            # Comments are the last nodes of their container node, and search
            # needs to continue one or more levels up.
            return None
    elif search_step < 0:  # backward
        search_end = max(node.start_mark.index, search_end)
        if index > search_end:
            return _yaml_find_node(node, max(search_end, index + search_step), search_end, search_step)
        else:  # See comment above
            return None

def _extend_key(path):
    # remove the ScalarNode from the beginning of the path so that the
    # MappingNode is the lowest possible candidate
    if isinstance(path[1], yaml.MappingNode) and path[0] is path[1].value[0][0]:
        return path[1:]
    else:
        return path


def _dbg_node(node):
    tag = node.tag.replace("tag:yaml.org,2002:", "")
    return "{} ({})".format(_dbg_node_key(node), tag)

def _dbg_node_key(node):
    if isinstance(node, yaml.MappingNode):
        return node.value[0][0].value
    else:
        return node.value if isinstance(node.value, str) else ""


if __name__ == '__main__':
    import doctest
    doctest.testmod() #(verbose=True)
