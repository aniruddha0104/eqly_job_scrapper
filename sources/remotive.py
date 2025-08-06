"""Fetch jobs from the Remotive public API.

The Remotive API returns a JSON object containing a list of job postings
under the ``jobs`` key.  A legal notice at the top of the response
requires that developers link back to the job and credit Remotive as
the source【537219484937451†L14-L19】.  The API supports a ``search`` query
parameter; however, Remotive warns that data is delayed by 24 hours and
recommends limiting requests to a few times per day【537219484937451†L14-L19】.

Fields extracted:
  * ``publication_date``: ISO 8601 timestamp with timezone.
  * ``company_name``
  * ``title``
  * ``candidate_required_location`` (location)
  * ``salary``: free‑form string, often containing currency and range.
  * ``url``: link to the job description.

Jobs lacking salary information are retained only if `min_salary` is zero.
"""

from __future__ import annotations

import datetime as _dt
import logging
import re
from typing import List, Optional

import requests

from ..utils import Job, is_recent, is_top_company


LOGGER = logging.getLogger(__name__)


REMOTIVE_API_URL = "https://remotive.com/api/remote-jobs"


def _parse_salary(salary_text: str) -> tuple[Optional[float], Optional[float]]:
    """Parse numeric salary bounds from a salary string.

    Remotive salaries may appear as "$100,000 – $150,000", "€60k",
    "100k-120k", or similar.  This helper extracts up to two numbers
    from the string and treats them as salary bounds.  Returns (min,
    max) in whatever units appear in the string; caller is responsible
    for currency conversion if needed.
    """
    # Extract numbers with optional commas and a trailing k (e.g. 100k)
    matches = re.findall(r"([0-9][0-9,]*\.?[0-9]*)k?", salary_text.lower())
    if not matches:
        return None, None
    nums: List[float] = []
    for m in matches:
        # Skip empty strings (can happen with ranges like "100k - 150k")
        if not m:
            continue
        value = float(m.replace(",", ""))
        # If 'k' was present in the original text after the number, multiply by 1,000
        if re.search(rf"{re.escape(m)}k", salary_text.lower()):
            value *= 1_000
        nums.append(value)
    if not nums:
        return None, None
    if len(nums) >= 2:
        return nums[0], nums[1]
    return None, nums[0]


def fetch_jobs(
    days: int = 7,
    min_salary: float = 0.0,
    top_companies: Optional[List[str]] = None,
    limit: int = 50,
    search: str = "",
) -> List[Job]:
    """Fetch recent jobs from the Remotive API.

    Args:
        days: Maximum age in days.
        min_salary: Minimum average salary required.  If 0, jobs without
            salary information are retained.
        top_companies: Optional list of company names to restrict results.
        limit: Maximum number of jobs to return.
        search: Optional search term to narrow jobs (e.g. "engineer").

    Returns:
        List of `Job` objects.
    """
    params = {}
    if search:
        params["search"] = search
    try:
        resp = requests.get(REMOTIVE_API_URL, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        items = data.get("jobs", [])
    except Exception as exc:
        LOGGER.error("Failed to fetch Remotive jobs: %s", exc)
        return []
    jobs: List[Job] = []
    for item in items:
        date_str = item.get("publication_date") or ""
        try:
            published = _dt.datetime.fromisoformat(date_str)
        except Exception:
            continue
        dummy_job = Job(
            title="",
            company="",
            location="",
            publication_date=published,
            salary_min=None,
            salary_max=None,
            currency=None,
            url="",
            source="Remotive",
        )
        if not is_recent(dummy_job, days):
            continue
        company = item.get("company_name", "N/A")
        if top_companies:
            dummy_job.company = company
            if not is_top_company(dummy_job, top_companies):
                continue
        salary_text = item.get("salary", "")
        salary_min, salary_max = _parse_salary(salary_text)
        avg_salary: Optional[float] = None
        if salary_min is not None and salary_max is not None:
            avg_salary = (salary_min + salary_max) / 2.0
        elif salary_max is not None:
            avg_salary = salary_max
        elif salary_min is not None:
            avg_salary = salary_min
        if avg_salary is None and min_salary > 0:
            # Skip if salary is unknown and threshold is set
            continue
        if avg_salary is not None and avg_salary < min_salary:
            continue
        location = item.get("candidate_required_location", "Remote")
        url = item.get("url", "")
        job = Job(
            title=item.get("title", ""),
            company=company,
            location=location,
            publication_date=published,
            salary_min=salary_min,
            salary_max=salary_max,
            currency=None,
            url=url,
            source="Remotive",
        )
        jobs.append(job)
    jobs.sort(key=lambda j: j.average_salary or 0.0, reverse=True)
    return jobs[:limit]