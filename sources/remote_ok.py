"""Fetch jobs from the Remote OK public API.

Remote OK provides a public endpoint that returns a JSON array of job
postings.  The first element contains a legal notice requiring that
developers link back to the job’s URL and acknowledge Remote OK as the
source【619872956787367†L0-L4】.  Subsequent elements represent individual job
listings sorted by publication date.  We respect these terms by
including the `source` field in each `Job` instance and by requiring
callers to link to the original `url` when displaying results.

The API does not require authentication but should not be queried more
than a few times per day.  The function below filters the results by
publication date, salary and company before returning.
"""

from __future__ import annotations

import datetime as _dt
import logging
import re
from typing import List, Optional

import requests

from ..utils import Job, is_recent, is_top_company


LOGGER = logging.getLogger(__name__)


REMOTE_OK_API_URL = "https://remoteok.com/api"


def _parse_salary(salary_text: str) -> tuple[Optional[float], Optional[float]]:
    """Extract numeric salary bounds from a salary string.

    Remote OK often expresses salaries as a string like "$80,000 – $120,000".
    This helper returns a `(min, max)` tuple of floats, or `(None, None)` if
    no numbers are found.
    """
    matches = re.findall(r"\$([0-9,]+)", salary_text)
    if not matches:
        return None, None
    nums = [float(s.replace(",", "")) for s in matches]
    if len(nums) >= 2:
        return nums[0], nums[1]
    # Single number: treat as max
    return None, nums[0]


def fetch_jobs(
    days: int = 7,
    min_salary: float = 0.0,
    top_companies: Optional[List[str]] = None,
    limit: int = 50,
) -> List[Job]:
    """Fetch recent, high‑paying jobs from Remote OK.

    Args:
        days: Maximum age of the job posting in days.
        min_salary: Minimum average salary required to include a job.
        top_companies: Optional list of company names to prioritise.  If
            provided, only jobs whose company appears in this list (case
            insensitive) are returned.  If None or empty, all companies
            meeting the salary criterion are considered.
        limit: Maximum number of jobs to return.

    Returns:
        A list of `Job` objects sorted by descending average salary.
    """
    try:
        resp = requests.get(REMOTE_OK_API_URL, timeout=30, headers={"Accept": "application/json"})
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        LOGGER.error("Failed to fetch Remote OK jobs: %s", exc)
        return []
    # First entry is legal notice; skip it
    items = data[1:]
    jobs: List[Job] = []
    for item in items:
        try:
            date_str = item.get("date") or item.get("publication_date") or ""
            # Normalize ISO date (append timezone if missing)
            date_norm = date_str.replace("Z", "+00:00")
            published = _dt.datetime.fromisoformat(date_norm)
        except Exception:
            continue
        # Filter by recency
        dummy_job = Job(
            title="",
            company="",
            location="",
            publication_date=published,
            salary_min=None,
            salary_max=None,
            currency=None,
            url="",
            source="Remote OK",
        )
        if not is_recent(dummy_job, days):
            continue
        # Extract salary
        salary_min: Optional[float] = item.get("salary_min")
        salary_max: Optional[float] = item.get("salary_max")
        if salary_min is None and salary_max is None:
            salary_text = item.get("salary") or ""
            salary_min, salary_max = _parse_salary(salary_text)
        avg_salary: Optional[float] = None
        if salary_min is not None and salary_max is not None:
            avg_salary = (salary_min + salary_max) / 2.0
        elif salary_max is not None:
            avg_salary = salary_max
        elif salary_min is not None:
            avg_salary = salary_min
        # Filter by salary threshold
        if avg_salary is None or avg_salary < min_salary:
            continue
        company = item.get("company", "N/A")
        # Filter by top companies if provided
        if top_companies:
            dummy_job.company = company
            if not is_top_company(dummy_job, top_companies):
                continue
        # Build Job object
        job = Job(
            title=item.get("position", ""),
            company=company,
            location=item.get("location", "Remote"),
            publication_date=published,
            salary_min=salary_min,
            salary_max=salary_max,
            currency="USD",  # Remote OK salaries are typically in USD
            url=item.get("url", ""),
            source="Remote OK",
        )
        jobs.append(job)
    # Sort by average salary descending
    jobs.sort(key=lambda j: j.average_salary or 0.0, reverse=True)
    return jobs[:limit]