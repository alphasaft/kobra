"""Module to define dynamically the docstrings of your objects"""

from egg.decorating import configurable_decorator


@configurable_decorator
def doc(obj, /, docstring):
    """Sets the object's __doc__ to docstring"""
    obj.__doc__ = docstring
    return obj


def as_docstring(docstring):
    """Removes the indentations of the docstring without totally flattening it"""

    split = docstring.split("\n")
    minimum_indentation = min(len(it) - len(it.lstrip()) for it in split)
    return "\n".join(it[minimum_indentation:] for it in split)
