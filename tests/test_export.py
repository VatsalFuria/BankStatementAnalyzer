import os
import tempfile
import unittest

from analyzer import database as db_module
from analyzer.export import export_workbook


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_statements.db")
        db_module.DB_PATH = self.db_path
        db_module.init_db()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_empty_export_raises_value_error(self):
        output_path = os.path.join(self.temp_dir.name, "empty_export.xlsx")
        with self.assertRaises(ValueError):
            export_workbook(output_path)


if __name__ == "__main__":
    unittest.main()
