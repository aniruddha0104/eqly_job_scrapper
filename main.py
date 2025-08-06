"""Entry point for the job scraper.

This script orchestrates fetching jobs from multiple sources, filtering
them by recency, salary and company, writing results to a CSV file and
Firestore, and providing both a CLI and an optional GUI via Appify.  It
is designed to run on a schedule (default every 12 hours) or be
invoked on demand.  The configuration is primarily driven by
environment variables so that you can deploy it flexibly.

Run `python main.py --help` for CLI usage.
"""

from __future__ import annotations

import argparse
import csv
import datetime as _dt
import logging
import os
import signal
import sys
from typing import List, Optional

import schedule
import time

from dotenv import load_dotenv
load_dotenv()

# Allow running as a script by adjusting sys.path for relative imports
if __package__ is None or __package__ == "":
    import os as _os
    import sys as _sys
    parent_dir = _os.path.dirname(_os.path.abspath(__file__))
    _sys.path.append(parent_dir)
    __package__ = "job_scraper_production"
from .firebase import init_firebase, upsert_jobs
from .sources import (
    fetch_adzuna_jobs,
    fetch_remote_ok_jobs,
    fetch_remotive_jobs,
)
from .utils import Job, to_local_date_str


LOGGER = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")



def load_top_companies(env_var: str = "TOP_COMPANIES") -> List[str]:
    value = os.environ.get(env_var)
    if not value:
        return DEFAULT_TOP_COMPANIES
    return [c.strip() for c in value.split(",") if c.strip()]


def scrape_jobs(
    days: int,
    min_salary: float,
    limit: int,
    top_companies: Optional[List[str]] = None,
    sources: Optional[List[str]] = None,
    search: str = "",
) -> List[Job]:
    """Fetch and aggregate jobs from multiple sources.

    Args:
        days: Number of days to look back when filtering jobs.
        min_salary: Minimum salary threshold.
        limit: Maximum number of jobs to return (across all sources).
        top_companies: List of top company names to prioritise (case‑insensitive).
        sources: Optional list specifying which sources to include.  Valid
            values are 'remoteok', 'remotive', 'adzuna'.  If None, all
            available sources are used.
        search: Optional search term to pass to sources that support it.

    Returns:
        A list of jobs sorted by descending average salary.
    """
    if top_companies is None:
        top_companies = load_top_companies()
    if sources is None or not sources:
        sources = ["remoteok", "remotive", "adzuna"]
    jobs: List[Job] = []
    if "remoteok" in sources:
        jobs += fetch_remote_ok_jobs(days=days, min_salary=min_salary, top_companies=top_companies, limit=limit)
    if "remotive" in sources:
        jobs += fetch_remotive_jobs(days=days, min_salary=min_salary, top_companies=top_companies, limit=limit, search=search)
    if "adzuna" in sources:
        jobs += fetch_adzuna_jobs(days=days, min_salary=min_salary, top_companies=top_companies, limit=limit, countries=None, what=search, where=None)
    # Deduplicate by job URL
    seen = set()
    unique_jobs: List[Job] = []
    for job in jobs:
        if not job.url or job.url in seen:
            continue
        seen.add(job.url)
        unique_jobs.append(job)
    # Sort by average salary descending; fallback to recency if salary is missing
    unique_jobs.sort(key=lambda j: (j.average_salary or 0.0, j.publication_date), reverse=True)
    return unique_jobs[:limit]


