"""
Module extending in a certain way the standard module 'inspect', by providing the program some reflexion
capabilities, as well as awareness of its own source code.
"""

from inspect import *
from functools import lru_cache as _lru_cache
from abc import ABC as _ABC
import re as _re
import traceback as _tb
from typing import Callable

_cache = _lru_cache(maxsize=None)
_identifier = "[\\w_][\\w\\d_]*"
_ws = "\\s*"


def _fetch_globals(internal_calls=2):
    call_site = stack()[internal_calls]
    return call_site.frame.f_globals


@_cache
def get_declaring_class(method):
    """
    Returns the declaring class of the given method.
    get_declaring_class(m) is the same as m.im_class in python 2.
    """
    if hasattr(method, "__self__"):
        return type(method.__self__)

    if not hasattr(method, "__call__"):
        raise TypeError(f"Expected an unbound method, got : {method}")

    call_site_globals = _fetch_globals()
    for var in call_site_globals.values():
        if isinstance(var, type):
            for m in (obj for obj in vars(var).values() if hasattr(obj, "__call__")):
                if m is method:
                    return var

    return None


@_cache
def is_method(m):
    """Returns True if m is a method - bound or unbound -, False otherwise"""
    return get_declaring_class(m) is not None


def pointers_to(obj):
    """
    Returns all the non-nested variables (i.e not declared as an attribute), that hold a reference to obj.
    If the object is a str, int, float... or any builtin type for which '==' and 'is' always
    return the same result, then it will return all the variables that are equal to that
    object instead.
    """

    result = []
    call_site_globals = _fetch_globals()
    for name, var in call_site_globals.items():
        if var is obj:
            result.append(name)

    return result


def _parse_declaration_statement(
        pattern_name: str,
        error_handler: Callable,
        assignation_regex: _re.Pattern,
        groups: tuple[str],
        top_level: bool,
        internal_calls: int = 1
):
    frame = _tb.extract_stack()[-(internal_calls+1)]
    declaration_statement = frame.line

    if top_level and frame.name != "<module>":
        raise TypeError(f"{pattern_name} declaration statements must be done at module level")

    if match := assignation_regex.match(declaration_statement):
        groups_values = {}
        for group in groups:
            groups_values[group] = match.group(group)
    else:
        return error_handler(declaration_statement)

    return groups_values


class Assignable(_ABC):
    def _make_regex(
            *,
            unmatched_identifier_prefix="",
            matched_identifier=_identifier,
            expression_constraint=".*",
            type_annotation_allowed=True
    ):
        return _re.compile(
            f"^{unmatched_identifier_prefix}(?P<name>{matched_identifier}){_ws}" +
            (f"(:{_ws}{_identifier}{_ws})?" if type_annotation_allowed else "") +
            f"={expression_constraint}$"
        )

    __assignation_regex__ = _make_regex()
    __groups__ = ("name",)
    __top_level__ = False
    _make_regex = staticmethod(_make_regex)

    def __init__(self, *args, internal_calls=1, **kwargs):
        self._assign(*args, internal_calls=internal_calls+1, **kwargs)

    def _assign(self, *additional_args, internal_calls=0, **additional_kwargs):
        self.__assign__(
            *additional_args,
            **(additional_kwargs | _parse_declaration_statement(
                pattern_name=self.__class__.__name__,
                error_handler=self.__error_handler__,
                assignation_regex=self.__assignation_regex__,
                groups=self.__groups__,
                top_level=self.__top_level__,
                internal_calls=internal_calls+1
            )))

    def __error_handler__(self, assignment_statement):
        raise SyntaxError(
            f"{self.__class__.__name__} declaration statements must be of the form {self.__assignation_regex__},"
            f" got {assignment_statement}"
        )

    def __assign__(self, *args, **kwargs):
        ...


class _AssignableFactoryMeta(type):
    __build__: Callable
    __error_handler__: Callable
    __assignation_regex__: _re.Pattern
    __groups__: tuple[str]
    __top_level__: bool

    def __call__(cls, *args, do_not_assign=False, internal_calls=1, **kwargs):
        if do_not_assign:
            return cls.__build__(*args, **kwargs)

        return cls.__build__(
            *args,
            **(kwargs | _parse_declaration_statement(
                pattern_name=cls.__name__,
                error_handler=cls.__error_handler__,
                assignation_regex=cls.__assignation_regex__,
                groups=cls.__groups__,
                top_level=cls.__top_level__,
                internal_calls=internal_calls + 1
            ))
        )


class AssignableFactory(metaclass=_AssignableFactoryMeta):
    def _make_regex(
            *,
            unmatched_identifier_prefix="",
            matched_identifier=_identifier,
            expression_constraint=".*",
            type_annotation_allowed=True
    ):
        return _re.compile(
            f"^{unmatched_identifier_prefix}(?P<name>{matched_identifier}){_ws}" +
            (f"(:{_ws}{_identifier}{_ws})?" if type_annotation_allowed else "") +
            f"={expression_constraint}$"
        )

    __assignation_regex__ = _make_regex()
    __groups__ = ("name",)
    __top_level__ = False
    _make_regex = staticmethod(_make_regex)

    @classmethod
    def __error_handler__(cls, assignment_statement):
        raise SyntaxError(
            f"{cls.__name__} declaration statements must be of the form {cls.__assignation_regex__},"
            f" got {assignment_statement}"
        )

    def __build__(self, *args, **kwargs): ...
