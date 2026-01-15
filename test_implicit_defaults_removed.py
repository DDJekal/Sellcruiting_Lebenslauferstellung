"""
Simple test to verify implicit defaults are removed.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

import yaml
from models import MandantenConfig

print("=" * 70)
print("TEST: IMPLICIT DEFAULTS ENTFERNT")
print("=" * 70)

configs_to_check = [
    "config/mandanten/kita_urban.yaml",
    "config/mandanten/template_460.yaml",
    "config/mandanten/template_62.yaml"
]

all_empty = True

for config_path in configs_to_check:
    with open(config_path, 'r', encoding='utf-8') as f:
        config_data = yaml.safe_load(f)
    
    mandanten_config = MandantenConfig(**config_data)
    
    count = len(mandanten_config.implicit_defaults)
    
    print(f"\n{config_path}:")
    print(f"  Implicit Defaults: {count}")
    
    if count == 0:
        print(f"  OK: Keine implicit defaults")
    else:
        print(f"  FEHLER: {count} implicit defaults gefunden!")
        all_empty = False
        for default in mandanten_config.implicit_defaults:
            print(f"    - prompt_id: {default.prompt_id}")

print("\n" + "=" * 70)
if all_empty:
    print("SUCCESS! Alle implicit defaults wurden entfernt!")
else:
    print("FEHLER! Einige implicit defaults sind noch vorhanden!")
print("=" * 70)
