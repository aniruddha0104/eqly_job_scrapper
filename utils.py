"""Utility classes and functions for the job scraper.

This module centralises shared data structures, type hints and filtering
logic.  It defines a `Job` data class that serves as a common schema for
all job sources, as well as helper functions for computing average salary
and determining whether a job originates from a “top company”.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from typing import List, Optional

from tzlocal import get_localzone


@dataclass
class Job:
    """Represents a normalised job listing.

    Attributes:
        title: Human‑readable job title.
        company: Name of the hiring company.
        location: Location string (may be "Remote" or city/country).
        publication_date: UTC timestamp when the job was posted (aware
            datetime).  Each source should convert its dates into a
            timezone‑aware datetime before populating this field.
        salary_min: Minimum annual salary in USD if available.
        salary_max: Maximum annual salary in USD if available.
        currency: ISO currency code for salary (e.g. "USD", "INR").
        url: URL to the full job description.  Must link to the original
            posting on the source’s domain.
        source: The API/source used to fetch this job (e.g. "Remote OK").
    """

    title: str
    company: str
    location: str
    publication_date: _dt.datetime
    salary_min: Optional[float]
    salary_max: Optional[float]
    currency: Optional[str]
    url: str
    source: str

    @property
    def average_salary(self) -> Optional[float]:
        """Compute the average of salary_min and salary_max.

        Returns:
            The average salary if at least one salary bound is present,
            otherwise ``None``.  Salaries are assumed to be annual and in
            USD.  If currency conversions are required, convert before
            populating salary_min/max.
        """
        if self.salary_min is not None and self.salary_max is not None:
            return (self.salary_min + self.salary_max) / 2.0
        return self.salary_max or self.salary_min


def is_recent(job: Job, days: int) -> bool:
    """Return True if the job was published within the past ``days`` days.

    Args:
        job: The job listing to evaluate.
        days: The maximum age of the job in days.

    Returns:
        True if the job’s `publication_date` is within the last ``days``
        relative to the current time in the local timezone.
    """
    now = _dt.datetime.now(_dt.timezone.utc)
    cutoff = now - _dt.timedelta(days=days)
    return job.publication_date >= cutoff


def is_top_company(job: Job, top_companies: List[str]) -> bool:
    """Return True if the job’s company is in the list of top companies.

    Case‑insensitive comparison is performed.  Partial matches are allowed,
    so "Google" will match "Google LLC".  If `top_companies` is empty,
    returns False.
    """
    if not top_companies:
        return False
    company_lower = job.company.lower()
    return any(tc.strip().lower() in company_lower for tc in top_companies)


def to_local_date_str(dt_obj: _dt.datetime) -> str:
    """Convert an aware datetime to a local date string in ISO format.

    Useful for presenting dates in the UI.  The local timezone is
    determined by tzlocal.get_localzone().
    """
    local_tz = get_localzone()  # type: ignore
    return dt_obj.astimezone(local_tz).strftime("%Y-%m-%d %H:%M")