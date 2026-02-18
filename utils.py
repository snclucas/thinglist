import random
import re
import string

from PIL import Image
import bleach


CLEANR = re.compile('<.*?>|&([a-z0-9]+|#[0-9]{1,6}|#x[0-9a-f]{1,6});')

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

def _to_bool(value):
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).lower() in ('1', 'true', 'on', 'yes')

def sanitize(value: str) -> str:
    """Sanitize user input using bleach clean and return a stripped string.

    Returns empty string for falsy input.
    """
    if not value:
        return ''
    try:
        return bleach.clean(str(value), strip=True)
    except Exception:
        return str(value)

def password_check(password: str) -> dict:
    """Return a dict describing password policy checks.

    Policy: min length 8, must contain digit, uppercase, lowercase and symbol.
    """
    if password is None:
        password = ''
    length_error = len(password) < 8
    digit_error = re.search(r"\d", password) is None
    uppercase_error = re.search(r"[A-Z]", password) is None
    lowercase_error = re.search(r"[a-z]", password) is None
    symbol_error = re.search(r"\W", password) is None
    password_ok = not (length_error or digit_error or uppercase_error or lowercase_error or symbol_error)

    return {
        'password_ok': password_ok,
        'length_error': length_error,
        'digit_error': digit_error,
        'uppercase_error': uppercase_error,
        'lowercase_error': lowercase_error,
        'symbol_error': symbol_error,
    }
