import json
from inspect import stack
from abc import ABC, abstractmethod
from re import compile

from egg.modifiers import singleton


COMPONENT_FLAG = "__component__"
STRING_REGEX = compile("'\w[\w0-9 ]*'")


def map_dict(value_mapper, dct):
    result = {}
    for key, value in dct.items():
        result[key] = value_mapper(value)
    return result


class Globals:
    def __init__(self, storage):
        self._storage = storage

    def require(self, item):
        value = self._storage.get(item)
        if value is None:
            raise NameError(
                f"A {item} argument seems to be required to decode the json file. Make sure you provided it.")
        return value

    def as_dict(self):
        return self._storage


class JsonIOSupporter(ABC):
    @classmethod
    @abstractmethod
    def __load__(cls, gbls, **kwargs):
        ...

    @abstractmethod
    def __dump__(self):
        ...

    class __Dumper:
        def __init__(self, parent):
            self._fields = {COMPONENT_FLAG: parent.__class__.__name__}
            self._parent_dict = parent.__dict__

        def add(self, *fields, transform=lambda x: x):
            for field in fields:
                field_value = self._parent_dict.get(field)
                if field_value is None:
                    raise NameError("Unknown field %s for class %s" % (field, self._fields[COMPONENT_FLAG]))

                if isinstance(field_value, JsonIOSupporter):
                    if transform(field) is not field:
                        raise ValueError("JsonIOSupporter aren't supposed to be transformed")
                    field_value = field_value.__dump__()
                else:
                    field_value = transform(field_value)

                self.create_field(field.lstrip("_"), field_value)

        def create_field(self, field, value):
            field_type = type(value).__name__

            if field_type == "str":
                self._fields[field] = value
            elif field_type == "list":
                self._fields[field] = [it.__dump__() if isinstance(it, JsonIOSupporter) else it for it in value]
            elif field_type == "dict":
                self._fields[field] = map_dict(lambda it: it.__dump__() if isinstance(it, JsonIOSupporter) else it, value)
            else:
                self._fields[field] = f"<{field_type}>{value}"

        def to_dict(self):
            return self._fields

    def _get_dumper(self):
        return JsonIOSupporter.__Dumper(self)


class AsyncLoader:
    def __init__(self, loader):
        self._loader = loader

    async def load_async(self):
        return await self._loader()


class LateLoader:
    def __init__(self, loader):
        self._loader = loader

    def load(self):
        return self._loader()


@singleton
class JsonIO:
    cast_regex = compile("(<(?P<data_type>[\\w_][\\w\\d_]*)>)?(?P<raw_data>.*)")

    def _cast_data(self, data):
        match = self.cast_regex.match(data)
        data_type = match.group("data_type")
        raw_data = match.group("raw_data")

        if data_type:
            return eval(data_type)(raw_data)

        return raw_data

    def hook(self, dct, global_arguments):
        dct = map_dict(lambda value: self._cast_data(value) if isinstance(value, str) else value, dct)

        if dct.get(COMPONENT_FLAG):
            component_name = dct[COMPONENT_FLAG]
            try:
                component_class = eval(component_name, global_arguments.as_dict())
            except NameError as e:
                raise NameError("Cannot load component %s" % component_name) from e

            dct.pop(COMPONENT_FLAG)

            if not issubclass(component_class, JsonIOSupporter):
                raise TypeError("Component %s isn't a JsonIOSupporter subclass" % component_name)
            try:
                return component_class.__load__(gbls=global_arguments, **dct)
            except TypeError as e:
                if "got an unexpected keyword argument" in str(e):
                    e = TypeError(f"Cannot load component {component_name} with argument {STRING_REGEX.search(str(e)).group()}")
                raise e from None

        return dct

    def _apply_recursively(self, obj, func):
        if isinstance(obj, list):
            result = []
            for item in obj:
                result.append(self._apply_recursively(item, func))
            return result

        elif isinstance(obj, dict):
            result = {}
            for key, value in obj.items():
                result[key] = self._apply_recursively(value, func)
            return result

        else:
            return func(obj)

    async def _apply_recursively_async(self, func, obj):
        if isinstance(obj, list):
            result = []
            for item in obj:
                result.append(await self._apply_recursively_async(item, func))
            return result

        elif isinstance(obj, dict):
            result = {}
            for key, value in obj.items():
                result[key] = await self._apply_recursively_async(value, func)
            return result

        else:
            return await func(obj)

    def prepare(self, obj):
        return self._apply_recursively(obj, lambda o: o.__dump__() if hasattr(o, "__dump__") else o)

    def load(self, file_path, *args, globals_=None, **kwargs):
        globals_ = globals_ or Globals()
        with open(file_path, "r") as file:
            return json.load(
                file,
                *args,
                **kwargs,
                object_hook=lambda obj: self.hook(obj, globals_))

    def dump(self, obj, file_path, *args, **kwargs):
        result = json.dumps(self.prepare(obj), indent=4, *args, **kwargs)
        with open(file_path, "w") as file:
            file.write(result)

    def finalize_loading(self, dct):
        return self._apply_recursively(dct, lambda l: l.load() if isinstance(l, LateLoader) else l)

    async def finalize_loading_even_async(self, dct):
        async def mapper(it):
            if isinstance(it, AsyncLoader):
                return await it.load_async()
            elif isinstance(it, LateLoader):
                return it.load()
            return it

        return self._apply_recursively(dct, mapper)
