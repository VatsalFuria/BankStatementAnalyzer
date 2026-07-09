import os
import importlib
import pkgutil
from analyzer.parsers.base_parser import BaseParser
from analyzer.exceptions import ParserNotFoundError
from analyzer.logging_config import logger

_instances_by_name = {}

def discover_parsers():
    global _instances_by_name
    _instances_by_name = {}
    package_dir = os.path.dirname(__file__)
    for _, module_name, _ in pkgutil.iter_modules([package_dir]):
        if module_name in ('base_parser', '__init__'):
            continue
        module = importlib.import_module(f"analyzer.parsers.{module_name}")
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (isinstance(attr, type) and issubclass(attr, BaseParser)
                    and attr is not BaseParser
                    and attr.__module__ == module.__name__):
                instance = attr()
                if instance.display_name in _instances_by_name:
                    logger.warning(
                        f"Duplicate parser display_name '{instance.display_name}' "
                        f"— '{attr.__name__}' will overwrite the earlier one in the dropdown."
                    )
                _instances_by_name[instance.display_name] = instance
    logger.info(f"Discovered {len(_instances_by_name)} parser(s): {list(_instances_by_name)}")
    return list(_instances_by_name.values())

def get_parser_choices() -> dict:
    """{display_name: parser instance} — for populating the GUI dropdown."""
    if not _instances_by_name:
        discover_parsers()
    return dict(_instances_by_name)

def get_parser_by_name(name: str) -> BaseParser:
    choices = get_parser_choices()
    if name not in choices:
        raise ParserNotFoundError(f"No parser registered with name '{name}'")
    return choices[name]

def get_parser_for_file(filepath: str):
    """Auto-detect fallback, kept for CLI/test use (test_import.py, main.py
    call import_file without parser_name). The GUI no longer relies on this
    by default — the user picks explicitly instead."""
    for parser in get_parser_choices().values():
        if parser.can_parse(filepath):
            return parser
    return None