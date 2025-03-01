import csv
import os
import json

from slugify import slugify

from database.database_functions import get_or_create

from models import Field, ItemType, ReservedWords


def load_words():
    path = os.getcwd()
    _reserved_words_file = f"{path}/../data/reserved_words.json"
    _reserved_words_json = json.load(open(_reserved_words_file))

    line_count = 0

    for word in _reserved_words_json:
        if line_count != 0:
            get_or_create(model=ReservedWords, word=word)
        line_count += 1

    return line_count


if __name__ == '__main__':
    load_words()
