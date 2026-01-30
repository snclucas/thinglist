import csv
import json
import os

from slugify import slugify

from database.database_functions import get_or_create

from models import Field, ItemType, ReservedWords


def load_fields():
    path = os.getcwd()
    file_path = os.path.realpath(__file__)
    item_types_csv = f"{path}/../data/fields.csv"

    with open(item_types_csv, newline='') as csvfile:
        line_count = 0
        reader = csv.reader(csvfile, delimiter=',', quotechar='"')
        for row in reader:
            if line_count != 0:
                get_or_create(model=Field, field=row[0], slug=slugify(row[0]), type=row[1])
            line_count += 1

    return line_count


def load_types():
    path = os.getcwd()
    file_path = os.path.realpath(__file__)
    item_types_csv = f"{path}/../data/items_types.csv"

    with open(item_types_csv, newline='') as csvfile:
        line_count = 0
        reader = csv.reader(csvfile, delimiter=',', quotechar='"')
        for row in reader:
            if line_count != 0:
                get_or_create(model=ItemType, name=row[0])
            line_count += 1

    return line_count


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
