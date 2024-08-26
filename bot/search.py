import re
from difflib import SequenceMatcher

# string from https://www.geeksforgeeks.org/python-check-url-string/
link_grabber = (r"(?i)\b((?:https?://|www\d{0,3}[.]|[a-z0-9.\-]+[.][a-z]{2"
                r",4}/)(?:[^\s()<>]+|\(([^\s()<>]+|(\([^\s()<>]+\)))*\))+("
                r"?:\(([^\s()<>]+|(\([^\s()<>]+\)))*\)|[^\s`!()\[\]{};:'\""
                r".,<>?«»“”‘’]))")


def is_url(string: str, from_: list | None = None) -> bool:
    search = re.findall(link_grabber, string)
    if len(search) == 0:
        return False
    if from_:
        for website in from_:
            if website in search[0][0]:
                return True
        return False
    else:
        return True


def similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()
