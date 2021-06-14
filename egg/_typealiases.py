from typing import *  # get them all in the global namespace


T = TypeVar("T")
TypeOrFunction = TypeVar("TypeOrFunction", type, Callable[..., Any])
Decorator = Callable[[TypeOrFunction], TypeOrFunction]
Function = Callable[..., Any]
