import re

def sanitize_filename(filename: str) -> str:
    # Define a regular expression pattern that matches any character not allowed in filenames
    # For Windows, common illegal characters include: \ / : * ? " < > |
    # The following pattern keeps only alphanumeric characters, hyphens, underscores, and periods.
    sanitized_filename = re.sub(r'[^A-Za-z0-9._-]', '_', filename)
    return sanitized_filename