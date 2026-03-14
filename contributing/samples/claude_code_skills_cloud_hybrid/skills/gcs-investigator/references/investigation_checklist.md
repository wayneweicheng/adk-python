# GCS Investigation Checklist

- Confirm the bucket and prefix are correct
- Check whether expected files are missing or delayed
- Look for duplicate object naming patterns or partial uploads
- Compare object timestamps with the reported pipeline incident window
- Inspect safe text payloads for malformed JSON, empty files, or schema drift hints
