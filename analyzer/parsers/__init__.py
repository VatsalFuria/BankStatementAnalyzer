import os
import importlib
import pkgutil
from analyzer.parsers.base_parser import BaseParser

_parsers = []

def discover_parsers():
    global _parsers
    _parsers = []
    package_dir = os.path.dirname(__file__)
    for _, module_name, _ in pkgutil.iter_modules([package_dir]):
        if module_name in ('base_parser', '__init__'):
            continue
        module = importlib.import_module(f"analyzer.parsers.{module_name}")
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if isinstance(attr, type) and issubclass(attr, BaseParser) and attr is not BaseParser:
                _parsers.append(attr())
    return _parsers

def get_parser_for_file(filepath: str) -> BaseParser:
    for parser in _parsers:
        if parser.can_parse(filepath):
            return parser
    return None