"""Root-level conftest: put the harness root and tests/ on sys.path."""
import sys, os

# Harness root — so 'import agent', 'import config', etc. work from tests
sys.path.insert(0, os.path.dirname(__file__))
# tests/ — so 'from helpers import ...' works inside test modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "tests"))
