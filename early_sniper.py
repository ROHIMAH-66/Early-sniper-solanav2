
import os
import json
import urllib.request
import urllib.parse
from datetime import datetime, timezone

# FILTER AWAL — bisa diubah nanti
MIN_LIQUIDITY = 8000
MIN_VOLUME_M5 = 1000
MIN_BUYS_M5 = 8
MAX_AGE_MINUTES = 10

API_URL = (
    "https://api.geckoterminal.com/api/v2/"
    "networks/solana/new_pools"
    "?include=base_token,quote_token"
)

STATE_FILE = "scanner_state.json"


def get_json(url):
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json;version=20230302",
            "User-Agent": "EarlySniperSolana/1.0"
        }
    )

    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def send_telegram(message):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        raise RuntimeError("Telegram secrets belum diatur.")

    url = f"https://api.telegram.org/bot{token}/sendMessage"

    data = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": message
    }).encode("utf-8")

    request = urllib.request.Request(url, data=data)

    with urllib.request.urlopen(request, timeout=30) as response:
        result = json.loads(response.read().decode("utf-8"))

    if not result.get("ok"):
        raise RuntimeError("Telegram gagal mengirim pesan.")


def load_seen():
    try:
        with open(STATE_FILE, "r") as file:
            return set(json.load(file))
    except (FileNotFoundError, json.JSONDecodeError):
        return set()


def save_seen(seen):
    with open(STATE_FILE, "w") as file:
        json.dump(sorted(seen)[-5000:], file)


def number(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def main():
    print("Memulai scanner Solana...")

    result = get_json(API_URL)

    pools = result.get("data", [])
    included = result.get("included", [])

    token_map = {}

    for item in included:
        if item.get("type") == "token":
            token_map[item.get("id")] = item.get("attributes", {})

    seen = load_seen()
    now = datetime.now(timezone.utc)
    alerts = []

    for pool in pools:
        pool_id = pool.get("id")

        if not pool_id or pool_id in seen:
            continue

        attr = pool.get("attributes", {})

        created = attr.get("pool_created_at")
        if not created:
            continue

        try:
            created_at = datetime.fromisoformat(
                created.replace("Z", "+00:00")
            )
            age = (now - created_at).total_seconds() / 60
        except (ValueError, TypeError):
            continue

        if age < 0 or age > MAX_AGE_MINUTES:
            continue

        liquidity = number(attr.get("reserve_in_usd"))
        volume = number(
            attr.get("volume_usd", {}).get("m5")
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

        relationships = pool.get("relationships", {})
        base_relation = relationships.get("base_token", {})
        base_data = base_relation.get("data", {})
        base_id = base_data.get("id")

        token = token_map.get(base_id, {})
        mint = token.get("address")

        if not mint:
            continue

        name = token.get("name", "Unknown")
        symbol = token.get("symbol", "Unknown")

        message = (
            "🚨 SOLANA EARLY WATCHLIST\n\n"
            f"Token: {name} ({symbol})\n"
            f"Mint: {mint}\n"
            f"Umur pool: {age:.1f} menit\n"
            f"Likuiditas: ${liquidity:,.0f}\n"
            f"Volume M5: ${volume:,.0f}\n"
            f"Buy M5: {buys}\n"
            f"Sell M5: {sells}\n\n"
            "Periksa keamanan token secara manual!\n"
            f"DexScreener: https://dexscreener.com/solana/{mint}\n"
            f"RugCheck: https://rugcheck.xyz/tokens/{mint}"
        )

        alerts.append(message)
        seen.add(pool_id)

    if alerts:
        for message in alerts:
            send_telegram(message)

        print(f"{len(alerts)} kandidat dikirim ke Telegram.")
    else:
        print("Belum ada kandidat yang memenuhi filter.")

    save_seen(seen)
    print("Pemindaian selesai.")


if __name__ == "__main__":
    main()
      
