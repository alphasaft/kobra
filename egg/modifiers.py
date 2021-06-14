import sys
import traceback
import enum
import copy
from functools import update_wrapper, wraps, partial, cache
from abc import *  # noqa : re-exporting

import egg._typealiases as _types
from egg.decorating import decorator, annotation, configurable_decorator, has_decorator
from egg.reflection import AssignableFactory
from egg._utils import *


__all__ = [
    "ABC",
    "abstractmethod",
    "add_effect",
    "anonymous_class",
    "call_once",
    "default",
    "deprecated",
    "DeprecationLevel",
    "final",
    "freezable",
    "freeze",
    "heat",
    "is_deprecated",
    "layer",
    "overrides",
    "partially_final",
    "readonly",
    "singleton",
    "unwrap",
    "wrapper",
    "writeonly"
]


_Type = _types.TypeVar("_Type", bound=type)
_TypeOrFunction = _types.TypeVar("_TypeOrFunction", bound=_types.Union[type(lambda: None), type])


# -----  {  WRAPPING  }  -----


def anonymous_class(*bases: type):
    """Returns an anonymous class, named '<anonymous>' inheriting from all bases."""
    return type.__new__(type, "<anonymous>", bases, {})


class _UnboundMethodProxy(property):
    """Internal helper that adds the possibility to call the property as if it were a normal method"""
    def __init__(self, fget, original_method):
        super().__init__(fget)
        self._original_method = original_method
        update_wrapper(self, fget, updated=())

    def __call__(self, self_, *args, **kwargs):
        return self.__get__(self_, type(self_))(*args, **kwargs)

    def __repr__(self):
        return repr(self._original_method)


# The choice of using partial instead of partialmethod is done because the latter doesn't fit at all,
# albeit I must admit the name _Bound>>Method<<Proxy may be confusing
class _BoundMethodProxy(partial):
    """Internal helper to provide a cleaner __repr__ for methods of layered classes"""
    def __new__(cls, layer_wrapper, method, instance):
        self = partial.__new__(cls, layer_wrapper, method) # noqa : partial does have a custom __new__ method
        return self

    def __init__(self, layer_wrapper, method, instance):  # noqa : partial has no custom __init__ method
        self._method_qualname = instance.__class__.__name__ + "." + method.__name__
        self._instance_repr = repr(instance)

    def __repr__(self):
        return f"<bound method {self._method_qualname} of {self._instance_repr}>"


def _make_wrapper_proxy(name, original_method):
    """Internal helper to build proxies for wrappers"""
    def proxy(self):
        return getattr(self._obj, name)

    return _UnboundMethodProxy(proxy, original_method)


def _make_layer_proxy(name, original_method, apply):
    """Internal helper to build proxies for layers"""
    def layer_wrapper(method, *args, **kwargs):
        for func in apply:
            method = func(method)
        return method(*args, **kwargs)

    def binder(self):
        method = getattr(self._obj, name)
        return _BoundMethodProxy(layer_wrapper, method, self)

    return _UnboundMethodProxy(binder, original_method)


def _make_default_wrapper_repr(prefix: str, wrapper_proto: type, original_type: type[_types.T]) -> _types.Callable[[_types.T], str]:
    """Internal helper that defines the default __repr__ methods of wrappers"""
    def __repr__(self: _types.T):
        dummy_repr = object.__repr__
        if wrapper_proto.__repr__ is not dummy_repr:
            return wrapper_proto.__repr__(self)  # noqa
        elif original_type.__repr__ is not dummy_repr:
            return original_type.__repr__(self._obj)
        else:
            module = original_type.__module__
            wrapped_name = original_type.__name__
            wrapper_name = wrapper_proto.__name__

            return f"<{prefix}@{module}.{wrapped_name} : {wrapper_name} object at {hex(id(self))}>"
    return __repr__


