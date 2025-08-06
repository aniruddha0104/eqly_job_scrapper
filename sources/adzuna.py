"""Fetch jobs from the Adzuna Jobs API.

Adzuna exposes a RESTful API for job advertisements.  To use this module
you must supply an ``app_id`` and ``app_key`` via environment
variables or function arguments.  Each request must specify a country
code (e.g. ``gb`` for the UK, ``us`` for the US, ``in`` for India) and
an endpoint page number; we always fetch page 1 and limit the number
of results via ``results_per_page``.  Example call:

```
https://api.adzuna.com/v1/api/jobs/gb/search/1?app_id=XXX&app_key=YYY&results_per_page=20&sort_by=salary&salary_min=50000
```

Query parameters of interest:

* ``results_per_page``: number of job ads per page【268901123310661†L17-L25】.
* ``what``: search keywords; you may use spaces or %20.
* ``where``: location filter; optional.
* ``sort_by``: sort criterion (e.g. "salary", "date").
* ``salary_min``: minimum salary to filter on【268901123310661†L73-L85】.

See the Adzuna API documentation for more options.  This module only
supports simple filtering and does not implement pagination beyond the
first page.
"""

from __future__ import annotations

import datetime as _dt
import logging
import os
from typing import List, Optional

import requests

from ..utils import Job, is_recent, is_top_company


LOGGER = logging.getLogger(__name__)


ADZUNA_API_BASE = "https://api.adzuna.com/v1/api/jobs"


def _get_credentials() -> tuple[Optional[str], Optional[str]]:
    """Return (app_id, app_key) from environment variables.

    If either is missing, logs a warning and returns (None, None).
    """
    app_id = os.environ.get("ADZUNA_APP_ID")
    app_key = os.environ.get("ADZUNA_APP_KEY")
    if not app_id or not app_key:
        LOGGER.warning(
            "Adzuna credentials are not set. Set ADZUNA_APP_ID and ADZUNA_APP_KEY to enable Adzuna scraping."
        )
        return None, None
    return app_id, app_key


def fetch_jobs(
    days: int = 7,
    min_salary: float = 0.0,
    top_companies: Optional[List[str]] = None,
    limit: int = 50,
    countries: Optional[List[str]] = None,
    what: str = "",
    where: Optional[str] = None,
) -> List[Job]:
    """Fetch jobs from Adzuna across one or more countries.

    Args:
        days: Maximum age in days.  Jobs older than this are skipped.
        min_salary: Minimum average salary required (in the job’s currency);
            if zero, jobs with unknown salary are retained.
        top_companies: Optional list of company names to restrict results.
        limit: Total maximum number of jobs to return across all countries.
        countries: List of country codes (lowercase, e.g. ["us", "in"]).
            Defaults to ["us", "gb", "in"] to cover major markets.
        what: Search keywords to narrow results (e.g. "software engineer").
        where: Optional location string to include jobs only from a specific
            city or region.

    Returns:
        List of `Job` objects.
    """
    app_id, app_key = _get_credentials()
    if not app_id or not app_key:
        return []
    if countries is None:
        countries = ["us", "gb", "in"]
    results: List[Job] = []
    for country in countries:
        endpoint = f"{ADZUNA_API_BASE}/{country}/search/1"
        params = {
            "app_id": app_id,
            "app_key": app_key,
            "results_per_page": min(limit, 50),  # Adzuna max is 50 per page
            "content-type": "application/json",
            # sort by salary descending to find high-paying roles
            "sort_by": "salary",
        }
        if what:
            params["what"] = what
        if where:
            params["where"] = where
        # Adzuna accepts salary_min only if we specify currency; leave as min_salary for filter
        if min_salary > 0:
            params["salary_min"] = int(min_salary)
        try:
            resp = requests.get(endpoint, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            items = data.get("results", [])
        except Exception as exc:
            LOGGER.error("Error fetching Adzuna jobs for %s: %s", country, exc)
            continue
        for item in items:
            # Parse publication date; Adzuna uses 'created' in ISO format
            date_str = item.get("created") or ""
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
                source="Adzuna",
            )
            if not is_recent(dummy_job, days):
                continue
            # Company filter
            company = item.get("company", {}).get("display_name", "N/A")
            if top_companies:
                dummy_job.company = company
                if not is_top_company(dummy_job, top_companies):
                    continue
            # Salaries in Adzuna are numeric and may be missing
            salary_min_val = item.get("salary_min")
            salary_max_val = item.get("salary_max")
            avg_salary: Optional[float] = None
            if salary_min_val is not None and salary_max_val is not None:
                avg_salary = (salary_min_val + salary_max_val) / 2.0
            elif salary_max_val is not None:
                avg_salary = float(salary_max_val)
            elif salary_min_val is not None:
                avg_salary = float(salary_min_val)
            if avg_salary is None and min_salary > 0:
                continue
            if avg_salary is not None and avg_salary < min_salary:
                continue
            location = item.get("location", {}).get("display_name", "")
            url = item.get("redirect_url", "")
            currency = item.get("salary_currency")
            job = Job(
                title=item.get("title", ""),
                company=company,
                location=location,
                publication_date=published,
                salary_min=float(salary_min_val) if salary_min_val is not None else None,
                salary_max=float(salary_max_val) if salary_max_val is not None else None,
                currency=currency,
                url=url,
                source="Adzuna",
            )
            results.append(job)
    results.sort(key=lambda j: j.average_salary or 0.0, reverse=True)
    return results[:limit]