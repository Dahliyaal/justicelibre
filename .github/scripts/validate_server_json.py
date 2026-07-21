#!/usr/bin/env python3
"""Valide server.json contre le schéma officiel du MCP registry.

Lancé en CI. Échec si le JSON est invalide ou ne respecte pas le schéma
déclaré dans son champ $schema. Le schéma est récupéré en ligne ; en cas
d'indisponibilité réseau, on valide au moins que le JSON est bien formé
et porte les champs obligatoires (dégradation gracieuse, jamais un faux
échec pour un souci réseau).
"""
import json
import sys
import urllib.request
from pathlib import Path

doc = json.loads(Path("server.json").read_text(encoding="utf-8"))
schema_url = doc.get("$schema")
print(f"server.json chargé — {len(doc.get('tools', []))} tools, $schema={schema_url}")

if not schema_url:
    print("ERREUR : champ $schema absent de server.json", file=sys.stderr)
    sys.exit(1)

try:
    with urllib.request.urlopen(schema_url, timeout=15) as r:
        schema = json.loads(r.read())
except Exception as e:  # réseau indisponible → validation minimale
    print(f"[schéma inaccessible : {e}] — validation minimale (champs requis)")
    for field in ("name", "description", "version", "tools"):
        if field not in doc:
            print(f"ERREUR : champ requis manquant : {field}", file=sys.stderr)
            sys.exit(1)
    print("OK (validation minimale)")
    sys.exit(0)

import jsonschema
jsonschema.validate(doc, schema)
print("OK — server.json valide contre le schéma officiel du registry.")
