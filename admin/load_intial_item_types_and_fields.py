import csv
import os

from slugify import slugify

from database_functions import get_or_create

from models import Field


def load_fields():
    path = os.getcwd()
    file_path = os.path.realpath(__file__)
    item_types_csv = f"{path}/../data/fields.csv"

    with open(item_types_csv, newline='') as csvfile:
        line_count = 0
        reader = csv.reader(csvfile, delimiter=',', quotechar='"')
        for row in reader:
            print(', '.join(row))
            if line_count != 0:
                get_or_create(model=Field, field=row[0], slug=slugify(row[1]), type=row[2])
            line_count += 1


if __name__ == '__main__':
    load_fields()
