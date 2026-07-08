#!/usr/bin/env python3
import sys, traceback
sys.path.insert(0, '/app')
sys.stdout = open('/tmp/debug_output.txt', 'w')
sys.stderr = sys.stdout

print("Starting debug...")
from app.services.database import database_service
print("Imported database_service")

try:
    r = database_service.get_users_paginated()
    print("OK: " + str(r))
except Exception as e:
    print("ERROR: " + str(e))
    traceback.print_exc()

print("Done")
sys.stdout.close()
