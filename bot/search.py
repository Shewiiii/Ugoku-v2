import re
from difflib import SequenceMatcher
from urllib.parse import urlparse

# string from https://www.geeksforgeeks.org/python-check-url-string/
link_grabber = (
    r"(?i)\b((?:https?://|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2"
    r",4}/)(?:[^\s()<>]+|\(([^\s()<>]+|(\([^\s()<>]+\)))*\))+("
    r"?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|[^\s`!()\[\]{};:'\""
    r".,<>?«»“”‘’]))"
)


def is_url(string: str, from_: list | None = None) -> bool:
    search = re.match(link_grabber, string)
    if not search:
        return False
    if from_:
        parsed_url = urlparse(string)
        domain = parsed_url.netloc
        return any(domain.endswith(website) for website in from_)
    else:
        return True


def token_sort_ratio(str1, str2):
    tokens1 = str1.split()
    tokens2 = str2.split()

    sorted_tokens1 = sorted(tokens1)
    sorted_tokens2 = sorted(tokens2)

    sorted_str1 = ' '.join(sorted_tokens1)
    sorted_str2 = ' '.join(sorted_tokens2)

    return SequenceMatcher(None, sorted_str1, sorted_str2).ratio()
