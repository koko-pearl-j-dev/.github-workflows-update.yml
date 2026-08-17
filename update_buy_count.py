import os
import requests
from datetime import datetime, timedelta, timezone

STORE = os.environ["SHOPIFY_STORE"]
TOKEN = os.environ["SHOPIFY_ACCESS_TOKEN"]
HEADERS = {
    "X-Shopify-Access-Token": TOKEN,
    "Content-Type": "application/json"
}

since = (datetime.now(timezone.utc) - timedelta(days=365)).strftime("%Y-%m-%dT%H:%M:%SZ")
print(f"Fetching orders since: {since}")

def get_orders():
    url = f"https://{STORE}/admin/api/2025-01/graphql.json"
    counts = {}
    cursor = None
    has_next = True

    while has_next:
        after = f', after: "{cursor}"' if cursor else ""
        query = f"""
        {{
        　orders(first: 250, query: "created_at:>{since} status:any"{after}) {{
            edges {{
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
            pageInfo {{ hasNextPage endCursor }}
          }}
        }}
        """
        res = requests.post(url, json={"query": query}, headers=HEADERS)
        data = res.json()

        orders = data.get("data", {}).get("orders", {})
        edges = orders.get("edges", [])

        for edge in edges:
            for item in edge["node"]["lineItems"]["edges"]:
                node = item["node"]
                if node["product"]:
                    pid = node["product"]["id"].split("/")[-1]
                    counts[pid] = counts.get(pid, 0) + node["quantity"]

        page_info = orders.get("pageInfo", {})
        has_next = page_info.get("hasNextPage", False)
        cursor = page_info.get("endCursor")

    return counts

def update_metafield(product_id, count):
    url = f"https://{STORE}/admin/api/2025-01/graphql.json"
    query = """
    mutation metafieldsSet($metafields: [MetafieldsSetInput!]!) {
      metafieldsSet(metafields: $metafields) {
        metafields { key value }
        userErrors { field message }
      }
    }
    """
    variables = {
        "metafields": [{
            "ownerId": f"gid://shopify/Product/{product_id}",
            "namespace": "custom",
            "key": "buy_count_365days",
            "value": str(count),
            "type": "number_integer"
        }]
    }
    res = requests.post(url, json={"query": query, "variables": variables}, headers=HEADERS)
    data = res.json()
    errors = data.get("data", {}).get("metafieldsSet", {}).get("userErrors", [])
    if errors:
        print(f"Error for {product_id}: {errors}")

counts = get_orders()
for product_id, count in counts.items():
    update_metafield(product_id, count)
    print(f"Updated product {product_id}: {count}")

print("Done!")
