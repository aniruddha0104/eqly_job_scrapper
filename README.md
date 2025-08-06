# Job Scraper – Production‑ready & Appify Compatible

This repository contains a **production‑ready** job scraping tool built in
Python.  It automatically retrieves IT and corporate job postings from
multiple sources, filters them for freshness and salary, persists them to
Firebase, and exposes both a command‑line interface and an optional
graphical interface via the `appify` library.  The system is designed to
run twice daily (or on demand) while staying within free‑tier limits of
the APIs and Firebase.

## Features

* **Multiple data sources**: Jobs are fetched from several public APIs,
  including **Remote OK**, **Remotive**, and **Adzuna** (international and
  Indian markets).  Each source has its own module under `sources/` and
  may be enabled or disabled via configuration.
* **Fresh, high‑paying jobs**: Only roles posted within the last seven
  days are considered.  Jobs are filtered by salary (where available) and
  company name to prioritise high‑paying positions at top companies.  A
  configurable list of “top companies” includes FAANG and major Indian IT
  firms.
* **Firebase integration**: When provided with a Firebase service account
  key, the scraper writes job records into a Firestore collection.  Job
  URLs are used as document IDs to prevent duplicates and to allow
  incremental updates.  Only new or updated listings are written on
  subsequent runs.
* **Automated scheduling**: A lightweight scheduler runs the scraping
  pipeline twice per day by default.  You can disable scheduling and run
  manually via the CLI.  The schedule is implemented using the
  `schedule` library; for deployment in cloud environments you can
  alternatively set up a cron job.
* **Appify compatible**: If the optional `appify` package is installed,
  the script exposes a simple graphical interface.  You can specify
  filters such as the number of days, minimum salary, and the maximum
  number of jobs to return; results are displayed in a table that links
  back to the original job postings.
* **Extensible and maintainable**: Each data source lives in its own
  module with a common return schema.  Adding a new source requires
  implementing a single `fetch_jobs` function that yields `Job` objects.
  The code uses type hints, logging, docstrings, and proper error
  handling throughout.

## Usage

### Prerequisites

1. **Python 3.8+**
2. Optional: [appify](https://pypi.org/project/appify/) for a GUI.
3. Optional: A Firebase project with the [Firestore database](https://firebase.google.com/docs/firestore) enabled.
4. API credentials for Adzuna (free tier) if you enable Adzuna scraping.

Install dependencies:

```bash
pip install -r requirements.txt
```

Environment variables:

| Variable | Purpose |
|---------|--------|
| `ADZUNA_APP_ID` and `ADZUNA_APP_KEY` | Credentials for the Adzuna API (free
  tier supports a limited number of requests per day【268901123310661†L17-L25】.  See
  the Adzuna documentation for details). |
| `FIREBASE_CREDENTIALS` | Path to your Firebase service account JSON file. |
| `TOP_COMPANIES` | Comma‑separated list of company names considered “top
  companies”; defaults to a list of FAANG and leading Indian IT firms. |

### Running from the command line

Run the scraper once, writing results to a CSV and to Firebase:

```bash
python main.py --days 7 --min-salary 80000 --limit 50 --output jobs.csv
```

This command scrapes the last 7 days of listings, filters out jobs with an
average salary below USD 80k, returns up to 50 jobs, writes them to
`jobs.csv` and pushes them into Firestore if credentials are provided.  Use
`--no-firebase` to skip Firebase writes.

### Running on a schedule

By default, the script schedules itself to run every 12 hours.  To enable
this behaviour run:

```bash
python main.py --schedule
```

The script will continue running in the foreground, scraping jobs twice
daily.  In production you might instead set up a cron job or a cloud
function that invokes the script (or just the `run_pipeline()` function)
every 12 hours.  Scheduling is intentionally lightweight so it can run on
free‑tier infrastructure.

### Using the Appify GUI

If `appify` is installed, you can launch a GUI by simply running:

```bash
python main.py
```

The interface allows you to specify the days, minimum salary and result
limit, then displays the scraped jobs in a sortable table.  The GUI uses
the same underlying pipeline as the CLI.

## Compliance and Ethics

* **Respect API terms**: Both Remote OK and Remotive require you to link
  back to the original job posting and credit them as the source【619872956787367†L0-L4】.
  This scraper always includes the `source` field in the resulting
  documents and you must display it along with the job URL in any UI or
  data feed you produce.  Please avoid excessive requests; for Remotive
  specifically, calls should be limited to a few times per day【537219484937451†L14-L19】.
* **Do not scrape restricted sites**: The script only accesses
  publicly‑available APIs whose terms permit redistribution with proper
  attribution.  Do not attempt to scrape job boards that prohibit
  automated access or require pay‑per‑use licensing.
* **Cost management**: All third‑party APIs used here offer a free tier.
  The code minimises requests by fetching just enough jobs (50 at most)
  twice per day, staying within free quotas.  Firebase’s free tier
  supports generous daily reads and writes, but monitor your usage and
  upgrade your plan if necessary.

## Project Structure

```
job_scraper_production/
├── main.py        # Entry point, orchestrates scraping, scheduling, CLI, and GUI.
├── sources/
│   ├── __init__.py
│   ├── remote_ok.py   # Fetches jobs from Remote OK
│   ├── remotive.py    # Fetches jobs from Remotive
│   └── adzuna.py      # Fetches jobs from Adzuna (requires credentials)
├── firebase.py    # Helper functions for Firebase integration
├── utils.py       # Shared data structures and filtering helpers
├── requirements.txt
└── README.md
```

Feel free to extend the `sources` package with additional job APIs.  Each
module must define a `fetch_jobs` function that returns a list of `Job`
objects defined in `utils.py`.

## Deploying to Appify

1. Ensure your repository is pushed to GitHub with all improvements.
2. On Appify, select "Deploy from GitHub Repository".
3. Set Environment Variables explicitly on Appify:
   - `ADZUNA_APP_ID`
   - `ADZUNA_APP_KEY`
   - `FIREBASE_CREDENTIALS`
   - `FIRESTORE_COLLECTION`
   - `TOP_COMPANIES`
4. Set Run Command to `python main.py`.
5. Deploy and manage your scraper GUI effortlessly.
