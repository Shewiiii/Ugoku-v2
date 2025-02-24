from difflib import SequenceMatcher


def token_sort_ratio(str1, str2):
    tokens1 = str1.split()
    tokens2 = str2.split()

    sorted_tokens1 = sorted(tokens1)
    sorted_tokens2 = sorted(tokens2)

    sorted_str1 = ' '.join(sorted_tokens1)
    sorted_str2 = ' '.join(sorted_tokens2)

    return SequenceMatcher(None, sorted_str1, sorted_str2).ratio()


def get_closest_string(model, strings: list[str]) -> str:
    """Returns the index of the string closest to the model in a list of strings."""
    scores = {}
    for i, string in enumerate(strings):
        scores[token_sort_ratio(model, string)] = i
    return scores[max(scores)]
