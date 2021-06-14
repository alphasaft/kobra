import abc
import os.path

from ast import *
from importlib.abc import Loader, MetaPathFinder
from importlib.util import spec_from_file_location

from egg.modifiers import overrides, default, final, partially_final, add_effect, call_once
import sys


def find_module_spec(fullname, path, loader):
    if path is None or path == "":
        path = [os.getcwd()] + sys.path  # top level import --
        name = fullname.replace(".", "/")
    elif "." in fullname:
        *parents, name = fullname.split(".")
    else:
        name = fullname

    for entry in path:
        if os.path.isdir(os.path.join(entry, name)):
            filename = os.path.join(entry, name, "__init__.py")
            submodule_locations = [os.path.join(entry, name)]
        else:
            filename = os.path.join(entry, name + ".py")
            submodule_locations = None

        if not os.path.exists(filename):
            continue

        return spec_from_file_location(
            fullname,
            filename,
            loader=loader(filename),
            submodule_search_locations=submodule_locations
        )

    raise NameError(f"Can't find module {fullname}")


class _HookMetaPathFinder(MetaPathFinder):
    def __init__(self, import_hook):
        self._import_hook = import_hook

    @overrides(MetaPathFinder, check=False)
    def find_spec(self, fullname, path, target=None):
        try:
            return find_module_spec(fullname, path, self._import_hook)
        except NameError:
            return None


@partially_final
class ImportHook(Loader, NodeTransformer):
    """
    Allows you to easily create an import hook, i.e something that modify the contents of the imported
    python files before even loading them.
    Import hooks __init__ method must accept the full path to the module to import as its only arguments, and
    set the self.filename attribute to that same value. Overriding transform_module_code will modify the
    source code of the modules, and transform_module_ast will modify the ast of the modules' source code once
    they're parsed ; besides, you can add ast.NodeTransformer-style methods to your import hook, as it inherits
    from ast.NodeTransformer (see also the ast builtin module documentation)
    """
    def __init__(self, filename):
        self.filename = filename

    @final
    @overrides(Loader)
    def create_module(self, spec):
        return None

    @final
    @overrides(Loader, check=False)
    def exec_module(self, module):
        with open(self.filename) as f:
            data = f.read()

        data = compile(
            self.transform_ast(parse(self.transform_module_content(data))),
            filename=self.filename,
            mode="exec"
        )

        exec(data, module.__dict__)

    @default
    def transform_module_content(self, module_content):
        """
        Transform the loaded modules' source code before returning it.
        Default behavior is to return it as is.
        """
        return module_content

    @default
    def transform_module_ast(self, module_ast):
        """
        Transform the loaded modules' ast before return them.
        Default behavior is to call the visit method of the class.
        """
        return self.visit(module_ast)

    @classmethod
    def install(cls):
        """Inserts the hook into the import machinery"""
        sys.meta_path.insert(0, _HookMetaPathFinder(cls))


class _AnnotationProcessorMeta(abc.ABCMeta):
    """
    Internal helper to allow decorating functions with the annotation processor, while in fact this
    will be lost at 'compile' time.
    """
    def __call__(cls, function_or_filename):
        if isinstance(function_or_filename, str):
            return type.__call__(cls, function_or_filename)
        return function_or_filename

    def __new__(mcs, name, bases, namespace):
        cls = type.__new__(mcs, name, bases, namespace)
        cls.__bound_annotation__ = (
            cls.__bound_annotation__
            if cls.__bound_annotation__ is not None and cls.__bound_annotation__ not in cls.mro()
            else cls
        )
        return cls
