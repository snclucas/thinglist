import random
import string

from PIL import Image


def correct_image_orientation(image: Image):
    if hasattr(image, '_getexif'):
        exifdata = image._getexif()
        try:
            orientation = exifdata.get(274)
        except:
            orientation = 1
    else:
        orientation = 1

    if orientation == 1:
        pass
    elif orientation == 2:
        image = image.transpose(Image.FLIP_LEFT_RIGHT)
    elif orientation == 3:
        image = image.rotate(180)
    elif orientation == 4:
        image = image.rotate(180)
    elif orientation == 5:
        image = image.rotate(-90)
    elif orientation == 6:
        image = image.rotate(-90)
    elif orientation == 7:
        image = image.rotate(90)
    elif orientation == 8:
        image = image.rotate(90)

    return image

def generate_item_image_filename(item_slug: str, item_id: int, img_type: str) -> str:
    """Generate the filename for an item's image.

    :param item_slug: The slug of the item. The slug is a URL-safe version of the item's name.
    :param item_id: The numerical ID of the item.
    :param img_type: The type or extension of the image file.
    :return: The generated filename for the item's image.
    """
    item_slug = item_slug.replace('-', '_')
    rand_ = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    img_filename = f"{item_slug}_{item_id}_{rand_}.{img_type}"
    return img_filename
