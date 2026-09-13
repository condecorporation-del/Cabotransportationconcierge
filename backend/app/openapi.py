"""Imprime el contrato OpenAPI; lo usa packages/api-client (`npm run gen`)."""

import json
import sys

from app.main import app

# Bytes UTF-8: en Windows la consola usaría cp1252 y el contrato diferiría del de CI.
sys.stdout.buffer.write(json.dumps(app.openapi(), ensure_ascii=False).encode())
