"""Public export interface, loaded on demand to keep CLI parsing lightweight."""

from importlib import import_module

_EXPORTS = {
    "AbaqusSource": (".source", "AbaqusSource"),
    "Converter": (".converter", "Converter"),
    "Selection": (".models", "Selection"),
    "OutputOptions": (".outputs", "OutputOptions"),
}
__all__ = tuple(_EXPORTS)


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(name)
    module, attribute = _EXPORTS[name]
    value = getattr(import_module(module, __name__), attribute)
    globals()[name] = value
    return value
