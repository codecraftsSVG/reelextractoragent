import os
import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()

# Oracle Cloud Object Storage S3-Compatible Configuration for Namespace: axsjpohxau7f (Region: HYD / ap-hyderabad-1)
OCI_ENDPOINT_URL = os.getenv(
    "OCI_ENDPOINT_URL",
    "https://axsjpohxau7f.compat.objectstorage.ap-hyderabad-1.oraclecloud.com"
)
OCI_ACCESS_KEY_ID = os.getenv("OCI_ACCESS_KEY_ID")
OCI_SECRET_ACCESS_KEY = os.getenv("OCI_SECRET_ACCESS_KEY")
OCI_BUCKET_NAME = os.getenv("OCI_BUCKET_NAME", "reel-extractor-bucket")
OCI_REGION = os.getenv("OCI_REGION", "ap-hyderabad-1")


def get_oci_s3_client():
    if not OCI_ACCESS_KEY_ID or not OCI_SECRET_ACCESS_KEY:
        raise ValueError(
            "OCI S3 Customer Secret Keys are not configured in environment variables "
            "(OCI_ACCESS_KEY_ID, OCI_SECRET_ACCESS_KEY)"
        )
    
    session = boto3.session.Session()
    return session.client(
        's3',
        endpoint_url=OCI_ENDPOINT_URL,
        aws_access_key_id=OCI_ACCESS_KEY_ID,
        aws_secret_access_key=OCI_SECRET_ACCESS_KEY,
        region_name=OCI_REGION
    )


def upload_file_to_oci(file_path: str, object_name: str = None) -> str:
    """Uploads a file (e.g. extracted reel video or analysis JSON) to Oracle Cloud Object Storage."""
    if object_name is None:
        object_name = os.path.basename(file_path)

    s3 = get_oci_s3_client()
    try:
        s3.upload_file(file_path, OCI_BUCKET_NAME, object_name)
        print(f"Successfully uploaded {file_path} to OCI bucket {OCI_BUCKET_NAME} as {object_name}")
        return f"oci://{OCI_BUCKET_NAME}/{object_name}"
    except ClientError as e:
        print(f"Error uploading to OCI: {e}")
        raise e


def download_file_from_oci(object_name: str, download_path: str) -> str:
    """Downloads a file from OCI Object Storage."""
    s3 = get_oci_s3_client()
    try:
        s3.download_file(OCI_BUCKET_NAME, object_name, download_path)
        print(f"Successfully downloaded {object_name} from OCI bucket {OCI_BUCKET_NAME} to {download_path}")
        return download_path
    except ClientError as e:
        print(f"Error downloading from OCI: {e}")
        raise e


