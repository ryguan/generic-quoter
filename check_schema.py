import requests
import json

kalshi_v2_openapi_url = "https://trading-api.readme.io/openapi/6573c0ae0b7d2f002bbae214"
r = requests.get(kalshi_v2_openapi_url)
print(r.status_code)
# Try looking directly
try:
    print("Trying explicit kalshi spec...")
    r = requests.get("https://trading-api.readme.io/openapi/6573c0ae0b7d2f002bbae214")
    spec = r.json()
    # Search for TimeInForce
    components = spec.get("components", {}).get("schemas", {})
    for k, v in components.items():
        if "TimeInForce" in k or "CreateOrderRequest" in k:
            if "properties" in v and "time_in_force" in v["properties"]:
                print("Enum values:", v["properties"]["time_in_force"].get("enum"))
except Exception as e:
    print(e)
