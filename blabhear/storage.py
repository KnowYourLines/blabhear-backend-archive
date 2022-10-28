import os

from google.cloud import storage
from google.oauth2 import service_account

gcp_storage_credentials = {
    "type": "service_account",
    "project_id": os.environ.get("GCP_STORAGE_PROJECT_ID"),
    "private_key_id": os.environ.get("GCP_STORAGE_PRIVATE_KEY_ID"),
    "private_key": os.environ.get("GCP_STORAGE_PRIVATE_KEY").replace("\\n", "\n"),
    "client_email": os.environ.get("GCP_STORAGE_CLIENT_EMAIL"),
    "client_id": os.environ.get("GCP_STORAGE_CLIENT_ID"),
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://accounts.google.com/o/oauth2/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_x509_cert_url": os.environ.get("GCP_STORAGE_CLIENT_CERT_URL"),
}

credentials = service_account.Credentials.from_service_account_info(
    gcp_storage_credentials
)
storage_client = storage.Client(
    project=gcp_storage_credentials["project_id"], credentials=credentials
)


def generate_upload_signed_url_v4(blob_name):
    bucket = storage_client.bucket(os.environ.get("GCP_STORAGE_BUCKET"))
    blob = bucket.blob(blob_name)

    url = blob.generate_signed_url(
        version="v4",
        method="PUT",
        content_type="application/ogg",
    )
    return url


def generate_download_signed_url_v4(blob_name):
    bucket = storage_client.bucket(os.environ.get("GCP_STORAGE_BUCKET"))
    blob = bucket.blob(blob_name)

    url = blob.generate_signed_url(
        version="v4",
        expiration=None,
        method="GET",
    )
    return url
