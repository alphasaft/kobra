import functools
import typing as _typing
import functools as _functools

from egg.reflection import Assignable


_ws = "\\s*"
_identifier = "[\\w_][\\w\\d_]*"


def has_decorator(obj, decorator_):
    return hasattr(obj, "__decorators__") and any(decorator_ is d for d in obj.__decorators__)


def decorators_of(obj: _typing.Any) -> _typing.Optional[list]:
    decorators = obj.__decorators__ if hasattr(obj, "__decorators__") else []

    try:
        obj.__decorators__ = decorators
    except (TypeError, AttributeError) as e:
        return None

    return decorators


# noinspection PyPep8Naming
class _Decorator:
    _custom_wrapper_assignments = tuple(_functools.WRAPPER_ASSIGNMENTS) + ("__decorators__",)
    __wrapped__: _typing.Callable[..., _typing.Any]
    only_once: bool

    def __init__(self, function, *, only_once=False, traceable=True, _self=None):
        _functools.update_wrapper(self, function, assigned=self._custom_wrapper_assignments, updated=())
        self.only_once = only_once
        self.traceable = traceable
        self.__self__ = _self

    def __call__(self, obj):
        return self._call_internal(obj)

    def _call_internal(self, obj, *args, **kwargs):
        if self.only_once and self in (decorators_of(obj) or ()):
            raise ValueError(f"Decorator {self.__wrapped__.__name__} can only be applied once per object")

        if self.__self__ is not None:
            ret = self.__wrapped__(self.__self__, obj, *args, **kwargs)
        else:
            ret = self.__wrapped__(obj, *args, **kwargs)
        decorators = decorators_of(ret)

        if decorators is None:
            raise TypeError(
                "The __decorators__ field can't be added to the given object. Make sure "
                "that it isn't a built-in method or object, that your decorator properly returns, and "
                "that the __slots__ attribute of the decorated object includes '__decorators__'"
            )

        if base_decorators := decorators_of(obj):
            decorators.extend(base_decorators)
        decorators.append(self)
        _functools.update_wrapper(ret, obj, updated=())
        return ret

    def __repr__(self):
        return repr(self.__wrapped__)

    def __get__(self, instance, owner):
        return type(self)(
            self.__wrapped__,
            only_once=self.only_once,
            traceable=self.traceable,
            _self=instance
        )


def decorator(function=None, *, only_once=True, traceable=True):
    """
        Mark a function as a decorator, i.e something that is destined to be used with the '@my_decorator'
        syntax. Whenever called on obj, self will be added as a element of obj.__decorators__. Note that
        if the field doesn't yet exist on the object, it will be created and, if that isn't possible (e.g
        if the decorator was applied to a class that declares a __slots__ attribute), a TypeError
        will be raised.

        Additional options :

        only_once: Set this to False to allow multiple applications of the resulting decorator to the
        same object

        traceable: Set this to False not to add self to the __decorators__ field, thereby avoiding
        raising errors if it cannot be created
    """
    if function is not None:
        if not callable(function):
            raise TypeError("Expected a callable as the first argument")
        return _Decorator(function, only_once=False, traceable=True)

    def decorator_wrapper(func):
        return _Decorator(func, only_once=only_once, traceable=traceable)

    return decorator_wrapper


# noinspection PyPep8Naming
class _ConfigurableDecorator(_Decorator):
    _args: tuple
    _kwargs: dict[str, _typing.Any]

    def __init__(self, function, *, only_once=False, traceable=True, _args=None, _kwargs=None, _self=None):
        super().__init__(function, only_once=only_once, traceable=traceable, _self=_self)
        self._args = _args or ()
        self._kwargs = _kwargs or {}

    def __call__(self, obj=None, /, *args, **kwargs):
        if args or kwargs or not (isinstance(obj, _typing.Callable) or isinstance(obj, type)):
            if self._args or self._kwargs:
                raise ValueError("Configurable decorators must only be called only once with arguments")

            # Let's assume it was passed in as an argument
            if obj is not None:
                args += (obj,)

            return _ConfigurableDecorator(
                function=self.__wrapped__,
                only_once=self.only_once,
                _args=args,
                _kwargs=kwargs,
                _self=self.__self__,
            )
        else:
            return self._call_internal(obj, *self._args, **self._kwargs)


def configurable_decorator(function, *, only_once=False, traceable=True):
    """
    Simplify the creation of configurable decorators, i.e decorators called with arguments. Usage : ::

        @configurable_decorator
        def speak(function, /, sentence="Hello", *, end_of_the_sentence="world !"):
            print(obj.__name__ + " says : " + sentence + " " + end_of_the_sentence)

        @speak
        # @speak() instead of @speak works all the way too
        def dummy():
            pass
        # Output : dummy says : Hello world !

        @speak("Hi", end_of_the_sentence="my friends !")
        def dummy2():
            pass
        # Output : dummy2 says : Hi my friends !

    configurable_decorator is a subclass of decorator, and thus provides all features that it does.
    """
    if function is not None:
        if not callable(function):
            raise TypeError("Expected a callable as the first argument")
        return _ConfigurableDecorator(function, only_once=False, traceable=True)

    def decorator_wrapper(func):
        return _ConfigurableDecorator(func, only_once=only_once, traceable=traceable)
    return decorator_wrapper


# noinspection PyPep8Naming
class annotation(Assignable):
    """
        Describes a decorator that has no side effect.
        Usage : ::

            my_annotation = annotation()
            assert my_annotation.__name__ == "my_annotation"

            @my_annotation
            def foo(*args, **kwargs):
                ...

            assert foo.__decorators__ == [my_annotation]
    """
    def __assign__(self, name):
        self.__name__ = name

    def __repr__(self):
        return f"<annotation {self.__name__} at {hex(id(self))}>"

    def __call__(self, annotated):
        return annotated

