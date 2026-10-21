"""Regenerate fictional ECU/A2L sample files (safe training data)."""
from pathlib import Path
import sys
root=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(root/'src'))
from ecu_studio.core.extended_demo import generate_extended_demo
print(generate_extended_demo(str(Path(__file__).parent)))
