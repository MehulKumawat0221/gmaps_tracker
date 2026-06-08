"""
Google Maps New Business Tracker — SerpAPI + CSV Edition
---------------------------------------------------------
Finds new businesses by location + category using SerpAPI,
saves results to CSV files, sends daily alerts via Telegram or Gmail.

NO Google Cloud needed.
NO service_account.json needed.
NO billing card needed.

Just need:
  - SerpAPI key (free at serpapi.com)
  - Gmail app password OR Telegram bot (for alerts)

Requirements:
    pip install -r requirements.txt
"""

import os
import csv
import time
import smtplib
import requests
from pathlib import Path
from datetime import datetime
from email.mime.text import MIMEText
from dotenv import load_dotenv

load_dotenv()

# ─── CONFIG ──────────────────────────────────────────────────────────────────

CLIENTS = [
    {
        "name":      "Mehul Kumawat",
        "locations": ["Jaipur Rajasthan", "Jodhpur Rajasthan"],
        "category":  "restaurant",
        "email":     os.getenv("mehulkumawat0221@gmail.com"),  # sends to yourself by default
    },
    # Add more clients below:
    # {
    #     "name":      "Client B",
    #     "locations": ["Udaipur Rajasthan", "Kota Rajasthan"],
    #     "category":  "cafe",
    #     "email":     "clientb@example.com",
    # },
]

SERP_API_KEY       = os.getenv("SERP_API_KEY")
GMAIL_USER         = os.getenv("GMAIL_USER")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID")

# Folder where all CSV files are saved
DATA_FOLDER = Path("data")
DATA_FOLDER.mkdir(exist_ok=True)

# ─── CSV HELPERS ─────────────────────────────────────────────────────────────

DB_HEADERS  = ["place_id", "name", "address", "category", "rating", "first_seen", "location"]
NEW_HEADERS = ["name", "address", "category", "rating", "found_at", "location"]


def get_db_path(client_name: str) -> Path:
    """Path to the permanent database CSV for a client."""
    safe = client_name.lower().replace(" ", "_")
    return DATA_FOLDER / f"{safe}_database.csv"


def get_today_path(client_name: str) -> Path:
    """Path to today's new businesses CSV for a client."""
    safe  = client_name.lower().replace(" ", "_")
    today = datetime.now().strftime("%Y-%m-%d")
    return DATA_FOLDER / f"{safe}_new_{today}.csv"


def load_seen_ids(client_name: str) -> set:
    """Load all place_ids already seen for this client."""
    db_path = get_db_path(client_name)
    if not db_path.exists():
        return set()
    with open(db_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return {row["place_id"] for row in reader if row.get("place_id")}


def save_to_database(client_name: str, info: dict):
    """Append a new business to the permanent database CSV."""
    db_path      = get_db_path(client_name)
    write_header = not db_path.exists()
    with open(db_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=DB_HEADERS)
        if write_header:
            writer.writeheader()
        writer.writerow({
            "place_id":   info["place_id"],
            "name":       info["name"],
            "address":    info["address"],
            "category":   info["category"],
            "rating":     info["rating"],
            "first_seen": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "location":   info["location"],
        })


def save_to_today(client_name: str, info: dict):
    """Append a new business to today's results CSV."""
    today_path   = get_today_path(client_name)
    write_header = not today_path.exists()
    with open(today_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=NEW_HEADERS)
        if write_header:
            writer.writeheader()
        writer.writerow({
            "name":     info["name"],
            "address":  info["address"],
            "category": info["category"],
            "rating":   info["rating"],
            "found_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "location": info["location"],
        })


# ─── SERPAPI SEARCH ──────────────────────────────────────────────────────────

def search_places(location: str, category: str) -> list[dict]:
    """
    Search Google Maps via SerpAPI.
    Free plan: 100 searches/month — no card needed.
    Docs: https://serpapi.com/google-maps-api
    """
    url    = "https://serpapi.com/search"
    params = {
        "engine":  "google_maps",
        "q":       f"{category} in {location}",
        "type":    "search",
        "api_key": SERP_API_KEY,
    }

    all_results = []

    for page in range(2):  # max 2 pages = 40 results per location
        if page > 0:
            params["start"] = page * 20
        try:
            resp = requests.get(url, params=params, timeout=15)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"    SerpAPI error: {e}")
            break

        if "error" in data:
            print(f"    SerpAPI: {data['error']}")
            break

        results = data.get("local_results", [])
        if not results:
            break

        all_results.extend(results)
        time.sleep(1)

    return all_results


