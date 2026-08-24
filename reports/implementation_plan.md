# Implementation Plan - ML-Assisted Secure Data Deduplication System

Building a complete system for secure cloud data deduplication with ML-based prediction.

## Proposed Changes

### [Backend]
Refine logic and remove branding.

#### [MODIFY] [config.py](file:///c:/Users/amara/OneDrive/Desktop/Hybrid%20ML-CNS%20Dedupliation%20System/config.py)
- Change `SECRET_KEY` default value to remove "Bhnu@2004".
- Ensure all paths are correctly configured.

#### [MODIFY] [app.py](file:///c:/Users/amara/OneDrive/Desktop/Hybrid%20ML-CNS%20Dedupliation%20System/app.py)
- Add basic error handling for file operations.
- Ensure user_id is handled (even if simplified).

#### [MODIFY] [utils.py](file:///c:/Users/amara/OneDrive/Desktop/Hybrid%20ML-CNS%20Dedupliation%20System/utils.py)
- Refine `encrypt_file` and `decrypt_file` if needed.
- Ensure logging is clean.

### [Frontend]
Update aesthetics and remove branding.

#### [MODIFY] [index.html](file:///c:/Users/amara/OneDrive/Desktop/Hybrid%20ML-CNS%20Dedupliation%20System/templates/index.html)
- Remove project code-name branding from navbar and footer.
- Apply more "premium" styling (dark mode support, vibrant accent colors, better typography).

#### [MODIFY] [upload.html](file:///c:/Users/amara/OneDrive/Desktop/Hybrid%20ML-CNS%20Dedupliation%20System/templates/upload.html)
- Enhance the upload form design.

#### [MODIFY] [dashboard.html](file:///c:/Users/amara/OneDrive/Desktop/Hybrid%20ML-CNS%20Dedupliation%20System/templates/dashboard.html)
- Improve data visualization layout.

### [System Setup]
#### [RUN] [init_db.py](file:///c:/Users/amara/OneDrive/Desktop/Hybrid%20ML-CNS%20Dedupliation%20System/init_db.py)
- Execute to initialize the database.

### [Cloud Integration]
Move physical storage to AWS S3.

#### [MODIFY] [config.py](file:///c:/Users/amara/OneDrive/Desktop/Hybrid%20ML-CNS%20Dedupliation%20System/config.py)
- Add `AWS_ACCESS_KEY`, `AWS_SECRET_KEY`, `AWS_REGION`, and `S3_BUCKET_NAME`.
- Add `USE_S3` flag to toggle between local and cloud storage.

#### [MODIFY] [utils.py](file:///c:/Users/amara/OneDrive/Desktop/Hybrid%20ML-CNS%20Dedupliation%20System/utils.py)
- Add `s3_client` initialization.
- Implement `upload_to_s3(file_path, object_name)` and `download_from_s3(object_name, local_path)`.

#### [MODIFY] [dedup.py](file:///c:/Users/amara/OneDrive/Desktop/Hybrid%20ML-CNS%20Dedupliation%20System/dedup.py)
- Update `process_file` to upload the encrypted file to S3 if `USE_S3` is enabled.

#### [MODIFY] [auditing.py](file:///c:/Users/amara/OneDrive/Desktop/Hybrid%20ML-CNS%20Dedupliation%20System/auditing.py)
- Update `audit_file` to fetch the file from S3 before performing the integrity check.

#### [MODIFY] [requirements.txt](file:///c:/Users/amara/OneDrive/Desktop/Hybrid%20ML-CNS%20Dedupliation%20System/requirements.txt)
- Add `boto3`.

## Verification Plan (Cloud)

### Automated Tests
- None.

### Manual Verification
1.  **Configure AWS**: Provide dummy or real S3 credentials in `config.py`.
2.  **Upload to Cloud**: Upload a file and verify it appears in the S3 bucket (or check logs for S3 upload success).
3.  **Cloud Deduplication**: Upload the same file and verify deduplication works even with S3 storage.
4.  **Cloud Auditing**: Run an audit and verify the file is correctly fetched from S3 and validated.