class _WrapperBase:
    """Base class for the @wrapper and @layer decorators"""
    __prototype__: type
    __wraps__: type[_types.T]
    _obj: _types.T

    def __new__(cls, *args, **kwargs):
        if cls.__wraps__.__new__ is not object.__new__:
            return cls.__wraps__.__new__(cls, *args, **kwargs)  # noqa
        return cls.__wraps__.__new__(cls)  # noqa

    def __init__(self, *args, wrap_it=False, **kwargs):
        if args and type(args[0]) in self.__wraps__.mro() and wrap_it:
            # Assuming it was passed just to wrap it, not to create a new object
            obj = args[0]
        else:
            cls = self._cls().__wraps__
            obj = cls.__new__(cls)
            if cls.__init__ is not object.__init__:
                cls.__init__(obj, *args, **kwargs)

        object.__setattr__(self, "_obj", obj)
        type(self).__prototype__.__init__(self)

    def _cls(self):
        return self.__class__

    def __unwrap__(self):
        prototype = self._cls().__prototype__
        if hasattr(prototype, "__unwrap__"):
            return prototype.__unwrap__(self)
        return self._obj

    @classmethod
    def __wrap__(cls, obj):
        return cls(obj, wrap_it=True)

    def __getattr__(self, name):
        return getattr(self._obj, name)

    def __setattr__(self, key, value):
        setattr(self._obj, key, value)


__ignore__ = (
    {f"__{it}__" for it in "class mro new init setattr getattr getattribute unwrap wrap repr".split(" ")}
    | set(vars(_WrapperBase).keys())
)


def wrapper(*, of: type) -> _types.Decorator:
    def decorator_(wrapper_prototype):
        class Wrapper(_WrapperBase, wrapper_prototype, of):
            __wraps__ = of
            __prototype__ = wrapper_prototype
            __repr__ = _make_default_wrapper_repr("Wrapper", wrapper_prototype, of)

        ignore = set(dir(wrapper_prototype)) | __ignore__
        for name in dir(Wrapper.__wraps__):
            if name not in ignore:
                method = getattr(Wrapper.__wraps__, name)
                if callable(method):
                    setattr(Wrapper, name, _make_wrapper_proxy(name, original_method=method))
                else:
                    setattr(Wrapper, name, getattr(Wrapper.__wraps__, name))

        Wrapper.__name__ = f"Wrapper@{of.__name__}"
        return Wrapper
    return decorator_


def layer(*, on: type, apply: _types.Union[_types.Function, tuple[_types.Function, ...]] = ()) -> _types.Decorator:
    apply = (apply,) if not isinstance(apply, tuple) else apply

    def decorator_(layer_prototype):
        class Layer(_WrapperBase, layer_prototype, on):
            __wraps__ = on
            __prototype__ = layer_prototype
            __repr__ = _make_default_wrapper_repr("Layer", __prototype__, __wraps__)

        ignore = set(dir(layer_prototype)) | __ignore__
        for name in dir(Layer.__wraps__):
            if name not in ignore:
                method = getattr(Layer.__wraps__, name)
                if callable(method):
                    setattr(Layer, name, _make_layer_proxy(name, original_method=method, apply=apply))
                else:
                    setattr(Layer, name, getattr(Layer.__wraps__, name))
        Layer.__name__ = f"Wrapper@{on.__name__}"

        return Layer

    return decorator_


def unwrap(obj):
    """Returns the object totally unwrapped, by calling recursively obj.__unwrap__() while it is possible"""
    while hasattr(obj, "__unwrap__"):
        obj = obj.__unwrap__()
    return obj


# -----  {  INHERITANCE  }  -----



@decorator
def singleton(cls_: _Type) -> _Type:
    """
    Mark this class as a singleton, that is a non-instantiable class that behaves as its own and unique
    instance. Singletons can't be inherited from, and can't own a custom __init__ method. Usage : ::

        @singleton
        class A:
            def a(self):
                print("I'm a singleton !")

        A.a()  # I'm a singleton !
        A()    # Cannot init singleton A
    """

    if cls_.__init__ is not object.__init__:
        raise TypeError("Singletons can't own a custom __init__ method")

    class SingletonMeta(cls_, type):
        def __instancecheck__(self, instance):
            return instance is Singleton

        def __subclasscheck__(self, subclass):
            return subclass is Singleton

    class Singleton(metaclass=SingletonMeta):
        def __new__(cls, *args, **kwargs):
            raise ValueError(f"Can't init singleton {cls.__name__}")

        def __init_subclass__(cls, **kwargs):
            raise ValueError(f"Can't subclass singleton {cls_.__name__}")

    return Singleton


