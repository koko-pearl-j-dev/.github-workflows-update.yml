import os
import requests
from datetime import datetime, timedelta, timezone

STORE = os.environ["SHOPIFY_STORE"]
TOKEN = os.environ["SHOPIFY_ACCESS_TOKEN"]
HEADERS = {
    "X-Shopify-Access-Token": TOKEN,
    "Content-Type": "application/json"
}

since = (datetime.now(timezone.utc) - timedelta(days=365)).strftime("%Y-%m-%d")

def get_orders():
    url = f"https://{STORE}/admin/api/2025-01/graphql.json"
    counts = {}
    cursor = None

    while True:
        after = f', after: "{cursor}"' if cursor else ""
        query = f"""
        {{
          orders(first: 250, query: "created_at:>{since} status:any"{after}) {{
            edges {{
              cursor
              node {{
                lineItems(first: 50) {{
                  edges {{
                    node {{
                      product {{ id }}
                      quantity
                    }}
                  }}
                }}
              }}
            }}
            pageInfo {{ hasNextPage }}
          }}
        }}
        """
        res = requests.post(url, json={"query": query}, headers=HEADERS)
        data = res.json()

        orders = data.get("data", {}).get("orders", {})
        edges = orders.get("edges", [])

        for edge in edges:
            cursor = edge["cursor"]
            for item in edge["node"]["lineItems"]["edges"]:
                node = item["node"]
                if node["product"]:
                    pid = node["product"]["id"].split("/")[-1]
                    counts[pid] = counts.get(pid, 0) + node["quantity"]

        if not orders.get("pageInfo", {}).get("hasNextPage"):
            break

    return counts

def update_metafield(product_id, count):
    url = f"https://{STORE}/admin/api/2025-01/products/{product_id}/metafields.json"
    data = {
        "metafield": {
            "namespace": "custom",
            "key": "buy_count_365days",
            "value": str(count),
            "type": "number_integer"
        }
    }
    requests.post(url, json=data, headers=HEADERS)

counts = get_orders()
for product_id, count in counts.items():
    update_metafield(product_id, count)
    print(f"Updated product {product_id}: {count}")

print("Done!")
