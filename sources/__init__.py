"""Job source modules.

This package contains individual modules for each job API or website you
wish to scrape.  Each module exposes a single function:

```
def fetch_jobs(days: int, min_salary: float, top_companies: List[str], limit: int) -> List[Job]:
    ...
```

The function should return a list of `Job` objects defined in
`job_scraper_production.utils`.  It should handle its own API errors and
network issues gracefully, returning an empty list on failure.

To add a new source, create a new module in this directory and ensure
that its `fetch_jobs` function is imported in this package’s
`__all__` list.
"""

from .remote_ok import fetch_jobs as fetch_remote_ok_jobs  # noqa: F401
from .remotive import fetch_jobs as fetch_remotive_jobs  # noqa: F401
from .adzuna import fetch_jobs as fetch_adzuna_jobs  # noqa: F401

__all__ = [
    "fetch_remote_ok_jobs",
    "fetch_remotive_jobs",
    "fetch_adzuna_jobs",
]