@decorator
def final(cls_or_method: _TypeOrFunction) -> _TypeOrFunction:
    """
    Avoids :
     * this class to be inherited in any way
     * this method to be overridden (the owner class must also be decorated with @partially_final in order
       to properly detect whenever it is the case).

    Usage : ::

        @final
        class A: ...
        class B(A): ... # TypeError: Can't subclass final class A

        @partially_final
        class A:
            @final
            def my_final_method(): ...

        class B(A):
            pass  # No errors

        class C(A):
            def my_final_method(): ...  # TypeError : Final method my_final_method cannot be overridden
    """

    if isinstance(cls_or_method, type):
        class Final(cls_or_method):
            def __init_subclass__(cls, **kwargs):
                raise TypeError(f"Can't subclass final class {cls_or_method.__name__}")

        return Final
    else:
        return cls_or_method  # @decorator already adds the function 'final' itself to the __decorators__ field


@decorator
def partially_final(base: _Type) -> _Type:
    """
    Annotating a class with @partially_final does grant it support of the @final decorator.
    Unlike @final, this decorator has for only purpose to check the overriding of @final methods,
    and does nothing on its own. See also : final.
    """

    class InheritanceSupport(base):
        __final_methods__ = {name: method for name, method in base.__dict__.items() if has_decorator(method, final)}

        def __init_subclass__(cls, **kwargs):
            final_methods = cls.__final_methods__
            for name, method in cls.__dict__.items():
                if name in final_methods and final_methods[name] is not method:
                    raise TypeError(f"Can't override final method {name}")

    update_wrapper(InheritanceSupport, base, updated=())
    return InheritanceSupport


def overrides(*base_classes, check=True):
    """
    Check that the method really overrides at least one method of the supplied base classes.
    For now the signature isn't checked, and every method with the same name will match.
    If a matching method is found, but the 'final' decorator was applied to it, a TypeError will be raised.
    Setting check to False will bypass all checks, and the decorator will only be used for informative purposes.
    """

    def decorator_(method):
        if not check:
            return method

        suitable = []
        for name, field, cls in flatten(((name, var, c) for name, var in vars(c).items()) for c in base_classes):
            if callable(field) and name == method.__name__:
                suitable.append((field, cls))

        if (final_method_and_cls := find(lambda m: has_decorator(m[0], final), suitable)) is not None:
            raise TypeError(f"Can't override final method {final_method_and_cls[0].__name__} of class {final_method_and_cls[1].__name__}")
        elif suitable:
            return method
        else:
            raise NameError(f"Can't find method {method.__name__} in superclass(es) {', '.join(c.__name__ for c in base_classes)}")

    return decorator_


@decorator
def chainable(method):
    """
    Transform this object into a chainable method, that is a method that always returns self.
    Usage : ::

        class Monster:
            def __init__(self):
                self.hp = 10
                self.attack = 2

            @chainable
            def set_hp(self, n):
                self.hp = n

            @chainable
            def set_attack(self, n):
                self.attack = 2

        # Monster is now easily configurable
        my_monster = Monster().set_hp(20).set_attack(3)
    """

    def chainable_wrapper(self, *args, **kwargs):
        method(self, *args, **kwargs)
        return self

    return chainable_wrapper


@decorator
def default(method):
    """
    Marks this method as a default method, which means that on the contrary of normal methods, it will
    called if and only if the class provides no other implementation, except those of 'object'.
    That is, it won't even override the methods of the base classes. Usage : ::

        class Foo:
            def foo(self):
                return "foo"

        class Bar(Foo):
            @default
            def foo(self):
                return "bar"

        assert Bar().foo() == "foo"

        # ---

        class Foo:
            pass

        class Bar(Foo):
            @default
            def foo(self):
                return "bar"

        assert Bar().foo() == "bar"

    While it isn't useful by normal, static-defined classes, combined to dynamic subclasses
    it can help a lot ; besides, it can be used for informative purposes, to tell the user it's
    perfectly fine to override it.
    """

    @cache
    def find_superclass_implementation_for(method_name, cls):
        for name, super_method in super_classes_vars(cls).items():
            if not callable(super_method):
                continue

            if super_method is getattr(object, name, None):
                continue

            if super_method.__name__ == method_name and super_method is not default_wrapper:
                return super_method

        return None

    def default_wrapper(self, *args, **kwargs):
        return (find_superclass_implementation_for(method.__name__, type(self)) or method)(self, *args, **kwargs)

    update_wrapper(default_wrapper, method)
    return default_wrapper


