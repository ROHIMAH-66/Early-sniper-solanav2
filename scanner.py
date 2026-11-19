
import os
import json
import urllib.request
import urllib.parse
from datetime import datetime, timezone

# KONFIGURASI FILTER
MIN_LIQUIDITY = 8000
MIN_VOLUME_M5 = 1000
MIN_BUYS_M5 = 8
MAX_AGE_MINUTES = 10

API_URL = "https://api.geckoterminal.com/api/v2/networks/solana/new_pools"
STATE_FILE = "scanner_state.json"


def get_json(url):
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json;version=20230302",
            "User-Agent": "SolanaEarlySniper/1.0"
        }
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode())


def send_telegram(message):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print("Telegram belum dikonfigurasi.")
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": message
    }).encode()

    req = urllib.request.Request(url, data=data)
    with urllib.request.urlopen(req, timeout=20) as response:
        print("Telegram:", response.status)


def load_state():
    try:
        with open(STATE_FILE, "r") as file:
            return set(json.load(file))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def save_state(state):
    with open(STATE_FILE, "w") as file:
        json.dump(sorted(state), file)


def main():
    print("Memulai pemindaian Solana...")

    url = API_URL + "?include=base_token,quote_token"
    result = get_json(url)

    pools = result.get("data", [])
    included = result.get("included", [])

    tokens = {
        item.get("id"): item.get("attributes", {})
        for item in included
        if item.get("type") == "token"
    }

    seen = load_state()
    now = datetime.now(timezone.utc)
    alerts = []

    for pool in pools:
        attr = pool.get("attributes", {})
        pool_id = pool.get("id", "")

        if not pool_id or pool_id in seen:
            continue

        created = attr.get("pool_created_at")
        if not created:
            continue

        try:
            created_at = datetime.fromisoformat(
                created.replace("Z", "+00:00")
            )
            age = (now - created_at).total_seconds() / 60
        except ValueError:
            continue

        if age < 0 or age > MAX_AGE_MINUTES:
            continue

        liquidity = float(attr.get("reserve_in_usd") or 0)
        volume = float(
            attr.get("volume_usd", {}).get("m5") or 0
        )

        transactions = attr.get("transactions", {}).get("m5", {})
        buys = int(transactions.get("buys") or 0)
        sells = int(transactions.get("sells") or 0)

        if liquidity < MIN_LIQUIDITY:
            continue
        if volume < MIN_VOLUME_M5:
            continue
        if buys < MIN_BUYS_M5 or buys <= sells:
            continue

        relation = pool.get("relationships", {})
        base = relation.get("base_token", {}).get("data", {})
        token_data = tokens.get(base.get("id"), {})

        mint = token_data.get("address", "")
        symbol = token_data.get("symbol", "Unknown")
        name = token_data.get("name", "Unknown")

        if not mint:
            continue

        alerts.append(
            f"🚨 SOLANA EARLY WATCHLIST\n\n"
            f"Token: {name} ({symbol})\n"
            f"Mint: {mint}\n"
            f"Umur: {age:.1f} menit\n"
            f"Likuiditas: ${liquidity:,.0f}\n"
            f"Volume M5: ${volume:,.0f}\n"
            f"Buy M5: {buys}\n"
            f"Sell M5: {sells}\n\n"
            f"Periksa keamanan token sebelum membeli!\n"
            f"https://dexscreener.com/solana/{mint}"
        )

        seen.add(pool_id)

    if alerts:
        send_telegram("\n\n----------------\n\n".join(alerts))
        print(f"Menemukan {len(alerts)} kandidat.")
    else:
        print("Belum ada kandidat yang lolos filter.")

    save_state(seen)


if __name__ == "__main__":
    main()
          
