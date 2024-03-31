from dataclasses import dataclass
from enum import StrEnum


class GitType(StrEnum):
    OGE = "oge"
    EGE = "ege"


class Subject(StrEnum):
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
    FRANCH_LANGUAGE = "fr"
    SPANISH_LANGUAGE = "sp"


@dataclass
class ProblemPart:
    text: str
    html: str
    image_urls: list[str]


@dataclass
class Problem:
    gia_type: GitType
    subject: Subject
    problem_id: int
    condition: ProblemPart | None
    solution: ProblemPart | None
    answer: str
    topic_id: int | None
    analog_ids: list[int]

    @property
    def url(self) -> str:
        return f"https://{self.subject}-{self.gia_type}.{BASE_DOMAIN}/problem?id={self.problem_id}"


BASE_DOMAIN = "sdamgia.ru"
