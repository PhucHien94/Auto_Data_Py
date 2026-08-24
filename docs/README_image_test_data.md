# Image Search Test Data — Usage

This document describes the structured test data used for verifying the Image Search feature.

- `SmartSearch/image_test_data_sets.csv`: CSV listing multiple test sets and individual test cases. Each row includes a placeholder `ImageFile` name. Replace placeholders with real images when preparing the dataset.

How to use:
- Create a `test_images` folder and populate it with images that match the `ImageFile` names in the CSV. Use realistic product images, variants, and edge cases described.
- Run your Image Search service with each test image (or batch uploads) and record results.
- Compare returned product IDs / similarity lists against `ExpectedResult` and `PassCriteria`.

Suggested artifacts to collect for each test run:
- Input image path and metadata (format, resolution, size)
- Service response (top N results with product IDs and similarity/confidence scores)
- Response time and any error messages
- Pass/Fail verdict and notes

If you want, I can:
- Generate placeholder image files (colored thumbnails) matching the `ImageFile` names.
- Produce an Excel version of the CSV.
- Create a small runner script to call a REST Image Search endpoint and record results into a CSV.
