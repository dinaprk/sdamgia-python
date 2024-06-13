from enum import Enum


class GiaType(str, Enum):
    """Represents GIA types."""

    OGE = "oge"
    EGE = "ege"


class Subject(str, Enum):
    """Represents subject types."""

    MATH = "math"
    MATH_BASE = "mathb"
    PHYSICS = "phys"
    INFORMATICS = "inf"
    BIOLOGY = "bio"
    LITERATURE = "lit"
    HISTORY = "hist"
    CHEMISTRY = "chem"
    GEOGRAPHY = "geo"
    SOCIAL_SCIENCE = "soc"
    RUSSIAN_LANGUAGE = "rus"
    ENGLISH_LANGUAGE = "en"
    GERMAN_LANGUAGE = "de"
    FRENCH_LANGUAGE = "fr"
    SPANISH_LANGUAGE = "sp"
