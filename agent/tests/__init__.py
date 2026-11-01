# No paid model in the testing path (docs/RUNS.md, part 3): every helper the Python tests make hides the real keys.
import os

os.environ["FABGYM_NO_MODEL"] = "1"
