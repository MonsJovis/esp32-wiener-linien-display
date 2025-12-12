from gc import collect

# Characters that need URL encoding
CHARS_TO_ENCODE = [
    '%', '+', 'ä', 'ö', 'ü', 'Ä', 'Ö', 'Ü',
    'ß', ' ', '°', '!', '"', '§', '$',
    '&', '/', '?', '\\', '^', '|', '(', ')', ';',
    ':', '#', "'", '[', ']', '{', '}',
]

# Corresponding URL-encoded values
ENCODED_VALUES = [
    '%25', '%2B', '%C3%A4', '%C3%B6', '%C3%BC', '%C3%84', '%C3%96', '%C3%9C',
    '%C3%9F', '%20', '%C2%B0', '%21', '%22', '%C2%A7', '%24',
    '%26', '%2F', '%3F', '%5C', '%5E', '%7C', '%28', '%29', '%3B',
    '%3A', '%23', '%27', '%5B', '%5D', '%7B', '%7D',
]


def url_encode(string):
    """URL-encode a string, handling special characters and German umlauts."""
    for i in range(len(CHARS_TO_ENCODE)):
        if CHARS_TO_ENCODE[i] in string:
            string = string.replace(CHARS_TO_ENCODE[i], ENCODED_VALUES[i])
    collect()  # Single GC call at end instead of per-iteration
    return string