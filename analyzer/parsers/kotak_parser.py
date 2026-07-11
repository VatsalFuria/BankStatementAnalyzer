import os

from analyzer.base_configurable_parser import ConfigurableExcelParser
from analyzer.config import BANK_FORMATS_DIR


class YourBankParser(ConfigurableExcelParser):
    config_path = os.path.join(BANK_FORMATS_DIR, "kotak.json")