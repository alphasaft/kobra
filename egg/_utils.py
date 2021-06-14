from typing import Generic, TypeVar
from contextlib import *


_T = TypeVar("_T", covariant=True)


class _ResultContainer(Generic[_T]):
    def __init__(self):
        self._filled = False
        self._result = None

    def fill(self, result: _T):
        self._filled = True
        self._result = result

    def get(self) -> _T:
        if not self._filled:
            raise ValueError("Results are only meant to be collected after the context manager")
        return self._result


class _Collector(Generic[_T]):
    def __init__(self, block):
        self._block = block
        self._generator = None
        self._container = None

    def __call__(self, *args, **kwargs):
        self._generator = self._block(*args, **kwargs)
        return self

    def __enter__(self):
        next(self._generator)
        self._container = _ResultContainer[_T]()
        return self._container

    def __exit__(self, *exit_info):
        try:
            next(self._generator)
            raise ValueError("Collectors must own an unique yield clause")
        except StopIteration as e:
            self._container.fill(e.value)
            self._generator = None


def collector(block):
    return _Collector[_T](block)


def flatten(iterable):
    result = []
    for item in iterable:
        result += item
    return result


def flatten_dicts(dict_iterable):
    result = {}
    for dct in dict_iterable:
        result |= dct
    return result


def dict_to_list(dct):
    result = []
    for k, v in dct.items():
        result.append((k, v))
    return result


def find(predicate, iterable):
    for item in iterable:
        if predicate(item):
            return item
    return None


def full_vars(cls):
    result = {}
    for superclass in reversed(cls.mro()):
        result |= vars(superclass)
    return result


def super_classes_vars(cls):
    result = {}
    for super_class in reversed(cls.mro()):
        if super_class is cls:
            continue

        result |= vars(super_class)
    return result


def setattr_safe(obj, attr, value):
    try:
        setattr(obj, attr, value)
    except (AttributeError, TypeError):
        pass


def apply(*decorators):
    def _(function):
        for decorator in decorators:
            function = decorator(function)
        return function
    return _


def standard_setattr(obj, key, value):
    if isinstance(obj, type):
        type.__setattr__(obj, key, value)
    else:
        object.__setattr__(obj, key, value)


__default_placeholder = object()


def standard_getattr(obj, name, default=__default_placeholder):
    try:
        if isinstance(obj, type):
            return type.__getattribute__(obj, name)
        return object.__getattribute__(obj, name)
    except AttributeError:
        if default is __default_placeholder:
            raise
        return default
