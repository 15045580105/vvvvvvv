#!/usr/bin/env python3
"""Run VLAN SOME/IP test from someip.py, output to file."""
import sys, os
sys.path.insert(0, r"d:\VCC")

# Redirect stdout to file
OUT = r"d:\VCC\tools\someip_vlan_main_result.txt"

import io
buf = io.StringIO()
old_stdout = sys.stdout
sys.stdout = buf

try:
    from app.common.communication.clients.someip import vlan_main
    rc = vlan_main()
except Exception as e:
    buf.write(f"\nERROR: {e}\n")
    rc = 1
finally:
    sys.stdout = old_stdout
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(buf.getvalue())
    print(f"Result written to {OUT}, exit={rc}")
