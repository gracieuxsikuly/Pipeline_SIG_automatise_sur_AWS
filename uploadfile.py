import boto3
import os
import logging
import json
from dotenv import load_dotenv
logging.basicConfig(level=logging.INFO)
load_dotenv()
session=boto3.Session(profile_name=os.getenv("AWS_PROFIL"),region_name=os.getenv("AWS_REGION"))
s3=session.client('s3')