from dataclasses import dataclass
from typing import TypeAlias

from .enums import GiaType, Subject

BASE_DOMAIN = "sdamgia.ru"


# defining here to prevent import loop
def _base_url(gia_type: GiaType, subject: Subject) -> str:
    return f"https://{subject}-{gia_type}.{BASE_DOMAIN}"


@dataclass(frozen=True)
class BaseType:
    """A base class for SdamGIA types."""

    gia_type: GiaType
    subject: Subject

    @property
    def _base_url(self) -> str:
        return _base_url(gia_type=self.gia_type, subject=self.subject)


@dataclass(frozen=True)
class ProblemPart:
    """Represents problem part (condition or solution)."""

    text: str
    html: str
    image_urls: list[str]


@dataclass(frozen=True)
class Problem(BaseType):
    """Represents problem."""

    id: int
    condition: ProblemPart | None
    solution: ProblemPart | None
    answer: str
    topic_id: int | None
    analog_ids: list[int]

    @property
    def url(self) -> str:
        """URL of the problem."""
        return f"{self._base_url}/problem?id={self.id}"


@dataclass(frozen=True)
class Category(BaseType):
    """Represents problems category."""

    id: int
    name: str
    problems_count: int

    @property
    def url(self) -> str:
        """URL of the category."""
        return f"{self._base_url}/test?category_id={self.id}"


@dataclass(frozen=True)
class Topic(BaseType):
    """Represents problems topic."""

    number: int
    name: str
    is_additional: bool
    categories: list[Category]

    @property
    def url(self) -> str:
        """URL of the topic."""
        category_params = "".join(f"&cat_id[]={category.id}" for category in self.categories)
        return f"{self._base_url}/test?a=view_many&filter=all{category_params}"


Catalog: TypeAlias = list[Topic]
"""Represents problems catalog."""
