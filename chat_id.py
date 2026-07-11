import csv
import json
from datetime import datetime
from pathlib import Path

import pytz
import requests


BOT_TOKEN = __import__("os").getenv("TELEGRAM_BOT_TOKEN")
if not BOT_TOKEN:
    print("Warning: TELEGRAM_BOT_TOKEN environment variable not found. For local testing, ensure it's set.")


API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates" if BOT_TOKEN else ""

CSV_FILE_PATH = Path("chats_data.csv")

def get_existing_chat_ids() -> set[int]:
    try:
        with CSV_FILE_PATH.open(mode='r', newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            return {int(row['chat_id']) for row in reader}
    except FileNotFoundError:
        return set()

def fetch_updates() -> list[dict]:
    try:
        response = requests.get(API_URL, params={'offset': -1}, timeout=15)
        response.raise_for_status()
        return response.json().get("result", [])
    except requests.RequestException as e:
        print(f"Error fetching updates from Telegram: {e}")
        return []

def process_updates(updates: list[dict], existing_ids: set[int]) -> list[dict]:
    new_chats = {}
    bdt_timezone = pytz.timezone("Asia/Dhaka")

    for update in updates:
        chat_info = None
        if "message" in update:
            chat_info = update["message"]["chat"]
        elif "my_chat_member" in update:
            chat_info = update["my_chat_member"]["chat"]
        elif "callback_query" in update:
            chat_info = update["callback_query"]["message"]["chat"]

        if chat_info:
            chat_id = chat_info["id"]
            if chat_id not in existing_ids and chat_id not in new_chats:
                chat_type = chat_info.get("type", "N/A")

                if chat_type == "private":
                    name = chat_info.get("first_name", "")
                    if "last_name" in chat_info:
                        name += f" {chat_info.get('last_name', '')}"
                else:
                    name = chat_info.get("title", "N/A")

                utc_now = datetime.now(pytz.utc)
                bdt_now = utc_now.astimezone(bdt_timezone)

                new_chats[chat_id] = {
                    "chat_id": chat_id,
                    "name": name.strip(),
                    "username": chat_info.get("username", "N/A"),
                    "type": chat_type,
                    "first_seen_bdt": bdt_now.strftime('%Y-%m-%d %H:%M:%S %Z')
                }
    return list(new_chats.values())

def append_to_csv(new_chats_data: list[dict]) -> None:
    file_exists = CSV_FILE_PATH.is_file()

    last_serial = 0
    if file_exists:
        with CSV_FILE_PATH.open('r', newline='', encoding='utf-8') as f:
            last_serial = sum(1 for _ in f) - 1

    with CSV_FILE_PATH.open(mode='a', newline='', encoding='utf-8') as f:
        fieldnames = ['serial_no', 'chat_id', 'name', 'username', 'type', 'first_seen_bdt']
        writer = csv.DictWriter(f, fieldnames=fieldnames)

        if not file_exists or last_serial < 0:
            writer.writeheader()
            print("Created new CSV file with headers.")
            last_serial = 0

        for i, chat_data in enumerate(new_chats_data, start=1):
            row_to_write = {'serial_no': last_serial + i, **chat_data}
            writer.writerow(row_to_write)

    print(f"Appended {len(new_chats_data)} new chat(s) to {CSV_FILE_PATH}.")

def save_chat_ids_to_json(chat_ids: set, json_path: str = "chat_ids.json") -> None:
    try:
        Path(json_path).write_text(json.dumps(list(chat_ids), ensure_ascii=False, indent=4), encoding='utf-8')
        print(f"✅ Saved {len(chat_ids)} chat IDs to {json_path}")
    except Exception as e:
        print(f"Error saving chat IDs to JSON: {e}")

def main() -> None:
    if not BOT_TOKEN:
        return

    existing_ids = get_existing_chat_ids()
    print(f"Found {len(existing_ids)} existing chat IDs.")

    updates = fetch_updates()
    if not updates:
        print("No updates found from Telegram.")
        return

    new_chats_data = process_updates(updates, existing_ids)

    if new_chats_data:
        append_to_csv(new_chats_data)
        all_chat_ids = existing_ids.union({c["chat_id"] for c in new_chats_data})
        save_chat_ids_to_json(all_chat_ids)
    else:
        print("No new unique chats to add.")

if __name__ == "__main__":
    main()
