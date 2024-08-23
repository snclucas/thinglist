

from database_functions import get_all_images


def prune():

    d = get_all_images(user_id=None)

    import os
    for root, dirs, files in os.walk("/mydir"):
        for file in files:
            if file.endswith(".txt"):
                print(os.path.join(root, file))

    f = 6


if __name__ == '__main__':
    prune()
