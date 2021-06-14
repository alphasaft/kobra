import typing as _typing
from ._doc import as_docstring, doc


def _standard_stream_doc_for(function_name, builtin_python_impl):
    """ Internal helper to define the stream class docstrings """
    return as_docstring(f"""
        @stream(l).{function_name}
        def lambda_(item):
            return lambda_impl(item)
        
        Cleaner shortcut for {builtin_python_impl}, the result is then stored as a stream into lambda_.result,
        or directly returned if used as an expression (e.g result = stream(l).{function_name}(lambda item: x)).
        Using this function does not mutate the original stream, but creates a new one from the result. 
    """)


# noinspection PyPep8Naming
class stream:
    def __init__(self, iterable):
        self._iterable = iterable

    @staticmethod
    def _exploit(result, output):
        output: _typing.Any

        if output.__name__ == "<lambda>":
            return stream(result)
        else:
            output.result = stream(result)
            return output

    @doc(_standard_stream_doc_for("filter", "filter(lambda item: lambda_impl(item), l)"))
    def filter(self, filter_lambda):
        return self._exploit(filter(filter_lambda, self._iterable), output=filter_lambda)

    @doc(_standard_stream_doc_for("map", "map(lambda item: lambda_impl(item), l)"))
    def map(self, map_lambda):
        return self._exploit(map(map_lambda, self._iterable), output=map_lambda)

    def collect_as(self, collector_class):
        try:
            return collector_class(self._iterable)
        except TypeError:
            raise TypeError(f"class '{collector_class.__name__}' is unable to collect streams") from None
