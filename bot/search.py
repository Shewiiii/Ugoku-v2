import re
from difflib import SequenceMatcher
from typing import Optional
from urllib.parse import urlparse

# string from https://www.geeksforgeeks.org/python-check-url-string/
link_grabber = re.compile(
    r"(?i)\b((?:https?://|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2"
    r",4}/)(?:[^\s()<>]+|\(([^\s()<>]+|(\([^\s()<>]+\)))*\))+("
    r"?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|[^\s`!()\[\]{};:'\""
    r".,<>?«»“”‘’]))"
)


def is_url(
    string: str,
    from_: Optional[list] = None,
    parts: Optional[list] = None,
) -> bool:
    search = link_grabber.match(string)
    if not search:
        return False

    conditions = []
    parsed_url = urlparse(string)
    domain = parsed_url.netloc

    if from_:
        conditions.append(any(domain.endswith(website) for website in from_))
    if parts:
        path_parts = set(parsed_url.path.split("/")[:-1])
        conditions.append(any(part in path_parts for part in parts))

    return all(conditions) if conditions else True


def token_sort_ratio(str1, str2):
    tokens1 = str1.split()
    tokens2 = str2.split()

    sorted_tokens1 = sorted(tokens1)
    sorted_tokens2 = sorted(tokens2)

    sorted_str1 = " ".join(sorted_tokens1)
    sorted_str2 = " ".join(sorted_tokens2)

    return SequenceMatcher(None, sorted_str1, sorted_str2).ratio()


def get_closest_string(model, strings: list[str]) -> str:
    """Returns the index of the string closest to the model in a list of strings."""
    scores = {}
    for i, string in enumerate(strings):
        scores[token_sort_ratio(model, string)] = i
    return scores[max(scores)]
