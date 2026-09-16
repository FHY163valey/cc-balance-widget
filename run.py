"""Source checkout entry point; supports pythonw and paths containing spaces."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from cc_balance_widget.widget import main

if __name__ == "__main__":
    sys.exit(main())
