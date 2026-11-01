
import os
import time
import requests
from datetime import datetime, timedelta, timezone

# ==========================================
# Shopify settings
# ==========================================

STORE = os.environ["SHOPIFY_STORE"]
TOKEN = os.environ["SHOPIFY_ACCESS_TOKEN"]

HEADERS = {
    "X-Shopify-Access-Token": TOKEN,
    "Content-Type": "application/json"
}

API_URL = f"https://{STORE}/admin/api/2025-01/graphql.json"

# Past 365 days
since = (
    datetime.now(timezone.utc) - timedelta(days=365)
).strftime("%Y-%m-%dT%H:%M:%SZ")

print(f"Fetching orders since: {since}")


# ==========================================
# Shopify API request with retry
# ==========================================

def shopify_request(payload, label="Shopify API"):
    max_attempts = 3

    for attempt in range(max_attempts):
        try:
            res = requests.post(
                API_URL,
                json=payload,
                headers=HEADERS,
                timeout=30
            )

            # Rate limit or temporary server error
            if res.status_code == 429 or res.status_code >= 500:
                print(
                    f"{label}: Temporary HTTP error "
                    f"{res.status_code} "
                    f"(attempt {attempt + 1}/{max_attempts})"
                )

                if attempt < max_attempts - 1:
                    retry_after = res.headers.get("Retry-After")

                    try:
                        wait = float(retry_after) if retry_after else 2 ** (attempt + 1)
                    except ValueError:
                        wait = 2 ** (attempt + 1)

                    time.sleep(wait)
                    continue

                return None

            # Other HTTP errors
            if not res.ok:
                print(
                    f"{label}: HTTP error "
                    f"{res.status_code}: {res.text[:500]}"
                )
                return None

            # Check JSON response
            try:
                data = res.json()
            except requests.exceptions.JSONDecodeError:
                print(
                    f"{label}: Invalid JSON response. "
                    f"HTTP {res.status_code}: {res.text[:500]}"
                )

                if attempt < max_attempts - 1:
                    time.sleep(2 ** (attempt + 1))
                    continue

                return None

            return data

        except requests.exceptions.RequestException as e:
            print(
                f"{label}: Request error: {e} "
                f"(attempt {attempt + 1}/{max_attempts})"
            )

            if attempt < max_attempts - 1:
                time.sleep(2 ** (attempt + 1))
                continue

            return None

    return None


# ==========================================
# Get orders from Shopify
# ==========================================

def get_orders():

    counts = {}
    cursor = None
    has_next = True
    total_orders = 0

    while has_next:

        after = f', after: "{cursor}"' if cursor else ""

        query = f"""
        {{
          orders(first: 250, sortKey: CREATED_AT, query: "created_at:>{since}"{after}) {{
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

        payload = {"query": query}

        data = shopify_request(
            payload,
            label="Get orders"
        )

        if data is None:
            print("ERROR: Failed to retrieve orders.")
            return None

        # GraphQL errors
        if data.get("errors"):
            print(f"GraphQL errors: {data['errors']}")
            return None

        orders = data.get("data", {}).get("orders")

        if orders is None:
            print("ERROR: Orders data is missing.")
            print(data)
            return None

        edges = orders.get("edges", [])
        total_orders += len(edges)

        for edge in edges:

            line_items = edge["node"]["lineItems"]["edges"]

            for item in line_items:

                product = item["node"].get("product")

                if product:

                    product_id = product["id"].split("/")[-1]
                    quantity = item["node"]["quantity"]

                    counts[product_id] = (
                        counts.get(product_id, 0) + quantity
                    )

        page_info = orders.get("pageInfo", {})

        has_next = page_info.get("hasNextPage", False)
        cursor = page_info.get("endCursor")

        if has_next and not cursor:
            print("ERROR: Pagination cursor is missing.")
            return None

    print(f"Total orders fetched: {total_orders}")
    print(f"Total products found: {len(counts)}")

    return counts


# ==========================================
# Update product metafield
# ==========================================

def update_metafield(product_id, count):

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

    payload = {
        "query": query,
        "variables": variables
    }

    data = shopify_request(
        payload,
        label=f"Update product {product_id}"
    )

    if data is None:
        return False

    # GraphQL errors
    if data.get("errors"):
        print(
            f"GraphQL error for {product_id}: "
            f"{data['errors']}"
        )
        return False

    result = (
        data.get("data", {})
        .get("metafieldsSet")
    )

    if result is None:
        print(
            f"Unexpected response for {product_id}: {data}"
        )
        return False

    errors = result.get("userErrors", [])

    if errors:
        print(f"Error for {product_id}: {errors}")
        return False

    return True


# ==========================================
# Main process
# ==========================================

counts = get_orders()

if counts is None:
    print("ERROR: Order retrieval failed. Update cancelled.")
    raise SystemExit(1)

success_count = 0
failed_count = 0

print("Starting product updates...")

for product_id, count in counts.items():

    if update_metafield(product_id, count):

        print(f"Updated product {product_id}: {count}")
        success_count += 1

    else:

        print(f"Failed product {product_id}: {count}")
        failed_count += 1

    # Small interval between API requests
    time.sleep(0.2)


# ==========================================
# Summary
# ==========================================

print("----------------------------------")
print("Update Buy Count completed")
print(f"Success: {success_count}")
print(f"Failed: {failed_count}")
print("----------------------------------")

if failed_count > 0:
    raise SystemExit(1)

print("Done!")
