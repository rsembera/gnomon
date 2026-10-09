"""Typeface list: well-formed. (What the faces look like is tests/test_ui.py's job.)"""

from core import fonts


def test_keys_and_labels_are_unique():
    assert len({key for key, _label in fonts.FACES}) == len(fonts.FACES)
    assert len({label for _key, label in fonts.FACES}) == len(fonts.FACES)


def test_default_is_the_original_face_and_comes_first():
    assert fonts.DEFAULT == "standard" == fonts.FACES[0][0]
    assert fonts.is_known(fonts.DEFAULT)


def test_unknown_keys_are_not_faces():
    assert not fonts.is_known("comic-sans")
    assert not fonts.is_known(None) and not fonts.is_known(3)
