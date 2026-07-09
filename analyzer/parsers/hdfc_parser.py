import os

from analyzer.base_configurable_parser import ConfigurableExcelParser
from analyzer.config import BANK_FORMATS_DIR


class HDFCParser(ConfigurableExcelParser):
    config_path = os.path.join(BANK_FORMATS_DIR, "hdfc.json")