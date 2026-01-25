import boto3
import os
import logging
from dotenv import load_dotenv
import shutil  # pour déplacer les fichiers

logging.basicConfig(level=logging.INFO)
load_dotenv()

session = boto3.Session(
    profile_name=os.getenv("AWS_PROFIL"),
    region_name=os.getenv("AWS_REGION")
)
s3 = session.client('s3')
LOCAL_DIR = "data"
UPLOADED_DIR = os.path.join(LOCAL_DIR, "uploaded")
os.makedirs(UPLOADED_DIR, exist_ok=True) 
BUCKET_NAME = os.getenv("BUCKET_NAME")
def upload_fichier():
    """
    Uploads files from the local directory to the 'raw/' folder in S3.
    - Files already uploaded (moved to 'uploaded/' folder) are skipped.
    - After uploading, the local file is moved to the 'uploaded/' folder.
    """
    for filename in os.listdir(LOCAL_DIR):
        local_file = os.path.join(LOCAL_DIR, filename)
        # skip if not a file
        if not os.path.isfile(local_file):
            continue
        # skip files already in the uploaded folder
        if filename in os.listdir(UPLOADED_DIR):
            logging.info(f"Skipping already uploaded file: {filename}")
            continue
        # target S3 key
        s3_key = f"raw/{filename}"
        # check if the file already exists on S3
        try:
            s3.head_object(Bucket=BUCKET_NAME, Key=s3_key)
            logging.info(f"File already exists on S3, skipping: {filename}")
            continue
        except s3.exceptions.ClientError as e:
            if e.response['Error']['Code'] != "404":
                logging.error(f"Error checking S3 object {s3_key}: {e}")
                continue
            # object does not exist → upload
        # upload the file
        s3.upload_file(local_file, BUCKET_NAME, s3_key)
        logging.info(f"Uploaded: s3://{BUCKET_NAME}/{s3_key}")
        # move file to uploaded folder
        shutil.move(local_file, os.path.join(UPLOADED_DIR, filename))
        logging.info(f"Moved file to uploaded folder: {filename}")
# lancer la fonction
upload_fichier()
