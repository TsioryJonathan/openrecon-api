#!/usr/bin/env python3
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.main import app

output = Path(__file__).parent.parent / "openapi.json"
schema = app.openapi()
output.write_text(json.dumps(schema, indent=2) + "\n")
print(f"Generated {output}")
