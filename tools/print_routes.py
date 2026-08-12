from app import app

for r in app.url_map.iter_rules():
    print(f"{r.endpoint} {r.rule}")
