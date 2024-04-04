import asyncio
import io
import logging
import re
import unicodedata
from collections.abc import Callable
from types import TracebackType
from typing import Any, Literal, Self
from urllib.parse import urljoin

import aiohttp
from cairosvg import svg2png
from PIL import Image
from PIL.Image import Image as ImageType
from selectolax.parser import HTMLParser, Node

from .types import BASE_DOMAIN, GiaType, Problem, ProblemPart, Subject


def _handle_params(method: Callable[..., Any]) -> Callable[..., Any]:
    """Handle `gia_type` and `subject` params."""

    async def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
        save_gia_type = self.gia_type
        save_subject = self.subject

        if (gia_type := kwargs.pop("gia_type", None)) is not None:
            self.gia_type = gia_type
        if (subject := kwargs.pop("subject", None)) is not None:
            self.subject = subject

        result = await method(self, *args, **kwargs)

        self.gia_type = save_gia_type
        self.subject = save_subject

        return result

    return wrapper


class SdamgiaAPI:
    """Interface for SdamGIA public API."""

    def __init__(
        self,
        gia_type: GiaType = GiaType.EGE,
        subject: Subject = Subject.MATH,
        *,
        session: aiohttp.ClientSession | None = None,
    ):
        """Initialize the SdamgiaAPI with specified GIA type and subject.

        Args:
            gia_type: The GIA type to use in methods if unspecified.
            subject: The subject to use in methods if unspecified.
            session: An aiohttp client session to use for requests.
        """
        self.gia_type = gia_type
        self.subject = subject
        self._session = session or aiohttp.ClientSession()
        self._latex_ocr_model = None

    @property
    def base_url(self) -> str:
        """Get base site url for currently used GIA type and subject."""
        return f"https://{self.subject}-{self.gia_type}.{BASE_DOMAIN}"

    @_handle_params
    async def get_problem(
        self,
        problem_id: int,
        recognize_text: bool = False,
    ) -> Problem:
        """Fetch a problem by its ID.

        Args:
            problem_id: The ID of the problem to Fetch.
            recognize_text: Whether to perform LaTeX OCR on the problem text.
                Requires "pix2tex" extra.

        Returns:
            The problem fetched.
        """
        parser = HTMLParser(await self._get(f"/problem?id={problem_id}"))

        if (problem_node := parser.css_first(".prob_maindiv")) is None:
            raise RuntimeError("Problem node not found")

        # make all image urls absolute
        for img_node in problem_node.css("img"):
            if BASE_DOMAIN not in (url := str(img_node.attributes["src"])):
                img_node.attributes["src"] = urljoin(self.base_url, url)

        try:
            topic_id = int(problem_node.css_first("span.prob_nums").text().split()[1])
        except (IndexError, AttributeError, ValueError):
            topic_id = None

        try:
            condition_node = parser.css_first("div.pbody")
            condition = await self._get_problem_part(condition_node, recognize_text=recognize_text)
        except (IndexError, AttributeError):
            condition = None

        try:
            solution_node = (
                problem_node.css_first("div.solution") or problem_node.css("div.pbody")[1]
            )
            solution = await self._get_problem_part(solution_node, recognize_text=recognize_text)
        except (IndexError, AttributeError):
            solution = None

        try:
            answer = problem_node.css_first("div.answer").text().lstrip("Ответ:").strip()
        except (IndexError, AttributeError):
            answer = ""

        analog_urls = [
            str(link.attributes["href"]) for link in problem_node.css_first("div.minor").css("a")
        ]
        analog_ids = [
            int(mo.group(1)) for url in analog_urls if (mo := re.search(r"id=(\d+)", url))
        ]

        return Problem(
            gia_type=self.gia_type,
            subject=self.subject,
            problem_id=problem_id,
            condition=condition,
            solution=solution,
            answer=answer,
            topic_id=topic_id,
            analog_ids=analog_ids,
        )

    @_handle_params
    async def search(self, query: str) -> list[int]:
        """Search problems by search query.

        Args:
            query: The search query to use.

        Returns:
            A list of IDs of problems what match search query.
        """
        return await self._get_problem_ids_pagination("/search", params={"search": query})

    @_handle_params
    async def get_theme(self, theme_id: int) -> list[int]:
        """Fetch a category theme by its ID.

        Args:
            theme_id: The ID of the theme to Fetch.

        Returns:
            A list of IDs of problems included in the theme.
        """
        return await self._get_problem_ids_pagination("/test", params={"theme": theme_id})

    @_handle_params
    async def get_test(self, test_id: int) -> list[int]:
        """Fetch a test by its ID.

        Args:
            test_id: The ID of the test to Fetch.

        Returns:
            A list of IDs of problem included in the test.
        """
        parser = HTMLParser(await self._get(f"/test?id={test_id}"))
        return self._get_problem_ids(parser)

    @_handle_params
    async def get_catalog(self) -> list[dict[str, Any]]:
        """Fetch a subject catalog.

        Returns:
            A list of topic dictionaries containing included categories.
        """
        parser = HTMLParser(await self._get("/prob_catalog"))
        topics = [c for c in parser.css("div.cat_category") if c.attributes.get("data-id") is None]
        topics = topics[1:]  # skip header

        catalog = []
        for topic in topics:
            topic_id_str, topic_name = topic.css_first("b.cat_name").text().split(". ", maxsplit=1)
            additional = "д" in topic_id_str.lower()
            topic_id = int(re.search(r"\d+", topic_id_str).group())  # type: ignore[union-attr]

            catalog.append(
                {
                    "topic_id": topic_id,
                    "topic_name": topic_name,
                    "additional": additional,
                    "categories": [
                        {
                            "category_id": int(cat_node.attributes["data-id"]),  # type: ignore[arg-type]
                            "category_name": cat_node.css_first("a.cat_name").text(),
                        }
                        for cat_node in topic.css_first("div.cat_children").css("div.cat_category")
                    ],
                }
            )

        return catalog

    @_handle_params
    async def generate_test(self, problems: dict[int | Literal["full"], int] | None = None) -> int:
        """Generate a test with a specified number of problems from selected categories.

        If none are passed, generates a test with one problem from each category.

        Args:
            problems: A dictionary specifying the number of problems to include for each category.
                Should be formatted as follows: `{<category id>: <problems count>, ... }`.

                Alternatively, you can specify the same number of problems for each category:
                `{'full': <problems count>}`.

        Returns:
            The generated test ID.
        """
        if not problems:
            problems = {"full": 1}

        if total := problems.get("full"):
            params = {f"prob{i + 1}": total for i in range(len(await self.get_catalog()))}
        else:
            params = {f"prob{i}": problems[i] for i in problems}

        path = (
            await self._session.get(
                f"{self.base_url}/test?a=generate",
                params=params,
                allow_redirects=False,
            )
        ).headers["location"]
        return int(re.search(r"id=(\d+)", path).group(1))  # type: ignore[union-attr]

    @_handle_params
    async def generate_pdf(
        self,
        test_id: int,
        *,
        solutions: bool = False,
        problem_ids: bool = False,
        answers: bool = False,
        answers_table: bool = False,
        criteria: bool = False,
        instruction: bool = False,
        footer: str = "",
        title: str = "",
        pdf_type: Literal["h", "z", "m", "true"] = "true",
    ) -> str:
        """Generates a PDF version of the test.

        Args:
            test_id: The identifier of the test.
            solutions: Include explanations.
            problem_ids: Include problem numbers.
            answers: Include answers.
            answers_table: Include answer key.
            criteria: Include criteria.
            instruction: Include instruction.
            footer: The text for the footer.
            title: The title of the test.
            pdf_type: The type of the generated PDF document.

                "h" - version with large margins.
                "z" - version with large font.
                "m" - horizontal version.
                "true" - normal version (default).

        Returns:
            The URL of the generated PDF document.
        """

        def _format(var: bool) -> str:
            return "true" if var else ""

        params = {
            "id": test_id,
            "print": "true",
            "pdf": pdf_type,
            "sol": _format(solutions),
            "num": _format(problem_ids),
            "ans": _format(answers),
            "key": _format(answers_table),
            "crit": _format(criteria),
            "pre": _format(instruction),
            "dcol": footer,
            "tt": title,
        }
        for key, value in params.copy().items():
            if not value:
                del params[key]

        return urljoin(
            self.base_url,
            (
                await self._session.get(
                    f"{self.base_url}/test", params=params, allow_redirects=False
                )
            ).headers["location"],
        )

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if not self._session.closed:
            await self._session.close()

    async def _get(self, path: str = "", url: str = "", **kwargs: Any) -> str:
        """Get html from full `url` or `path` relative to base url."""
        url = url or urljoin(self.base_url, path)
        async with self._session.request(method="GET", url=url, **kwargs) as response:
            logging.debug(f"Sent GET request: {response.status}: {response.url}")
            response.raise_for_status()
            return await response.text()

    async def _fetch_svg(self, url: str) -> ImageType:
        byte_string = await self._get(url=url)
        png_bytes = svg2png(bytestring=byte_string)
        buffer = io.BytesIO(png_bytes)
        return Image.open(buffer)

    def _recognize_image_text(self, image: ImageType) -> str:
        if self._latex_ocr_model is None:
            try:
                from pix2tex.cli import LatexOCR

                self._latex_ocr_model = LatexOCR()
            except ImportError:
                raise RuntimeError("'pix2tex' is required for this functional but not found")
        return f"${self._latex_ocr_model(image)}$"  # type: ignore[misc]

    async def _get_problem_part(self, node: Node, recognize_text: bool = False) -> ProblemPart:
        image_nodes = node.css("img.tex")
        image_urls = [str(img_node.attributes["src"]) for img_node in image_nodes]

        if recognize_text:
            images = await asyncio.gather(
                *[asyncio.create_task(self._fetch_svg(url)) for url in image_urls]
            )

            for img_node, image in zip(image_nodes, images):
                img_node.replace_with(self._recognize_image_text(image))

            text = node.text(strip=True, deep=True)
            text = unicodedata.normalize("NFKC", text).replace("\xad", "")
        else:
            text = ""

        for img_node in node.css("img"):
            if (url := str(img_node.attributes["src"])) not in image_urls:
                image_urls.append(url)

        return ProblemPart(text=text, html=str(node.html), image_urls=image_urls)

    @staticmethod
    def _get_problem_ids(node: Node | HTMLParser) -> list[int]:
        return [int(node.css_first("a").text()) for node in node.css("span.prob_nums")]

    async def _get_problem_ids_pagination(self, path: str, params: dict[str, Any]) -> list[int]:
        result: list[int] = []
        page = 1
        while True:
            params |= {"page": page}
            parser = HTMLParser(await self._get(path, params=params))
            if not (ids := self._get_problem_ids(parser)):
                return result
            for id in ids:
                # to prevent bug when site infinitely returns last results page
                if id in result:
                    return result
                result.append(id)
            page += 1
