import os
import requests
from datetime import datetime, timedelta, timezone

STORE = os.environ["SHOPIFY_STORE"]
TOKEN = os.environ["SHOPIFY_ACCESS_TOKEN"]
HEADERS = {
    "X-Shopify-Access-Token": TOKEN,
    "Content-Type": "application/json"
}

# 過去90日の注文を集計
since = (datetime.now(timezone.utc) - timedelta(days=365)).strftime("%Y-%m-%dT%H:%M:%SZ")

def get_orders():
    url = f"https://{STORE}/admin/api/2024-01/orders.json?status=any&created_at_min={since}&limit=250"
    counts = {}
    while url:
        res = requests.get(url, headers=HEADERS).json()
        for order in res.get("orders", []):
            for item in order.get("line_items", []):
                pid = str(item["product_id"])
                counts[pid] = counts.get(pid, 0) + item["quantity"]
        link = requests.get(url, headers=HEADERS).headers.get("Link", "")
        url = None
        for part in link.split(","):
            if 'rel="next"' in part:
                url = part.split(";")[0].strip().strip("<>")
    return counts

def update_metafield(product_id, count):
    url = f"https://{STORE}/admin/api/2024-01/products/{product_id}/metafields.json"
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
