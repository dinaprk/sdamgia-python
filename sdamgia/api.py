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

from .types import BASE_DOMAIN, GitType, Problem, ProblemPart, Subject


def _handle_params(method: Callable[..., Any]) -> Callable[..., Any]:
    """Handle :var:`gia_type` and :var:`subject` params"""

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
    def __init__(
        self,
        gia_type: GitType = GitType.EGE,
        subject: Subject = Subject.MATH,
        session: aiohttp.ClientSession | None = None,
    ):
        self.gia_type = gia_type
        self.subject = subject
        self._session = session or aiohttp.ClientSession()
        self._latex_ocr_model = None

    @property
    def base_url(self) -> str:
        return f"https://{self.subject}-{self.gia_type}.{BASE_DOMAIN}"

    @_handle_params
    async def get_problem(
        self,
        problem_id: int,
        recognize_text: bool = False,
    ) -> Problem:
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
        """Поиск задач по запросу"""
        return await self._get_problem_ids_pagination("/search", params={"search": query})

    @_handle_params
    async def get_theme(self, theme_id: int) -> list[int]:
        return await self._get_problem_ids_pagination("/test", params={"theme": theme_id})

    @_handle_params
    async def get_test(self, test_id: int) -> list[int]:
        """Получение списка задач, включенных в тест"""
        parser = HTMLParser(await self._get(f"/test?id={test_id}"))
        return self._get_problem_ids(parser)

    @_handle_params
    async def get_catalog(self) -> list[dict[str, Any]]:
        """Получение каталога заданий для определенного предмета"""
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
    async def generate_test(self, problems: dict[int | str, int] | None = None) -> int:
        """
        Генерирует тест по заданным параметрам

        :param problems: Список заданий
        По умолчанию генерируется тест, включающий по одной задаче из каждого задания предмета.
        Так же можно вручную указать одинаковое количество задач для каждогоиз заданий:
        {'full': <кол-во задач>}
        Указать определенные задания с определенным количеством задач для каждого:
        {<номер задания>: <кол-во задач>, ... }
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
        """
        Генерирует pdf версию теста

        :param test_id: Идентифигатор теста
        :param solutions: Пояснение
        :param problem_ids: № заданий
        :param answers: Ответы
        :param answers_table: Ключ
        :param criteria: Критерии
        :param instruction: Инструкция
        :param footer: Нижний колонтитул
        :param title: Заголовок
        :param pdf_type: Версия генерируемого pdf документа
        По умолчанию генерируется стандартная вертикальная версия
        h - версия с большими полями
        z - версия с крупным шрифтом
        m - горизонтальная версия
        true - версия по умолчанию
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
        """Get html from full :var:`url` or :var:`path` relative to base url"""
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