def save_jobs_to_csv(jobs: List[Job], path: str) -> None:
    """Write jobs to a CSV file in a human‑readable format."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "title",
            "company",
            "location",
            "publication_date",
            "salary_min",
            "salary_max",
            "currency",
            "average_salary",
            "url",
            "source",
        ])
        for job in jobs:
            writer.writerow([
                job.title,
                job.company,
                job.location,
                to_local_date_str(job.publication_date),
                job.salary_min,
                job.salary_max,
                job.currency,
                job.average_salary,
                job.url,
                job.source,
            ])


def run_pipeline(
    days: int,
    min_salary: float,
    limit: int,
    top_companies: Optional[List[str]],
    output_path: str,
    push_firebase: bool,
    sources: Optional[List[str]],
    search: str,
) -> None:
    """Execute the scraping workflow: fetch, save locally, push to Firebase."""
    LOGGER.info(
        "Running job scraping pipeline (days=%d, min_salary=%s, limit=%d) with sources=%s",
        days,
        min_salary,
        limit,
        sources,
    )
    jobs = scrape_jobs(days=days, min_salary=min_salary, limit=limit, top_companies=top_companies, sources=sources, search=search)
    LOGGER.info("Fetched %d jobs", len(jobs))
    if output_path:
        save_jobs_to_csv(jobs, output_path)
        LOGGER.info("Saved jobs to %s", output_path)
    if push_firebase:
        client = init_firebase()
        if client:
            inserted = upsert_jobs(jobs, collection=os.environ.get("FIRESTORE_COLLECTION", "jobs"), client=client)
            LOGGER.info("Upserted %d jobs into Firebase", inserted)


def schedule_pipeline(
    interval_hours: int,
    **kwargs,
) -> None:
    """Schedule the pipeline to run at a fixed hourly interval."""
    def job_wrapper():
        try:
            run_pipeline(**kwargs)
        except Exception as exc:
            LOGGER.exception("Error during scheduled scraping: %s", exc)
    schedule.every(interval_hours).hours.do(job_wrapper)
    LOGGER.info("Scheduled pipeline every %d hours", interval_hours)
    # Keep the scheduler running until interrupted
    def handle_exit(signum, frame):
        LOGGER.info("Received signal %s, shutting down scheduler", signum)
        sys.exit(0)
    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)
    while True:
        schedule.run_pending()
        # Sleep for a minute between checks
        time.sleep(60)


def main_cli(argv: Optional[List[str]] = None) -> None:
    """Parse CLI arguments and run the scraper accordingly."""
    parser = argparse.ArgumentParser(description="Scrape jobs from multiple sources and optionally push to Firebase.")
    parser.add_argument("--days", type=int, default=7, help="Max age of job postings in days")
    parser.add_argument("--min-salary", type=float, default=0.0, help="Minimum average salary (in the job's currency)")
    parser.add_argument("--limit", type=int, default=50, help="Maximum number of jobs to return")
    parser.add_argument("--output", type=str, default="jobs.csv", help="CSV file to save results")
    parser.add_argument("--no-firebase", action="store_true", help="Do not push results to Firebase")
    parser.add_argument("--sources", type=str, nargs="*", choices=["remoteok", "remotive", "adzuna"], help="Which sources to include (default: all)")
    parser.add_argument("--top-companies", type=str, help="Comma‑separated list of top companies to filter on")
    parser.add_argument("--search", type=str, default="", help="Search term to pass to APIs that support it")
    parser.add_argument("--schedule", action="store_true", help="Run on a schedule (every 12 hours)")
    parser.add_argument("--interval-hours", type=int, default=12, help="Interval in hours for scheduled runs")
    args = parser.parse_args(argv)
    top_companies = None
    if args.top_companies:
        top_companies = [c.strip() for c in args.top_companies.split(",") if c.strip()]
    push_firebase = not args.no_firebase
    kwargs = {
        "days": args.days,
        "min_salary": args.min_salary,
        "limit": args.limit,
        "top_companies": top_companies,
        "output_path": args.output,
        "push_firebase": push_firebase,
        "sources": args.sources,
        "search": args.search,
    }
    if args.schedule:
        schedule_pipeline(args.interval_hours, **kwargs)
    else:
        run_pipeline(**kwargs)


# Appify integration: define a GUI function only if appify is available.
def _run_app(days: int = 7, min_salary: float = 0.0, limit: int = 50, search: str = "") -> List[dict]:  # pragma: no cover
    """Appify callback to return a list of job dictionaries for the UI.

    Note: This function will be registered with Appify if the library is
    available.  It returns a list of dictionaries with simple scalar
    values so that Appify can render them as a table.
    """
    jobs = scrape_jobs(days=days, min_salary=min_salary, limit=limit, search=search, top_companies=None, sources=None)
    rows = []
    for job in jobs:
        rows.append({
            "Title": job.title,
            "Company": job.company,
            "Location": job.location,
            "Posted": to_local_date_str(job.publication_date),
            "Min Salary": job.salary_min,
            "Max Salary": job.salary_max,
            "Avg Salary": job.average_salary,
            "Currency": job.currency,
            "Source": job.source,
            "URL": job.url,
        })
    return rows


def _register_appify() -> None:  # pragma: no cover
    """Register the Appify GUI if available."""
    try:
        from appify import appify  # type: ignore
    except ImportError:
        return
    # Create a simple interface where the user can input parameters
    @appify.app()
    def app() -> List[dict]:  # type: ignore
        """Job Scraper App"""
        return _run_app()  # type: ignore


if __name__ == "__main__":  # pragma: no cover
    # Register Appify if available
    _register_appify()
    # If appify is not used, run CLI
    main_cli()