# -----  {  DEPRECATION  }  -----


class DeprecationLevel(enum.Enum):
    Info = 0
    Warning = 1
    Error = 2


def _build_deprecation_message(reason, supported_until, object_type, object_name):
    stack = traceback.extract_stack()
    header = traceback.format_list([stack[-3]])[0].removesuffix('\n')  # -1 is here, -2 is the build_deprecated_wrapper
    reason = f" ({reason})" if reason is not None else ""
    support_message = f"will be removed in release {supported_until}" if supported_until is not None else "will likely be removed in a future release"
    return f"{header} : {object_type} {object_name} is deprecated{reason} and {support_message}"


@configurable_decorator
def deprecated(obj, /, level=DeprecationLevel.Warning, reason=None, supported_until=None):
    """
    Marks this object as deprecated, and emits a warning every time someone tries to use it

    :param obj: The deprecated object
    :param level: Configure the severity of the deprecation warning
    :param reason: An explicative string to indicate why this object is now deprecated
    :param supported_until: A string, that should take the form major.minor.revision
    """
    if not isinstance(level, DeprecationLevel):
        raise TypeError("level must be a DeprecationLevel enum entry")

    def build_deprecated_wrapper(callback, object_name, object_type):
        def wrapper_(*args, **kwargs):
            message = _build_deprecation_message(reason, supported_until, object_type, object_name)
            if level is DeprecationLevel.Info:
                print("Info :", message)
            elif level is DeprecationLevel.Warning:
                print("Warning :", message, file=sys.stderr)
            elif level is DeprecationLevel.Error:
                raise Exception("\n" + message)

            return callback(*args, **kwargs)
        return wrapper_

    if isinstance(obj, type):
        obj.__init__ = build_deprecated_wrapper(obj.__init__, obj.__name__, "class")
    elif callable(obj):
        obj = build_deprecated_wrapper(obj, obj.__name__, "function")
    else:
        raise TypeError(f"Can't mark object {obj} as deprecated")
    return obj


def is_deprecated(obj):
    """Returns True if this object is deprecated, no matter how severe, False otherwise"""
    return has_decorator(obj, deprecated)


# -----  {  PROXIES  }  -----


# noinspection PyPep8Naming
class readonly(AssignableFactory):
    """
    Sets this property as a read-only property, and raises a TypeError if someone tries to overwrite its
    value. Usage : ::

        class Foo:
            def __init__(self, bar):
                self._bar = bar

            # Naming it 'bar' makes the property refers to self._bar, you can specify
            # its name as an argument for readonly(<name>)
            bar = readonly()

        foo = Foo("hello")
        assert foo.bar == "hello"
        foo.bar = 3  # TypeError : Can't set read-only property bar of class Foo
    """

    @staticmethod
    def _setter_dummy(name):
        def _(self, value):
            raise TypeError(f"Can't set read-only property {name} of {self}")
        return _

    @classmethod
    def __build__(cls, name):
        return property(getter(name=name, internal_calls=3), cls._setter_dummy(name))


# noinspection PyPep8Naming
class writeonly(AssignableFactory):
    """
    Sets this property as a write-only property, and raises a TypeError if someone tries to read its value.
    Usage : ::

        class Foo:
            def __init__(self, bar):
                self._bar = bar

            # Naming it 'bar' makes the property refers to self._bar, you can specify
            # its name as an argument for writeonly(<name>)
            bar = writeonly()

        foo = Foo("hello")
        foo.bar = "hi"  # OK
        print(foo.bar)  # TypeError : Can't read write-only property bar of class Foo
    """

    @staticmethod
    def _getter_dummy(name):
        def _(self):
            raise TypeError(f"Can't read write-only property {name} of {self}")
        return _

    @classmethod
    def __build__(cls, name):
        return property(cls._getter_dummy(name), setter(name=name, internal_calls=3))


