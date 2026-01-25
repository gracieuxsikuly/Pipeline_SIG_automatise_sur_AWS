import os
import json
import hashlib
import boto3
import logging
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)
LOCAL_DIR = "data"
MANIFEST_FILE = "data/uploaded_manifest.json"
BUCKET = os.getenv("BUCKET_NAME")
S3_PREFIX = "raw/"

session=boto3.Session(profile_name=os.getenv("AWS_PROFIL"),region_name=os.getenv("AWS_REGION"))
s3 = session.client('s3')


def file_hash(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

if os.path.exists(MANIFEST_FILE):
    with open(MANIFEST_FILE) as f:
        manifest = json.load(f)

else:
    manifest = {}
    
for filename in os.listdir(LOCAL_DIR):
    filepath = os.path.join(LOCAL_DIR, filename)
    if not os.path.isfile(filepath) or filename == os.path.basename(MANIFEST_FILE):
        continue
    h = file_hash(filepath)
    if h in manifest.values():
        continue

    try:
        s3.upload_file(filepath, BUCKET, S3_PREFIX + filename)
        manifest[filename] = h
       
        logging.info(f"Uploaded {filename}")
    except ClientError as e:
        logging.error(f"Error uploading {filename}: {e}")
        raise

with open(MANIFEST_FILE, "w") as f:
    json.dump(manifest, f, indent=2)