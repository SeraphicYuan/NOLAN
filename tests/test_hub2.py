"""Quick test for hub routes."""
from pathlib import Path
from nolan.hub import create_hub_app

# Create app
app = create_hub_app(db_path=None, projects_dir=None)

# List all routes
print("Registered routes:")
for route in app.routes:
    if hasattr(route, 'path'):
        methods = getattr(route, 'methods', ['N/A'])
        print(f"  {route.path} -> {methods}")
