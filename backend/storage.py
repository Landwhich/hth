import os
import boto3
from dotenv import load_dotenv

load_dotenv()

DO_SPACES_KEY = os.getenv("DO_SPACES_KEY")
DO_SPACES_SECRET = os.getenv("DO_SPACES_SECRET")
DO_SPACES_ENDPOINT_URL = os.getenv("DO_SPACES_ENDPOINT_URL") # e.g. https://nyc3.digitaloceanspaces.com
DO_SPACES_REGION_NAME = os.getenv("DO_SPACES_REGION_NAME", "nyc3")
DO_SPACES_BUCKET_NAME = os.getenv("DO_SPACES_BUCKET_NAME")

def get_s3_client():
    session = boto3.session.Session()
    client = session.client('s3',
                            region_name=DO_SPACES_REGION_NAME,
                            endpoint_url=DO_SPACES_ENDPOINT_URL,
                            aws_access_key_id=DO_SPACES_KEY,
                            aws_secret_access_key=DO_SPACES_SECRET)
    return client

def upload_file_to_spaces(file_obj, object_name, content_type):
    if not all([DO_SPACES_KEY, DO_SPACES_SECRET, DO_SPACES_ENDPOINT_URL, DO_SPACES_BUCKET_NAME]):
        raise ValueError("DigitalOcean Spaces credentials are not fully configured in .env")

    client = get_s3_client()
    client.upload_fileobj(
        file_obj,
        DO_SPACES_BUCKET_NAME,
        object_name,
        ExtraArgs={
            "ACL": "public-read",
            "ContentType": content_type
        }
    )
    
    # Construct the public URL. E.g., https://nyc3.digitaloceanspaces.com -> https://my-bucket.nyc3.digitaloceanspaces.com/filename.jpg
    # Handle the URL formatting so the bucket name is prepended to the host
    url_parts = DO_SPACES_ENDPOINT_URL.split("://")
    protocol = url_parts[0]
    domain = url_parts[1]
    
    public_url = f"{protocol}://{DO_SPACES_BUCKET_NAME}.{domain}/{object_name}"
    return public_url