_getter_marker = annotation()
_setter_marker = annotation()


# noinspection PyPep8Naming
class getter(AssignableFactory):
    """
    Auto-generates a getter with given decorators. Usage : ::

        class Foo:
            def __init__(self, bar, bar2):
                self._bar = bar
                self.bar2 = bar2

            get_bar = getter()  # Refers to self._bar
            bar = property(getter())  # Refers to self._bar as well
            get_bar2 = getter(private=False)  # Refers to non-protected attribute bar2

        f = Foo("hello", "hi")
        assert f.get_bar() == "hello"
        assert f.bar ==
        assert f.get_bar2() == "hi"
    """
    __assignation_regex__ = AssignableFactory._make_regex(unmatched_identifier_prefix="(get_)?")  # noqa

    @classmethod
    def __error_handler__(cls, assignment_statement):
        raise SyntaxError(f"Expected a property name, eventually prefixed by 'get_', got '{assignment_statement}'")

    @classmethod
    def __build__(cls, *decorators, private=True, name):
        @apply(*decorators+(_getter_marker,))
        def getter_impl(self):
            return getattr(self, name if not private else "_"+name)
        getter_impl.__name__ = f"<{name.removeprefix('_')} getter>"
        return getter_impl


# noinspection PyPep8Naming
class setter(AssignableFactory):
    """
    Auto-generates a setter with given decorators. Usage : ::

        class Foo:
            def __init__(self, bar, bar2):
                self._bar = bar
                self.bar2 = bar2

            @property
            def bar(self):
                return self._bar

            set_bar = setter()  # Refers to self._bar
            bar = property(fset=setter())  # Refers to self._bar as well
            set_bar2 = setter(private=False)  # Refers to non-protected attribute bar2

        f = Foo("hello", "hi")
        f.set_bar("gotcha")
        f.set_bar2("interesting right ?")
        assert f.bar == "gotcha"
        assert f.bar2 == "interesting right ?"
    """
    __assignation_regex__ = AssignableFactory._make_regex(unmatched_identifier_prefix="(set_)?")

    @classmethod
    def __error_handler__(cls, assignment_statement):
        raise SyntaxError(f"Expected a property name, eventually prefixed by 'set_', got '{assignment_statement}'")

    @classmethod
    def __build__(cls, *decorators, private=True, name):
        @apply(*decorators+(_setter_marker,))
        def setter_impl(self, value):
            return setattr(self, name if not private else "_"+name, value)
        setter_impl.__name__ = f"<{name.removeprefix('_')} setter>"
        return setter_impl


# -----  {  FREEZING  }  -----

class UnfreezableObjectError(Exception):
    """Error raised whenever someone tries to freeze an unfreezable object"""
    def __init__(self, message_or_obj):
        if isinstance(message_or_obj, str):
            super().__init__(message_or_obj)
        else:
            super().__init__(f"Can't freeze unfreezable object {message_or_obj}")
        

class FrozenMemberError(Exception):
    """Error raised whenever someone tries to call a frozen method or write to a frozen field"""
    def __init__(self, name: str):
        super().__init__(f"Can't invoke frozen method {name!r}")
            

freezable = annotation()
heat = annotation()


_frozen_builtins_mapping = {
    str: str,
    int: int,
    float: float,
    bool: bool,
    list: tuple,
    set: frozenset
}


class _FrozenProperty(property):
    """
    A subclass of property that prohibits being invoked to delete and/or set the property of frozen object
    """
    @staticmethod
    def _possibly_frozen_setter(setter_impl, property_name):
        @wraps(setter_impl)
        def _setter(self_, value):
            if getattr(self_, "__frozen__", False):
                raise FrozenMemberError(name=f"<{property_name} setter>")
            return setter_impl(self_, value)
        return _setter
    
    @staticmethod
    def _possibly_frozen_deleter(deleter_impl, property_name):
        @wraps(deleter_impl)
        def _deleter(self_):
            if getattr(self_, "__frozen__", False):
                raise FrozenMemberError(name=f"<{property_name} deleter>")
            return deleter_impl(self_)
        return _deleter
        
    def __init__(self, property_name: str, property_: property):
        super().__init__(
            property_.getter,
            self._possibly_frozen_setter(property_.setter, property_name),
            self._possibly_frozen_deleter(property_.deleter, property_name)
        )


