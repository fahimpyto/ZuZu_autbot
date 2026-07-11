import argparse
import csv
import json
import re
import time
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# --- Configuration ---
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0.0.0 Safari/537.36"
)
USER_IDS_FILE = Path("chat_ids.json")
CSV_FILE_NAME = Path("scraped_devices.csv")
RAW_DATA_DIR = Path("raw_data")
FORMATTED_DATA_DIR = Path("formatted_data")
IMAGES_DIR = Path("images")

TELEGRAM_BOT_TOKEN = Path(".env").read_text().strip() if Path(".env").exists() else __import__("os").getenv("TELEGRAM_BOT_TOKEN")
if not TELEGRAM_BOT_TOKEN:
    raise ValueError("NO SECRET CODE FOUND! PLEASE SET TELEGRAM_BOT_TOKEN in GitHub Secrets or .env file")

# ---------- Utility (Telegram অংশ) ----------

def load_user_ids() -> set[int]:
    if not USER_IDS_FILE.exists():
        print(f"⚠️ Warning: '{USER_IDS_FILE}' not found. No users to notify.")
        return set()
    try:
        content = USER_IDS_FILE.read_text(encoding="utf-8")
        if not content.strip():
            print(f"⚠️ Warning: '{USER_IDS_FILE}' is empty. No users to notify.")
            return set()
        return set(json.loads(content))
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"❌ Error loading user IDs from '{USER_IDS_FILE}': {e}")
        return set()


