"""Firebase integration for the job scraper.

This module encapsulates all interactions with Google Firebase.  It uses
the official `firebase_admin` library to initialise an application
context and write job documents into a Firestore collection.  Firestore
is chosen because it offers a flexible schema and generous free tier
limits.  The functions in this module will no‑op if credentials are
missing or if the `firebase_admin` package is not available.

Usage:

```python
from firebase import init_firebase, upsert_jobs

app = init_firebase()  # Provide credentials via env var or call signature
if app:
    upsert_jobs(jobs, collection="job_listings")
```
"""

from __future__ import annotations

import logging
import os
from typing import Iterable, Optional

from google.auth.exceptions import DefaultCredentialsError  # type: ignore
from google.cloud.firestore import Client  # type: ignore

from .utils import Job

try:
    import firebase_admin
    from firebase_admin import credentials, firestore
except ImportError:  # pragma: no cover
    firebase_admin = None  # type: ignore


LOGGER = logging.getLogger(__name__)


def init_firebase(credential_path: Optional[str] = None) -> Optional[firestore.Client]:
    """Initialise Firebase using a service account JSON key.

    Firebase Admin SDK requires a service account JSON file.  You can
    supply the path explicitly or set the ``FIREBASE_CREDENTIALS``
    environment variable.  If no path is provided and the environment
    variable is unset, the function attempts to initialise the app
    using Application Default Credentials.  Returns ``None`` if
    `firebase_admin` is not installed or credentials could not be
    loaded.

    Args:
        credential_path: Optional path to the service account JSON file.

    Returns:
        A Firestore client if initialisation succeeds, otherwise ``None``.
    """
    if firebase_admin is None:
        LOGGER.warning("firebase_admin is not installed; Firebase features disabled")
        return None
    # Only initialise once
    if firebase_admin._apps:
        return firestore.client()
    # Determine credential file
    path = credential_path or os.environ.get("FIREBASE_CREDENTIALS")
    try:
        if path:
            cred = credentials.Certificate(path)
            firebase_admin.initialize_app(cred)
        else:
            # Use default credentials (e.g. running in Google Cloud)
            firebase_admin.initialize_app()
        return firestore.client()
    except (FileNotFoundError, DefaultCredentialsError, ValueError) as exc:
        LOGGER.error("Failed to initialise Firebase: %s", exc)
        return None


def upsert_jobs_batch(
    jobs: Iterable[Job],
    collection: str = "jobs",
    client: Optional[firestore.Client] = None,
    batch_size: int = 400
) -> int:
    """Batch write jobs to Firestore for improved efficiency."""
    if client is None:
        client = firestore.client()

    batch = client.batch()
    count, total = 0, 0

    for job in jobs:
        if not job.url:
            continue
        doc_id = job.url.replace("/", "_").replace(":", "_")
        data = {
            "title": job.title,
            "company": job.company,
            "location": job.location,
            "publication_date": job.publication_date.isoformat(),
            "salary_min": job.salary_min,
            "salary_max": job.salary_max,
            "currency": job.currency,
            "average_salary": job.average_salary,
            "url": job.url,
            "source": job.source,
            "logo": job.logo if hasattr(job, 'logo') else "",
        }
        doc_ref = client.collection(collection).document(doc_id)
        batch.set(doc_ref, data)
        count += 1
        total += 1

        if count >= batch_size:
            batch.commit()
            LOGGER.info("Committed %d jobs to Firestore.", count)
            batch = client.batch()
            count = 0

    if count > 0:
        batch.commit()
        LOGGER.info("Final commit: %d jobs.", count)

    return total