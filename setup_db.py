from analyzer.database import init_db
from analyzer.rule_engine import seed_default_rules

init_db()
seed_default_rules()
print("Database and rules ready.")