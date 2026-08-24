"""
Test AWS Credentials and S3 Access
This script verifies your AWS credentials and S3 bucket access.
"""
import os
from dotenv import load_dotenv
from pathlib import Path

# Load environment variables
env_path = Path(__file__).parent / '.env'
load_dotenv(dotenv_path=env_path)

def test_aws_credentials():
    print("=" * 60)
    print("AWS Credentials Test")
    print("=" * 60)
    
    # Check if credentials are loaded
    aws_access_key = os.getenv('AWS_ACCESS_KEY')
    aws_secret_key = os.getenv('AWS_SECRET_KEY')
    aws_region = os.getenv('AWS_REGION')
    s3_bucket = os.getenv('S3_BUCKET_NAME')
    use_s3 = os.getenv('USE_S3', 'False').lower() == 'true'
    
    print(f"\n1. Environment Variables Check:")
    print(f"   USE_S3: {use_s3}")
    print(f"   AWS_ACCESS_KEY: {'[OK] Set' if aws_access_key else '[X] Missing'}")
    print(f"   AWS_SECRET_KEY: {'[OK] Set' if aws_secret_key else '[X] Missing'}")
    print(f"   AWS_REGION: {aws_region}")
    print(f"   S3_BUCKET_NAME: {s3_bucket}")
    
    if not use_s3:
        print("\n[!] USE_S3 is set to False. S3 storage is disabled.")
        return
    
    if not aws_access_key or not aws_secret_key:
        print("\n[X] ERROR: AWS credentials are missing!")
        return
    
    # Try to import boto3
    print(f"\n2. Boto3 Library Check:")
    try:
        import boto3
        print("   [OK] boto3 is installed")
    except ImportError:
        print("   [X] boto3 is NOT installed")
        print("   Install with: pip install boto3")
        return
    
    # Try to create S3 client
    print(f"\n3. S3 Client Connection:")
    try:
        s3_client = boto3.client(
            's3',
            aws_access_key_id=aws_access_key,
            aws_secret_access_key=aws_secret_key,
            region_name=aws_region
        )
        print("   [OK] S3 client created successfully")
    except Exception as e:
        print(f"   [X] Failed to create S3 client: {e}")
        return
    
    # Test credentials by listing buckets
    print(f"\n4. Credentials Validation:")
    try:
        response = s3_client.list_buckets()
        print("   [OK] Credentials are VALID")
        print(f"   Found {len(response['Buckets'])} bucket(s) in your account:")
        for bucket in response['Buckets']:
            marker = ">>>" if bucket['Name'] == s3_bucket else "   "
            print(f"   {marker} - {bucket['Name']}")
    except Exception as e:
        print(f"   [X] Credentials are INVALID or expired")
        print(f"   Error: {e}")
        return
    
    # Test bucket access
    print(f"\n5. Bucket Access Test ({s3_bucket}):")
    try:
        # Check if bucket exists and is accessible
        s3_client.head_bucket(Bucket=s3_bucket)
        print(f"   [OK] Bucket '{s3_bucket}' exists and is accessible")
        
        # Try to list objects (limited to 5)
        response = s3_client.list_objects_v2(Bucket=s3_bucket, MaxKeys=5)
        object_count = response.get('KeyCount', 0)
        print(f"   [OK] Can list objects in bucket (found {object_count} objects)")
        
    except s3_client.exceptions.NoSuchBucket:
        print(f"   [X] Bucket '{s3_bucket}' does NOT exist")
    except Exception as e:
        error_msg = str(e)
        if "403" in error_msg or "Access Denied" in error_msg:
            print(f"   [X] Access DENIED to bucket '{s3_bucket}'")
            print(f"   Your IAM user may not have permissions for this bucket")
        elif "404" in error_msg:
            print(f"   [X] Bucket '{s3_bucket}' not found")
        else:
            print(f"   [X] Error accessing bucket: {e}")
        return
    
    # Test bucket region
    print(f"\n6. Bucket Region Check:")
    try:
        bucket_location = s3_client.get_bucket_location(Bucket=s3_bucket)
        bucket_region = bucket_location['LocationConstraint'] or 'us-east-1'
        
        if bucket_region == aws_region:
            print(f"   [OK] Bucket region matches: {bucket_region}")
        else:
            print(f"   [!] WARNING: Region mismatch!")
            print(f"     Configured region: {aws_region}")
            print(f"     Bucket region: {bucket_region}")
            print(f"   Update AWS_REGION in .env to: {bucket_region}")
    except Exception as e:
        print(f"   [!] Could not determine bucket region: {e}")
    
    print("\n" + "=" * 60)
    print("[OK] AWS Configuration Test Complete!")
    print("=" * 60)

if __name__ == '__main__':
    test_aws_credentials()
