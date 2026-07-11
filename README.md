# GSMArena Web Automation & Scraper Bot

Automatically scrapes the latest mobile device data from [GSMArena.com](https://www.gsmarena.com/), extracts detailed specifications, downloads device images, and sends Telegram notifications to registered users — all powered by **GitHub Actions**.

---

## Features

- **Automated Scraping** — Crawls GSMArena's "Latest devices" section using Playwright (headless Chromium).
- **Detailed Spec Extraction** — Captures full device specifications (network, display, camera, battery, platform, etc.).
- **Data Transformation** — Converts raw scraped data into clean, structured JSON (categorized: Camera, Design, Battery, Display, etc.).
- **Image Download & Resize** — Downloads device images and resizes them to 300px width.
- **Duplicate Detection** — Tracks already-scraped devices in `scraped_devices.csv` to avoid re-processing.
- **Telegram Notifications** — Sends formatted messages (with photo) to all registered users when new devices are found.
- **Chat ID Management** — Separate utility (`chat_id.py`) auto-collects Telegram chat IDs from bot interactions.
- **CI/CD with GitHub Actions** — Runs on a schedule (BD time 11 AM & 11 PM) with automatic commit of new data.

---

## Tech Stack

| Technology | Purpose |
|------------|---------|
| Python 3.10 | Core language |
| Playwright | Headless browser automation |
| Pillow | Image processing & resizing |
| Requests | Telegram API calls & image download |
| pytz | Timezone handling (Bangladesh) |
| GitHub Actions | Scheduled execution & auto-deploy |

---

## Project Structure

```
GSMArena-Scraper-Bot/
├── .github/
│   └── workflows/
│       ├── main.yml              # Scheduled scraper (11 AM / 11 PM BDT)
│       └── chat_id.yml           # Chat ID collector (hourly)
├── raw_data/                     # Raw scraped JSON per device
├── formatted_data/               # Transformed/structured JSON per device
├── images/                       # Resized device images (300px)
├── main.py                       # Core scraper, formatter & notifier
├── chat_id.py                    # Telegram chat ID collector
├── chat_ids.json                 # Registered user chat IDs
├── chats_data.csv                # Chat details log
├── scraped_devices.csv           # Scraped device URL tracker
├── error_screenshot.png          # Debug screenshot on failure
├── .gitignore                    # Ignored file patterns
├── requirements.txt              # Python dependencies
├── .env.example                  # Environment variable template
└── README.md                     # This file
```

---

## How It Works

### 1. Scrape Latest Links
`scrape_latest_device_links()` navigates to GSMArena, handles cookie consent, and extracts all links from the "Latest devices" module.

### 2. Filter New Devices
Compares found links against `scraped_devices.csv` to skip already-processed entries.

### 3. Scrape Device Details
`scrape_device()` visits each new URL and extracts:
- Device name & image
- Highlight features
- Full specification tables (network, display, camera, battery, platform, etc.)

### 4. Transform & Save
`transform_gsmarena_to_formatted()` restructures raw data into 8 clean categories. Output saved to:
- `raw_data/<Device_Name>.json` — original scraped data
- `formatted_data/<Device_Name>.json` — transformed/structured data
- `images/<Device_Name>.jpg` — resized device image

### 5. Notify via Telegram
`send_telegram_notification()` sends a message (with photo if available) to all registered chat IDs using `MarkdownV2` formatting.

---

## Data Output

### Raw JSON (`raw_data/`)
Preserves the full GSMArena spec table structure as-is, including raw text.

### Formatted JSON (`formatted_data/`)
Organized into 8 categories:
- **Camera** — Rear, Front, Flash, Video recording
- **Design** — Dimensions, Weight, Materials, Colors, Biometrics
- **Battery** — Type, Capacity, Charging speeds
- **Display** — Size, Resolution, Technology, Refresh rate, Brightness
- **Cellular** — 2G/3G/4G/5G bands, SIM type
- **Hardware** — OS, Processor, GPU, RAM, Storage
- **Multimedia** — Speakers, Headphone jack
- **Connectivity & Features** — Wi-Fi, Bluetooth, USB, NFC, Sensors

### CSV Tracker (`scraped_devices.csv`)
Columns: `Device Name`, `URL` — used for duplicate detection.

---

## Telegram Notifications

### For Users
1. Start a chat with your bot on Telegram.
2. Send any message (the bot auto-registers your chat ID).
3. You'll receive notifications when new devices are scraped.

### For Admins
- Chat IDs are collected by `chat_id.py` and stored in `chat_ids.json`.
- The `chat_id.yml` workflow runs periodically to pick up new users.

---

## GitHub Actions CI/CD

### Main Scraper (`main.yml`)
- **Schedule:** Runs at UTC 05:00 and 17:00 (BD time 11:00 AM & 11:00 PM).
- **Trigger:** Also supports manual `workflow_dispatch`.
- **Permissions:** `contents: write` — auto-commits new data to the repo.

### Chat ID Collector (`chat_id.yml`)
- **Schedule:** Runs hourly to poll for new chat registrations.
- **Auto-commit:** Any new chat IDs are committed back to the repo.

---

## Setup

### Prerequisites
- Python 3.10+
- A Telegram Bot Token (from [@BotFather](https://t.me/BotFather))

### Local Development

```bash
# 1. Clone the repository
git clone <repo-url>
cd GSMArena-Scraper-Bot

# 2. Install dependencies
pip install -r requirements.txt
playwright install chromium

# 3. Set environment variable
# Windows (PowerShell):
$env:TELEGRAM_BOT_TOKEN="your-bot-token-here"
# Linux/macOS:
export TELEGRAM_BOT_TOKEN="your-bot-token-here"

# 4. Run the scraper
python main.py

# 5. Collect chat IDs (optional)
python chat_id.py
```

### GitHub Deployment

1. Push the code to a GitHub repository.
2. Add `TELEGRAM_BOT_TOKEN` to **Settings → Secrets and variables → Actions**.
3. The workflows run automatically on schedule, or you can trigger them manually via the Actions tab.

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Yes | Your Telegram bot token from @BotFather |

---

## Suggested Improvements

- Add a web dashboard to browse scraped devices
- Support more scraped categories (tablets, wearables, etc.)
- Store data in a database (PostgreSQL/SQLite) instead of JSON files
- Add search/filter API for scraped device data
- Implement price tracking if available on GSMArena

---

## License

This project is open source. Feel free to modify and distribute.

---

*Built with Python, Playwright, and GitHub Actions.*
