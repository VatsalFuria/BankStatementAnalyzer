import os
import tempfile
import unittest

from analyzer import database as db_module
from analyzer.rule_engine import add_rule, export_rules_to_json, import_rules_from_json, get_all_rules


class RulesJsonTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_statements.db")
        db_module.DB_PATH = self.db_path
        db_module.init_db()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_export_then_merge_import_is_idempotent(self):
        add_rule(1, "description", "contains", "NETFLIX", "Subscriptions", category_type="expense")
        rules_json_path = os.path.join(self.temp_dir.name, "rules.json")
        export_rules_to_json(rules_json_path)

        inserted = import_rules_from_json(rules_json_path, mode="merge")
        self.assertEqual(inserted, 0)  # already present, nothing new
        self.assertEqual(len(get_all_rules()), 1)

    def test_replace_import_wipes_existing_rules(self):
        add_rule(1, "description", "contains", "OLDRULE", "Old", category_type="expense")
        snapshot_path = os.path.join(self.temp_dir.name, "snapshot.json")
        export_rules_to_json(snapshot_path)

        add_rule(2, "description", "contains", "NEWRULE", "New", category_type="expense")
        import_rules_from_json(snapshot_path, mode="replace")

        categories = {r["category"] for r in get_all_rules()}
        self.assertEqual(categories, {"Old"})


if __name__ == "__main__":
    unittest.main()