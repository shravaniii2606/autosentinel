"""Google Earth Engine authentication for AutoSentinel.

Headless service-account setup:
1. Open the GCP console for the `ee-autosentinel` project.
2. Go to IAM & Admin > Service Accounts > Create service account.
3. Grant the service account the `Earth Engine Resource Viewer` role. Depending
   on project configuration, GEE may also require `Service Usage Consumer`.
4. Ensure the Earth Engine API is enabled and the Cloud project is registered
   for Earth Engine access. If prompted, register the service account at:
   https://signup.earthengine.google.com/#!/service_accounts
5. Create a JSON key for the service account, download it, and set the whole
   JSON document as the single-line `GEE_SERVICE_ACCOUNT_KEY` env var.

Never commit the downloaded JSON key or paste real key material into
`.env.example`.
"""

import os
import threading

GEE_PROJECT = "ee-autosentinel"
SERVICE_ACCOUNT_EMAIL_ENV = "GEE_SERVICE_ACCOUNT_EMAIL"
SERVICE_ACCOUNT_KEY_ENV = "GEE_SERVICE_ACCOUNT_KEY"

_init_lock = threading.Lock()
_initialized = False


def init_earth_engine():
    """Initialize Earth Engine once, preferring service-account auth.

    Returns the imported `ee` module so callers can use it if convenient.
    """
    global _initialized

    if _initialized:
        import ee

        return ee

    with _init_lock:
        if _initialized:
            import ee

            return ee

        import ee

        service_account_email = os.getenv(SERVICE_ACCOUNT_EMAIL_ENV, "").strip()
        service_account_key = os.getenv(SERVICE_ACCOUNT_KEY_ENV, "").strip()
        has_email = bool(service_account_email)
        has_key = bool(service_account_key)

        try:
            if has_email and has_key:
                credentials = ee.ServiceAccountCredentials(
                    service_account_email,
                    key_data=service_account_key,
                )
                ee.Initialize(credentials, project=GEE_PROJECT)
            elif has_email or has_key:
                missing = (
                    SERVICE_ACCOUNT_KEY_ENV
                    if has_email
                    else SERVICE_ACCOUNT_EMAIL_ENV
                )
                raise RuntimeError(
                    "Earth Engine service-account auth is partially configured. "
                    f"Set `{missing}` too, or remove both "
                    f"`{SERVICE_ACCOUNT_EMAIL_ENV}` and `{SERVICE_ACCOUNT_KEY_ENV}` "
                    "to use local personal OAuth."
                )
            else:
                ee.Initialize(project=GEE_PROJECT)
        except Exception as exc:
            mode = (
                "service-account environment variables"
                if has_email or has_key
                else "local personal OAuth"
            )
            raise RuntimeError(
                f"Failed to initialize Google Earth Engine for project "
                f"`{GEE_PROJECT}` using {mode}. "
                f"For deploys, set `{SERVICE_ACCOUNT_EMAIL_ENV}` to the service "
                f"account email and `{SERVICE_ACCOUNT_KEY_ENV}` to the complete "
                "single-line JSON key. Confirm the account has the Earth Engine "
                "Resource Viewer role, the Earth Engine API is enabled, and the "
                "project/service account is registered for Earth Engine access. "
                "For local OAuth fallback, unset both service-account env vars "
                f"and run `earthengine authenticate`. Original error: {exc}"
            ) from exc

        _initialized = True
        return ee
