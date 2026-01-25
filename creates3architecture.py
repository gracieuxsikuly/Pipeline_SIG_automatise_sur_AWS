import boto3
import os
import logging
import json
from dotenv import load_dotenv
logging.basicConfig(level=logging.INFO)
load_dotenv()
#session aws pour connexion
session=boto3.Session(profile_name=os.getenv("AWS_PROFIL"),region_name=os.getenv("AWS_REGION"))
#boto3.client('s3')
s3=session.client('s3')

FOLDERS=[
    "raw/",
    "processed/",
    "outputs/",
    "outputs/geojson/",
    "outputs/carte/"
    ]
# je creer notre bucket et architecture ici
def creation_architecture():
    """Creates and configures the initial S3 bucket architecture for a data processing pipeline.
    This function performs the following actions:
    - Creates an S3 bucket if it does not already exist.
    - Enables bucket versioning to ensure data traceability and protection.
    - Applies a bucket policy that makes the `raw/` folder immutable:
        * deletion of objects and their versions is denied for all users,
        * except for a designated administrator identified by an IAM ARN.
    - Creates the logical folder structure (S3 prefixes) corresponding to the different
      stages of the data pipeline (`raw`, `processed`, `outputs`, etc.).
    This architecture follows data lake best practices, where the `raw` zone preserves
    original source data to guarantee integrity, auditability, and reproducibility
    of downstream processing.
    Raises:
        s3.exceptions.BucketAlreadyExists:
            If the bucket already exists in another AWS account.
    Logging:
        Logs key steps including bucket creation, versioning activation,
        policy application, and folder structure initialization.
    """
    try:
        # create bucket
        s3.create_bucket(Bucket=os.getenv("BUCKET_NAME"))
        logging.info("Bucket "+os.getenv("BUCKET_NAME")+ " est creer avec success")
        s3.put_bucket_versioning(
            Bucket=os.getenv("BUCKET_NAME"),
            VersioningConfiguration={"Status": "Enabled"}
        )
        logging.info("Versionning acitvate")
        ma_policy = {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Sid": "DenyDeleteOnRawExceptRoot",
                        "Effect": "Deny",
                        "Principal": "*",
                        "Action": [
                            "s3:DeleteObject",
                            "s3:DeleteObjectVersion"
                        ],
                        "Resource": f"arn:aws:s3:::{os.getenv('BUCKET_NAME')}/raw/*",
                        "Condition": {
                            "StringNotEquals": {
                                "aws:PrincipalArn": os.getenv("ARN_ROOT")
                            }
                        }
                    }
                ]
            }
        # Appliquer la policy sur le bucket
        s3.put_bucket_policy(
            Bucket=os.getenv("BUCKET_NAME"),           
            Policy=json.dumps(ma_policy) 
        )
        # create folders in bucket
        for folder in FOLDERS:
            s3.put_object(Bucket=os.getenv("BUCKET_NAME"),Key=folder)
        logging.info("folders created successfully")
    except s3.exceptions.BucketAlreadyExists as e:
        logging.warning(f"Error: {e.response['Error']['Code']}")
creation_architecture()
