import os
import sys
import json
import re

from abc import abstractmethod
from functools import partial
from importlib.machinery import ModuleSpec
from importlib.abc import Loader, MetaPathFinder
from types import ModuleType

from egg.modifiers import overrides, singleton
from hypnosis.utils import DummyImportLoader


class _InterfaceMetaPathFinder(MetaPathFinder):
    def __init__(self, loader, extension, pure_domain):
        self._loader = loader
        self._extension = extension
        self._pure_domain = pure_domain

    @property
    def domain(self):
        return (self._pure_domain or "interface."+self._extension) + "."

    @overrides(MetaPathFinder, check=False)
    def find_spec(self, fullname, path, target=None):  # FIXME : Relative 'from .. [...]' imports are not handled properly
        if path is None or path == []:
            path = [os.getcwd()] + sys.path

        if self.domain.startswith(fullname+"."):
            return ModuleSpec(
                fullname,
                DummyImportLoader(),
                is_package=True
            )

        if not fullname.startswith(self.domain):
            return None

        fullname = fullname.removeprefix(self.domain).replace(".", "/")
        for entry in path:
            fullpath = os.path.join(entry, fullname)
            if os.path.isdir(fullpath):
                return ModuleSpec(
                    fullname,
                    DummyImportLoader(),
                    is_package=True
                )

            fullpath += "."+self._extension
            if os.path.isfile(fullpath):
                return ModuleSpec(fullname, self._loader(fullpath))

        raise NameError(f"Can't find file {fullname}.{self._extension}")


class ExtraInterface(Loader):
    __domain__ = None
    __extension__ = None
    __storage_field_name__ = "content"

    def __init__(self, storage_field_name, filename):
        self.storage_field_name = storage_field_name
        self.filename = filename

    @classmethod
    def install(cls, *, storage_field=None, domain=None):
        if cls.__extension__ is None:
            raise ValueError("Must provide a value for class field '__extension__'")

        sys.meta_path.insert(0, _InterfaceMetaPathFinder(
            partial(cls, storage_field or cls.__storage_field_name__),
            cls.__extension__,
            domain or cls.__domain__
        ))

    @overrides(Loader)
    def create_module(self, spec):
        return None

    @overrides(Loader, check=False)
    def exec_module(self, module: ModuleType) -> None:
        with open(self.filename, "r") as file:
            obj = self._as_python_object(file.read())
            module.__dict__[self.storage_field_name] = obj

    @abstractmethod
    def _as_python_object(self, file_content):
        ...


@singleton
class Installer:
    def _retrieve_extra_interfaces(self):
        return [
            element for element in globals().values()
            if isinstance(element, type) and element is not ExtraInterface and issubclass(element, ExtraInterface)
        ]

    def install(self, file_extension):
        for interface in self._retrieve_extra_interfaces():
            if interface.__extension__ == file_extension:
                interface.install()

    def install_all(self):
        for interface in self._retrieve_extra_interfaces():
            interface.install()


class JsonInterface(ExtraInterface):
    __extension__ = "json"

    def _as_python_object(self, file_content):
        result = json.loads(file_content)
        return result


class CsvInterface(ExtraInterface):
    __extension__ = "csv"

    def _as_python_object(self, file_content):
        return [
            [it.strip() for it in re.split("[,;]", line) if it.strip() != ""]
            for line in file_content.split("\n") if line.strip() != ""
        ]


