from importlib.abc import Loader
from egg.modifiers import overrides


class DummyImportLoader(Loader):
    @overrides(Loader)
    def create_module(self, spec):
        return None

    @overrides(Loader, check=False)
    def exec_module(self, module):
        pass