def extract_info(place: dict, location: str, category: str) -> dict:
    """Extract the fields we care about from a SerpAPI result."""
    return {
        "place_id": place.get("place_id") or place.get("data_id", ""),
        "name":     place.get("title", "Unknown"),
        "address":  place.get("address", ""),
        "category": place.get("type", category),
        "rating":   str(place.get("rating", "")),
        "location": location,
    }


# ─── CORE LOGIC ──────────────────────────────────────────────────────────────

def run_client(client: dict) -> list[dict]:
    """Run one full scan for a client. Returns list of new businesses found."""
    print(f"\n{'─'*55}")
    print(f"  Client : {client['name']}")
    print(f"  Areas  : {', '.join(client['locations'])}")
    print(f"  Type   : {client['category']}")
    print(f"{'─'*55}")

    seen_ids       = load_seen_ids(client["name"])
    new_businesses = []

    for location in client["locations"]:
        print(f"\n  Scanning: {location} / {client['category']}")
        places = search_places(location, client["category"])
        print(f"  API returned {len(places)} results")

        for place in places:
            info = extract_info(place, location, client["category"])
            pid  = info["place_id"]

            if not pid or pid in seen_ids:
                continue

            save_to_database(client["name"], info)
            save_to_today(client["name"], info)
            seen_ids.add(pid)
            new_businesses.append(info)
            print(f"  ✓ NEW: {info['name']} — {info['address']}")

    today_path = get_today_path(client["name"])
    print(f"\n  → {len(new_businesses)} new business(es) found")
    if new_businesses:
        print(f"  → Saved to: {today_path}")

    return new_businesses


# ─── ALERTS ──────────────────────────────────────────────────────────────────

def send_email_gmail(to_email: str, subject: str, body: str):
    """Send email via Gmail app password (free, no third party)."""
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        print("  [Email] Gmail not configured — skipping")
        return
    try:
        msg            = MIMEText(body)
        msg["Subject"] = subject
        msg["From"]    = GMAIL_USER
        msg["To"]      = to_email
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_USER, to_email, msg.as_string())
        print(f"  [Email] Sent to {to_email} ✓")
    except Exception as e:
        print(f"  [Email] Failed: {e}")


def send_telegram(message: str):
    """Send Telegram message, splitting if too long (4096 char limit)."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("  [Telegram] Not configured — skipping")
        return
    try:
        # Split message into chunks of 4000 characters
        chunks = [message[i:i+4000] for i in range(0, len(message), 4000)]
        for chunk in chunks:
            resp = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={
                    "chat_id":    TELEGRAM_CHAT_ID,
                    "text":       chunk,
                    "parse_mode": "Markdown",
                },
                timeout=10,
            )
            if not resp.ok:
                print(f"  [Telegram] Failed: {resp.text}")
                return
            time.sleep(0.5)  # small delay between chunks
        print(f"  [Telegram] Sent ✓ ({len(chunks)} message(s))")
    except Exception as e:
        print(f"  [Telegram] Error: {e}")


def build_alert(client_name: str, businesses: list[dict]) -> str:
    """Build the alert message for email and Telegram."""
    today = datetime.now().strftime("%d %b %Y")
    if not businesses:
        return f"*{client_name}* — {today}\nNo new businesses found today."
    lines = [
        f"*{client_name}* — {today}",
        f"*{len(businesses)} new business(es) found:*\n",
    ]
    for b in businesses:
        lines.append(f"📍 *{b['name']}*")
        lines.append(f"   {b['address']}")
        lines.append(f"   Type: {b['category']} | Rating: {b['rating'] or 'N/A'}")
        lines.append(f"   Area: {b['location']}")
        lines.append("")
    return "\n".join(lines)


# ─── ENTRY POINT ─────────────────────────────────────────────────────────────

def main():
    print(f"\n{'='*55}")
    print(f"  Google Maps Business Tracker (CSV Edition)")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*55}")

    for client in CLIENTS:
        new_businesses = run_client(client)
        message        = build_alert(client["name"], new_businesses)

        if new_businesses:
            subject = f"[{client['name']}] {len(new_businesses)} new business(es) — {datetime.now().strftime('%d %b')}"
            send_email_gmail(client["email"], subject, message.replace("*", ""))
            send_telegram(message)
        else:
            print(f"  No new businesses today — no alert sent")

    print(f"\n{'='*55}")
    print(f"  Done! Check the data/ folder for CSV files.")
    print(f"{'='*55}\n")


if __name__ == "__main__":
    main()