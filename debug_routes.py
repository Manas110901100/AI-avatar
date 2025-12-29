from main import app
import json

for route in app.routes:
    if hasattr(route, "methods"):
        print(f"Path: {route.path}, Methods: {route.methods}")
    else:
        print(f"Mount: {route.path}")
