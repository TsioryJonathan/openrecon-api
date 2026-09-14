#!/usr/bin/env python3
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.main import app

output = Path(__file__).parent.parent / "openapi.yaml"
schema = app.openapi()
output.write_text(yaml.dump(schema, default_flow_style=False, allow_unicode=True, sort_keys=False))
print(f"Generated {output}")