def _get_frozen_wrapper_for(m, *, name=None):
    @wraps(m)
    def _frozen_method(*args, **kwargs):
        raise FrozenMemberError(name=name or m.__name__)
    return _frozen_method


def freeze(obj: _types.T, *, in_place=False) -> _types.T:
    """
    Freeze objects, making them immutable.

    The class of the object to freeze is required to have been decorated with @freezable, to ensure that
    everybody is aware that this object might be frozen.
    The methods of the object now raise a TypeError whenever called, except for those that were decorated
    with @heat. For implementation issues, the instance attributes of the frozen object won't be frozen,
    but the property proxies declared through the @property builtin are ; For that reason, it is highly
    recommended to prefix instance properties with an underscore, and to provide external access to them
    thanks to all the @property machinery, or with kobra's getters and setters (you might be interested
    into taking a look at their documentation as well)

    Freezing is done recursively by iterating over the attributes of the object. For consistency with the freezing
    process of builtins, the object is deep-copied, frozen, and returned, but if you want to spare a significant
    amount of execution time, you can specify in_place=True, what will freeze the given object and returning it
    instead ; however a TypeError will eventually be raised if a builtin is passed with this argument set to True.
    Note that getters generated with the kobra.egg.getter() class and some methods - __repr__, __str__, __eq__,
    __lq__, __le__, __ge__ and __gt__ - aren't frozen, as they shouldn't modify the object.

    :param obj: The object to freeze
    :param in_place: If True, the object itself is frozen, else a deepcopy is created, frozen, and returned.
    :returns: The frozen object, no matter the value of in_place flag.
    """

    if type(obj) in _frozen_builtins_mapping:
        if in_place:
            raise UnfreezableObjectError(f"Can't freeze in place builtin {obj.__class__.__name__}")
        return _frozen_builtins_mapping[type(obj)](obj)

    if not has_decorator(obj.__class__, freezable):
        raise UnfreezableObjectError(obj)

    if not in_place:
        obj = copy.deepcopy(obj)

    for field_name in set(dir(obj)) - {f"__{p}__" for p in ("str", "repr", "eq", "lt", "le", "gt", "ge")}:
        cls_field = getattr(obj.__class__, field_name, None)
        if isinstance(cls_field, property):
            setattr_safe(obj.__class__, field_name, _FrozenProperty(field_name, cls_field))
            continue

        field = getattr(obj, field_name)
        if callable(field) and not (has_decorator(field, heat) or has_decorator(field, _getter_marker)):
            setattr_safe(obj, field_name, _get_frozen_wrapper_for(field))
        else:
            try:
                setattr_safe(obj, field_name, freeze(field, in_place=in_place))
            except UnfreezableObjectError:
                pass

    obj.__frozen__ = True
    return obj


@configurable_decorator
def add_effect(method, /, *, to: type):
    """
    Adds an additional side-effect to the method's implementation of the super class, that means that
    whenever called, instead of behaving normally, the method will :
        * call the super class implementation of itself and store the result
        * call itself and throw away the result
        * return the stored result
    """

    if (super_method := getattr(to, method.__name__, None)) is None:
        raise NameError(f"Can't add effect to non-existing method {method.__name__} for class {to.__name__}")

    def _wrapper(self, *args, **kwargs):
        ret = super_method(to, *args, **kwargs)
        method(self, *args, **kwargs)
        return ret
    return _wrapper


@decorator
def call_once(func):
    def _wrapper(*args, **kwargs):
        if getattr(_wrapper, "__called__", False):
            raise NameError(f"Can't call function {func.__name__} twice.")
        _wrapper.__called__ = True
        return func(*args, **kwargs)
    return _wrapper