def ensure_folder(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def download_and_resize_image(url: str, save_path: Path, width: int = 300) -> None:
    if not url:
        print("❌ Image URL missing. Skipping download.")
        return
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        img = Image.open(BytesIO(response.content))
        w_percent = (width / float(img.size[0]))
        height = int((float(img.size[1]) * float(w_percent)))
        img_resized = img.resize((width, height), Image.Resampling.LANCZOS)
        img_resized.save(save_path)
        print(f"🖼️ Resized image saved: {save_path}")
    except Exception as e:
        print(f"❌ Error downloading/resizing image: {e}")


def load_scraped_links_from_csv() -> set[str]:
    if not CSV_FILE_NAME.exists():
        return set()
    with CSV_FILE_NAME.open("r", newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        try:
            next(reader)
        except StopIteration:
            return set()
        return {row[1] for row in reader if len(row) > 1}


def append_to_csv(device_name: str, url: str) -> None:
    file_exists = CSV_FILE_NAME.exists()
    with CSV_FILE_NAME.open("a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["Device Name", "URL"])
        writer.writerow([device_name, url])


# ---------- Scrape latest device links (অপরিবর্তিত) ----------
def scrape_latest_device_links(playwright) -> list[str]:
    print("\n--- Step 1: Finding Latest Device Links ---")
    url = "https://www.gsmarena.com/"

    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context(user_agent=USER_AGENT, java_script_enabled=True, bypass_csp=True)
    context.route("**/*.{png,jpg,jpeg,gif,svg,css,woff,woff2}", lambda route: route.abort())
    page = context.new_page()

    try:
        print(f"🔄 Navigating to: {url}")
        page.goto(url, timeout=120000, wait_until="domcontentloaded")

        try:
            accept_button = page.locator('button:has-text("Agree and proceed")').first
            accept_button.click(timeout=5000)
            print("🍪 Cookie consent handled.")
        except PlaywrightTimeoutError:
            print("👍 Cookie banner not found.")

        latest_devices_module = page.locator("div.module-phones.module-latest").first
        latest_devices_module.wait_for(timeout=30000)
        print("✅ 'Latest devices' section found.")

        links = latest_devices_module.locator("a.module-phones-link").all()
        if not links:
            print("❌ No links found.")
            return []

        base_url = "https://www.gsmarena.com/"
        device_links = [f"{base_url}{link.get_attribute('href' )}" for link in links if link.get_attribute("href")]

        print(f"🔗 Found {len(device_links)} links.")
        return device_links
    except Exception as e:
        print(f"❌ Error: {e}")
        return []
    finally:
        browser.close()


# ---------- Scraper (অপরিবর্তিত) ----------
def scrape_device(context, url: str) -> dict | None:
    page = context.new_page()
    try:
        print(f"🔄 Navigating to: {url}")
        page.goto(url, timeout=120000, wait_until="domcontentloaded")
        try:
            accept_button_selector = 'button:has-text("Agree"), button:has-text("Accept")'
            accept_button = page.locator(accept_button_selector)
            if accept_button.is_visible(timeout=5000):
                print("🍪 Cookie consent banner found. Clicking 'Agree'...")
                accept_button.click()
        except PlaywrightTimeoutError:
            print("👍 Cookie consent banner not found or already handled.")
        page.wait_for_selector("h1.specs-phone-name-title", timeout=30000)
        device_name = page.locator("h1.specs-phone-name-title").inner_text().strip()
        print(f"📱 Scraping: {device_name}")
        data = {"url": url, "name": device_name}
        try:
            img_src = page.locator(".specs-photo-main img").get_attribute("src")
            if img_src and not img_src.startswith('http' ):
                data["image"] = f"https://www.gsmarena.com/{img_src}"
            else:
                data["image"] = img_src
        except Exception:
            data["image"] = None
        highlights_locator = page.locator(".specs-spotlight-features li" )
        data["highlights"] = [highlights_locator.nth(i).inner_text().strip() for i in range(highlights_locator.count())]
        specs = {}
        tables = page.locator("#specs-list table")
        for t in range(tables.count()):
            rows = tables.nth(t).locator("tr")
            category = ""
            for r in range(rows.count()):
                row = rows.nth(r)
                th = row.locator("th")
                if th.count() > 0:
                    category = th.inner_text().strip()
                    if category not in specs:
                        specs[category] = {}
                ttl = row.locator("td.ttl")
                nfo = row.locator("td.nfo")
                if ttl.count() > 0 and nfo.count() > 0 and category:
                    key = ttl.inner_text().strip()
                    val = nfo.inner_text().strip()
                    specs[category][key] = val
        data["specs"] = specs
        print("✅ Scraping completed successfully!")
        return data
    except Exception as e:
        print(f"❌ An error occurred during scraping: {e}")
        page.screenshot(path="error_screenshot.png")
        print("📸 Screenshot saved as 'error_screenshot.png' for debugging.")
        return None
    finally:
        page.close()
        print("🚪 Page closed.")


# ---------- Formatter (অপরিবর্তিত) ----------
def transform_gsmarena_to_formatted(data):
    def get_spec(category, key, default=""):
        key = key.replace("  ", "\xa0")
        return data.get("specs", {}).get(category, {}).get(key, default)

    camera_data = {
        "Rear:": "", "Flash:": get_spec("MAIN CAMERA", "Features"),
        "Front:": get_spec("SELFIE CAMERA", "Single") or get_spec("SELFIE CAMERA", "Dual"),
        "Folded:": "", "Main camera:": "", "Second camera:": "", "Third camera:": "", "Specifications:": "",
        "Video recording:": get_spec("MAIN CAMERA", "Video")
    }
    main_cam_spec = get_spec("MAIN CAMERA", "Triple") or get_spec("MAIN CAMERA", "Quad") or get_spec("MAIN CAMERA",
                                                                                                     "Dual") or get_spec(
        "MAIN CAMERA", "Single")
    if main_cam_spec:
        camera_data["Rear:"] = main_cam_spec.split('\n')[0]
        cam_specs = [line.strip() for line in main_cam_spec.split('\n')]
        if len(cam_specs) > 0: camera_data["Main camera:"] = cam_specs[0]
        if len(cam_specs) > 1: camera_data["Second camera:"] = cam_specs[1]
        if len(cam_specs) > 2: camera_data["Third camera:"] = cam_specs[2]
        if len(cam_specs) > 0:
            aperture_match = re.search(r'f/\d+(\.\d+)?', cam_specs[0])
            focal_length_match = re.search(r'\d+\s*mm', cam_specs[0])
            specs_str = []
            if aperture_match: specs_str.append(f"Aperture size: {aperture_match.group(0).upper()}")
            if focal_length_match: specs_str.append(f"Focal Length: {focal_length_match.group(0)}")
            camera_data["Specifications:"] = ' '.join(specs_str)
    design_data = {
        "Keys:": "Right: Volume control, Lock/Unlock key", "Colors:": get_spec("MISC", "Colors"),
        "Folded:": get_spec("BODY", "Folded"),
        "Weight:": get_spec("BODY", "Weight"), "Materials:": get_spec("BODY", "Build"),
        "Biometrics:": get_spec("FEATURES", "Sensors"),
        "Dimensions:": get_spec("BODY", "Dimensions"), "Resistance:": get_spec("BODY", "  ") or get_spec("BODY", "")
    }
    battery_type_str = get_spec("BATTERY", "Type", "")
    capacity_match = re.search(r'(\d+\s*mAh)', battery_type_str)
    capacity = capacity_match.group(1).strip() if capacity_match else ""
    type_info = battery_type_str.replace(capacity_match.group(0), "").strip(
        ', ') if capacity_match else battery_type_str
    battery_data = {
        "Type:": f"{type_info}, Not user replaceable" if 'non-removable' in type_info.lower() else type_info,
        "Capacity:": capacity, "Charging:": get_spec("BATTERY", "Charging"), "Max charge speed:": ""}
    charging_str = get_spec("BATTERY", "Charging")
    wired_speed_match = re.search(r'(\d+(\.\d+)?W)\s+wired', charging_str, re.IGNORECASE)
    wireless_speed_match = re.search(r'(\d+(\.\d+)?W)\s+wireless', charging_str, re.IGNORECASE)
    speeds = []
    if wired_speed_match: speeds.append(f"Wired: {wired_speed_match.group(1)}")
    if wireless_speed_match: speeds.append(f"Wireless: {wireless_speed_match.group(1)}")
    battery_data["Max charge speed:"] = ''.join(speeds)
    display_data = {
        "Size:": get_spec("DISPLAY", "Size").split(',')[0].strip(), "Features:": get_spec("FEATURES", "Sensors"),
        "Resolution:": get_spec("DISPLAY", "Resolution"),
        "Technology:": get_spec("DISPLAY", "Type").split(',')[0], "Refresh rate:": "", "Screen-to-body:": "",
        "Peak brightness:": "", "Front cover display:": get_spec("DISPLAY", "Secondary display") or ""
    }
    display_type_str = get_spec("DISPLAY", "Type")
    refresh_rate_match = re.search(r'(\d+Hz)', display_type_str)
    if refresh_rate_match: display_data["Refresh rate:"] = refresh_rate_match.group(1)
    size_str = get_spec("DISPLAY", "Size")
    s2b_match = re.search(r'(\d+(\.\d+)?%)\s*\(screen-to-body ratio\)', size_str)
    if s2b_match: display_data["Screen-to-body:"] = f"{s2b_match.group(1)} %"
    brightness_match = re.search(r'(\d+)\s*nits\s*\(peak\)', display_type_str, re.IGNORECASE)
    if brightness_match: display_data["Peak brightness:"] = f"{brightness_match.group(1)} cd/m2 (nit)"
    cellular_data = {
        "Technology:": get_spec("NETWORK", "Technology"), "2G bands:": get_spec("NETWORK", "2G bands"),
        "3G bands:": get_spec("NETWORK", "3G bands"),
        "4G bands:": get_spec("NETWORK", "4G bands"), "5G bands:": get_spec("NETWORK", "5G bands"),
        "SIM type:": get_spec("BODY", "SIM")
    }
    internal_mem = get_spec("MEMORY", "Internal", "")
    storage_ram_pairs = re.findall(r'(\d+\s*(?:GB|TB))\s+(\d+\s*GB)\s+RAM', internal_mem)
    if storage_ram_pairs:
        storage, ram = storage_ram_pairs[0]
    else:
        storage_match = re.search(r'(\d+\s*(?:GB|TB))', internal_mem)
        ram_match = re.search(r'(\d+\s*GB)\s+RAM', internal_mem)
        storage = storage_match.group(1) if storage_match else ""
        ram = ram_match.group(1) if ram_match else ""
    hardware_data = {
        "OS:": get_spec("PLATFORM", "OS"), "GPU:": get_spec("PLATFORM", "GPU"), "RAM:": ram,
        "Processor:": get_spec("PLATFORM", "Chipset"),
        "Device type:": "Smartphone",
        "Internal storage:": f"{storage} (UFS), not expandable" if get_spec("MEMORY", "Card slot").lower() in ["no",
                                                                                                               ""] else f"{storage} (UFS)"
    }
    multimedia_data = {
        "Speakers:": get_spec("SOUND", "Loudspeaker"), "Headphones:": get_spec("SOUND", "3.5mm jack"),
        "Screen mirroring:": "Wireless screen share",
        "Additional microphone(s):": "Noise cancellation" if "dedicated mic" in get_spec("SOUND", "  ",
                                                                                         "").lower() else ""
    }
    other_features = []
    if get_spec("COMMS", "NFC"): other_features.append("NFC")
    if get_spec("COMMS", "Infrared port"): other_features.append("Infrared")
    connectivity_data = {
        "USB:": get_spec("COMMS", "USB"), "Other:": ", ".join(other_features), "Wi-Fi:": get_spec("COMMS", "WLAN"),
        "Sensors:": get_spec("FEATURES", "Sensors"),
        "Features:": get_spec("COMMS", "USB"), "Location:": get_spec("COMMS", "Positioning"),
        "Bluetooth:": get_spec("COMMS", "Bluetooth")
    }
    return {
        "Camera": camera_data, "Design": design_data, "Battery": battery_data, "Display": display_data,
        "Cellular": cellular_data,
        "Hardware": hardware_data, "Multimedia": multimedia_data, "Connectivity & Features": connectivity_data
    }


# ---------- Telegram Notification (অপরিবর্তিত) ----------
def send_telegram_notification(device_name: str, device_url: str, image_path: Path | None = None) -> None:
    if not TELEGRAM_BOT_TOKEN:
        print("⚠️ Telegram token not configured. Skipping notification.")
        return

    user_ids = load_user_ids()
    if not user_ids:
        print("🤷 No users registered to notify.")
        return

    def escape_markdown(text: str) -> str:
        escape_chars = r'_*[]()~`>#+-=|{}.!'
        return re.sub(f'([{re.escape(escape_chars)}])', r'\\\1', text)

    safe_device_name = escape_markdown(device_name)
    safe_device_url = escape_markdown(device_url)

    message = (
        f"🔔 *Found New Device\\!* \n\n"
        f"📱 *Name:* {safe_device_name}\n"
        f"🔗 *Link:* {safe_device_url}"
    )
    parse_mode = 'MarkdownV2'

    print(f"✉️ Sending notification to {len(user_ids)} users...")

    for chat_id in user_ids:
        try:
            if image_path and image_path.exists():
                url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
                with image_path.open('rb') as photo:
                    files = {'photo': photo}
                    data = {'chat_id': chat_id, 'caption': message, 'parse_mode': parse_mode}
                    response = requests.post(url, data=data, files=files, timeout=30)
                    response.raise_for_status()
            else:
                url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
                data = {'chat_id': chat_id, 'text': message, 'parse_mode': parse_mode}
                response = requests.post(url, data=data, timeout=20)
                response.raise_for_status()

            print(f"    ✅ Notification sent to {chat_id}")
        except Exception as e:
            print(f"    ❌ Failed to send notification to {chat_id}: {e}")
        time.sleep(1)


# ---------- Main ----------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GSMArena Scraper & Telegram Notifier")
    parser.add_argument("--dry-run", action="store_true", help="Scrape but skip Telegram notifications")
    parser.add_argument("--single-url", type=str, help="Scrape a single device URL instead of latest")
    args = parser.parse_args()

    print("--- Starting Scraper and Notifier ---")

    ensure_folder(RAW_DATA_DIR)
    ensure_folder(FORMATTED_DATA_DIR)
    ensure_folder(IMAGES_DIR)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=USER_AGENT,
            java_script_enabled=True,
            bypass_csp=True
        )
        context.route("**/*.{png,jpg,jpeg,gif,svg,css,woff,woff2}", lambda route: route.abort())
        context.route("**/cmp.js", lambda route: route.abort())
        context.route("**/*google*/**", lambda route: route.abort())

        if args.single_url:
            all_links = [args.single_url]
        else:
            all_links = scrape_latest_device_links(playwright)

        if not all_links:
            print("\nNo links to process. Exiting.")
        else:
            scraped_links = set() if args.single_url else load_scraped_links_from_csv()
            print(f"🔎 Already scraped: {len(scraped_links)}")
            new_links_to_scrape = [link for link in all_links if link not in scraped_links]

            if not new_links_to_scrape:
                print("\n✅ No new devices to scrape.")
            else:
                print(f"\n--- Scraping {len(new_links_to_scrape)} New Devices ---")
                for i, link in enumerate(new_links_to_scrape):
                    print(f"\n[{i + 1}/{len(new_links_to_scrape)}] {link}")
                    raw_data = scrape_device(context, link)
                    if raw_data:
                        formatted_data = transform_gsmarena_to_formatted(raw_data)
                        safe_name = re.sub(r'[\\/*?:"<>|]', "", raw_data["name"]).replace(" ", "_")
                        raw_filename = RAW_DATA_DIR / f"{safe_name}.json"
                        raw_filename.write_text(json.dumps(raw_data, ensure_ascii=False, indent=2), encoding="utf-8")
                        print(f"    ✅ Raw saved: {raw_filename}")
                        formatted_filename = FORMATTED_DATA_DIR / f"{safe_name}.json"
                        formatted_filename.write_text(json.dumps(formatted_data, ensure_ascii=False, indent=2), encoding="utf-8")
                        print(f"    ✅ Formatted saved: {formatted_filename}")
                        image_path = None
                        image_url = raw_data.get("image")
                        if image_url:
                            file_extension = Path(image_url).suffix or ".jpg"
                            image_path = IMAGES_DIR / f"{safe_name}{file_extension}"
                            download_and_resize_image(image_url, image_path)
                        append_to_csv(raw_data["name"], link)
                        print(f"  💾 Logged to CSV")

                        if not args.dry_run:
                            send_telegram_notification(raw_data["name"], link, image_path)

        context.close()
        browser.close()

    print("\n--- Mission Successful ---")
