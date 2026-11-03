"""Run from a source checkout without installing the project itself."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent / 'src'))
from wifi_migrate.cli import main
raise SystemExit(main(sys.argv[1:] or ['gui']))
