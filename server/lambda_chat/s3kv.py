import json
import boto3
from botocore.exceptions import ClientError

class S3KeyValueStore:
    def __init__(self, bucket_name):
        print('Bucket name initialized: '+bucket_name)
        self.bucket_name = bucket_name
        self.s3 = boto3.client('s3')

    def object_exists(self, directory, key):
        object_key = f"{directory}/{key}"
        try:
            self.s3.head_object(Bucket=self.bucket_name, Key=object_key)
            return True
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                return False
            raise

    def put_value(self, directory, key, value):
        #print("PUT_VALUE:")
        #print(directory, key)
        object_key = f"{directory}/{key}"

        # Check if the object already exists
        if self.object_exists(directory, key):
            print(f"Object with key '{object_key}' already exists. Overwriting.")

        value_json_string = json.dumps(value)
        value_bytes = value_json_string.encode('utf-8')
        self.s3.put_object(Bucket=self.bucket_name, Key=object_key, Body=value_bytes)

    def get_value(self, directory, key):
        #print("GET_VALUE:")
        #print(directory, key)
        object_key = f"{directory}/{key}"

        # Check if the object exists
        if not self.object_exists(directory, key):
            print(f"Object with key '{object_key}' not found.")
            return None

        response = self.s3.get_object(Bucket=self.bucket_name, Key=object_key)
        value_json_string = response['Body'].read().decode('utf-8')
        value = json.loads(value_json_string)
        return value