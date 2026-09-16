# Voxel Estate — AI-Powered Real Estate Lead Pipeline

A Python-based automation pipeline for US real estate investors. Processes FSBO and price-drop lead data with AI, flags absentee owners, and syncs clean records to client Google Sheets daily.

---

## 🎯 What It Does

- **Reads** raw property CSVs (PropStream, BatchLeads, or custom)
- **Cleans** with Python (drops invalid rows, validates phones, formats addresses)
- **Classifies** seller motivation with AI (Gemini 3.5 Flash)
- **Flags** absentee owners (out-of-state = highest motivation)
- **Pushes** clean records to client Google Sheets via API
- **Deduplicates** — never same lead twice

---

## 🏗️ Architecture

```

Module 1 (data_[collector.py](http://collector.py))

   ↓ CSV/Excel → DataFrame

Module 2 (data_[cleaner.py](http://cleaner.py))

   ↓ Python filter + AI classification

Module 3 (sheet_[pusher.py](http://pusher.py))

   ↓ Google Sheets API push

```

**Multi-format support** — auto-detects PropStream, standard, and custom CSVs via `adapter.py`.

---

## 📂 Project Structure

```

voxel-estate-pipeline/

├── configs/clients/        ← Per-client JSON configs

├── credentials/            ← Service Account JSON (git-ignored)

├── data/

│   ├── clients/            ← Per-client CSVs

│   └── property_leads.csv  ← Sample data

├── logs/                   ← Activity + error logs

├── scripts/

│   ├── onboard_[client.py](http://client.py)   ← 2-minute client setup

│   ├── run_[client.py](http://client.py)       ← Single client run

│   └── run_all_[clients.py](http://clients.py)  ← Multi-client batch

├── src/

│   ├── data_[collector.py](http://collector.py)   ← Module 1

│   ├── data_[cleaner.py](http://cleaner.py)     ← Module 2

│   ├── sheet_[pusher.py](http://pusher.py)     ← Module 3

│   ├── [adapter.py](http://adapter.py)          ← Format conversion

│   ├── absentee_[detector.py](http://detector.py)

│   ├── county_[manager.py](http://manager.py)

│   ├── us_[validators.py](http://validators.py)

│   └── [logger.py](http://logger.py)

├── .env                    ← API keys (git-ignored)

├── .gitignore

├── requirements.txt

└── [README.md](http://README.md)

```

---

## 🚀 Quick Start

### 1. Install Dependencies

```bash

python -m venv venv

.\venv\Scripts\Activate.ps1   # Windows

pip install -r requirements.txt

```

### 2. Configure Environment

Create a `.env` file with:

```

GEMINI_API_KEY=your_gemini_api_key

GEMINI_MODEL=gemini-3.5-flash

GOOGLE_SHEET_ID=your_sheet_id

```

### 3. Add Service Account

Place your Google Service Account JSON at:

```

credentials/service_account.json

```

### 4. Run Pipeline

```bash

# Single client

python scripts/run_[client.py](http://client.py) --client-id client_001

# All clients

python scripts/run_all_[clients.py](http://clients.py)

```

---

## 🤖 AI Classification

Each lead is scored by Gemini 3.5 Flash:

| Signal | Score |

|--------|-------|

| Price drop > 10% OR FSBO with > 5% drop OR out-of-state absentee | `high_motivation` |

| Price drop 5-10% OR FSBO with 0-10% drop OR in-state absentee | `moderate_motivation` |

| No significant signals | `low_motivation` |

Each classification includes a **specific reason** — not generic labels.

---

## 📊 Output Format

Client's Google Sheet receives 8 columns:

| owner_name | address | county | owner_status | phone | signal_type | price | date_flagged |

|------------|---------|--------|--------------|-------|-------------|-------|--------------|

| Sarah Johnson | 456 Pine Ave Houston TX | Harris | out_of_state_absentee | (555) 987-6543 | high_motivation | 450000 | 2026-09-15 |

| David Wilson | 654 Cedar Ln Plano TX | Collin | out_of_state_absentee | (555) 345-6789 | high_motivation | 120000 | 2026-09-15 |

| Robert Taylor | 147 Walnut Way Austin TX | Travis | out_of_state_absentee | (555) 567-8901 | high_motivation | 95000 | 2026-09-15 |

---

## 🔐 Security

The following are **git-ignored** to protect client data and API keys:

- `.env` — API keys
- `credentials/` — Service Account JSON
- `data/clients/` — Client CSVs
- `configs/` — Client Sheet IDs
- `logs/` — Activity + error logs

**County Exclusivity:** Maximum 3 clients per US county.

---

## 🛠️ Tech Stack

- **Python 3.14**
- **pandas** — Data manipulation
- **langchain-google-genai** — AI classification
- **gspread** — Google Sheets API
- **python-dotenv** — Environment management

---

## 📋 Roadmap

### ✅ Now Available

- FSBO + Price-Drop Detection
- AI Motivation Scoring with Reasons
- Absentee Owner Flagging
- Clean US Phone Numbers
- County Exclusivity (3 per county)
- Duplicate Prevention
- Multi-Client Support
- CSV + Excel Input

### 🟡 Coming Q4 2026

- Tax Delinquent Signals
- BatchLeads Direct Import
- Zillow Data Import
- Daily 6 AM Cloud Scheduler
- Email Alerts

### 🔵 2027 Planned

- Web Dashboard
- Equity Estimation
- Multi-County Automation
- CRM Integrations

---

## 📧 Contact

**Founder:** Hamim Alam  

**Website:** [voxelestate.netlify.app]([https://voxelestate.netlify.app](https://voxelestate.netlify.app))

---

*Currently in beta — first 5 clients receive 40% lifetime discount.*