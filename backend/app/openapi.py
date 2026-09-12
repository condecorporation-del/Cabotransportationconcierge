"""Imprime el contrato OpenAPI; lo usa packages/api-client (`npm run gen`)."""

import json
import sys

from app.main import app

sys.stdout.write(json.dumps(app.openapi(), ensure_ascii=False))
