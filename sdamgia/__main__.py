import asyncio
import io
import logging
import unicodedata
from types import TracebackType
from typing import Any, Literal, Self
from urllib.parse import urljoin

import aiohttp
import bs4
from cairosvg import svg2png
from PIL import Image
from PIL.Image import Image as ImageType

from .types import GitType, Problem, ProblemPart, Subject


class SdamGIA:
    BASE_DOMAIN = "sdamgia.ru"

    def __init__(
        self,
        gia_type: GitType = GitType.EGE,
        subject: Subject | None = None,
        session: aiohttp.ClientSession | None = None,
    ):
        self.gia_type = gia_type
        self.subject = subject
        self._session = session or aiohttp.ClientSession()
        self._latex_ocr_model = None

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

    async def _get(self, url: str = "", path: str = "", **kwargs: Any) -> str:
        """Get html from ``url`` or ``path`` endpoint"""
        url = url or urljoin(self.base_url(), path)
        async with self._session.request(method="GET", url=url, **kwargs) as response:
            logging.debug(f"Sent GET request: {response.url}")
            return await response.text()

    @staticmethod
    def _soup(html: str) -> bs4.BeautifulSoup:
        return bs4.BeautifulSoup(markup=html, features="lxml")

    def base_url(self, subject: Subject | None = None, gia_type: GitType | None = None) -> str:
        gia_type = gia_type or self.gia_type
        subject = subject or self.subject
        return f"https://{subject.value}-{gia_type.value}.{self.BASE_DOMAIN}"

    async def get_image_from_url(self, url: str) -> ImageType:
        byte_string = await self._get(url)
        png_bytes = svg2png(bytestring=byte_string)
        buffer = io.BytesIO(png_bytes)
        return Image.open(buffer)

    def image_to_tex(self, image: ImageType) -> str:
        if self._latex_ocr_model is None:
            try:
                from pix2tex.cli import LatexOCR

                self._latex_ocr_model = LatexOCR()
            except ImportError:
                raise RuntimeError("'pix2tex' is required for this functional but not found")
        return f"${self._latex_ocr_model(image)}$"  # type: ignore[misc]

    async def get_latex_from_url_list(self, image_links: list[str]) -> dict[str, str]:
        condition_image_tasks = [
            asyncio.create_task(self.get_image_from_url(url)) for url in image_links
        ]
        images_data: tuple[ImageType] = await asyncio.gather(*condition_image_tasks)
        string_tex_list = tuple(map(self.image_to_tex, images_data))
        return dict(zip(image_links, string_tex_list))

    async def _get_problem_part(self, tag: bs4.Tag, recognize_text: bool = False) -> ProblemPart:
        image_links = [img.get("src") for img in tag.find_all("img", class_="tex")]

        if recognize_text:
            # replace images with recognized tex source code
            recognized_texts = await self.get_latex_from_url_list(image_links)
            for img_tag in tag.find_all("img", class_="tex"):
                img_tag.replace_with(recognized_texts.get(img_tag.get("src")))

            text = tag.get_text(strip=True).replace("−", "-").replace("\xad", "")
            text = unicodedata.normalize("NFKC", text)
        else:
            text = ""

        for img in tag.find_all("img"):
            if (link := img.get("src")) is not None and link not in image_links:
                image_links.append(link)

        return ProblemPart(text=text, html=str(tag), image_links=image_links)

    async def get_problem_by_id(
        self,
        subject: Subject,
        problem_id: int,
        recognize_text: bool = False,
    ) -> Problem:
        soup = self._soup(await self._get(f"{self.base_url(subject)}/problem?id={problem_id}"))

        if (problem_block := soup.find("div", class_="prob_maindiv")) is None:
            raise RuntimeError("Problem block not found")

        for img in problem_block.find_all("img"):
            if self.BASE_DOMAIN not in img["src"]:
                img["src"] = urljoin(self.base_url(subject), img["src"])

        try:
            topic_id = int(problem_block.find("span", class_="prob_nums").text.split()[1])
        except (IndexError, AttributeError, ValueError):
            topic_id = None

        try:
            condition_tag = soup.find("div", class_="pbody")
            condition = await self._get_problem_part(condition_tag, recognize_text=recognize_text)
        except (IndexError, AttributeError):
            condition = None

        try:
            if (solution_tag := problem_block.find("div", class_="solution")) is None:
                solution_tag = problem_block.find_all("div", class_="pbody")[1]
            solution = await self._get_problem_part(solution_tag, recognize_text=recognize_text)
        except (IndexError, AttributeError):
            solution = None

        try:
            answer = problem_block.find("div", class_="answer").text.lstrip("Ответ:").strip()
        except (IndexError, AttributeError):
            answer = ""

        analogs = [
            link["href"].replace("/problem?id=", "")
            for link in problem_block.find("div", class_="minor").find_all("a")
            if str(problem_id) not in link["href"]
        ]
        analogs = sorted([int(i) for i in analogs if i.isdigit()])

        return Problem(
            gia_type=self.gia_type,
            subject=subject,
            problem_id=problem_id,
            condition=condition,
            solution=solution,
            answer=answer,
            topic_id=topic_id,
            analogs=analogs,
        )

    async def search(self, subject: Subject, query: str) -> list[int]:
        """
        Поиск задач по запросу

        :param subject: Наименование предмета
        :param query: Запрос
        """
        problem_ids = []
        page = 1
        while True:
            params = {"search": query, "page": page}
            html = await self._get(f"{self.base_url(subject)}/search", params=params)
            soup = self._soup(html)
            ids = [int(i.text.split()[-1]) for i in soup.find_all("span", class_="prob_nums")]
            if not ids:
                break
            problem_ids.extend(ids)
            logging.debug(f"{page=}")
            page += 1
        logging.debug(f"total: {len(problem_ids)}")
        return problem_ids

    async def get_test_by_id(self, subject: Subject, test_id: int) -> list[int]:
        """
        Получение списка задач, включенных в тест

        :param subject: Наименование предмета
        :param test_id: Идентификатор теста
        """
        html = await self._get(f"{self.base_url(subject)}/test?id={test_id}")
        soup = self._soup(html)
        return [int(i.text.split()[-1]) for i in soup.find_all("span", class_="prob_nums")]

    async def get_theme_by_id(self, subject: Subject, theme_id: int) -> list[str | int]:
        problem_ids = []
        page = 1
        while True:
            params = {"theme": theme_id, "page": page}
            logging.info(f"Getting theme {theme_id}, page={page}")
            html = await self._get(f"{self.base_url(subject)}/test", params=params)
            soup = self._soup(html)
            ids = soup.find_all("span", class_="prob_nums")
            if not ids:
                break
            ids = [i.find("a").text for i in ids]
            problem_ids.extend(ids)
            page += 1
        return problem_ids

    async def get_catalog(self, subject: Subject) -> list[dict[str, Any]]:
        """
        Получение каталога заданий для определенного предмета

        :param subject: Наименование предмета
        """

        html = await self._get(f"{self.base_url(subject)}/prob_catalog")
        soup = self._soup(html)
        catalog = []
        catalog_result = []

        for i in soup.find_all("div", class_="cat_category"):
            try:
                i["data-id"]
            except IndexError:
                catalog.append(i)

        for topic in catalog[1:]:
            topic_text = topic.find("b", class_="cat_name").text
            topic_name = topic_text.split(". ")[1]
            topic_id = topic_text.split(". ")[0]
            if topic_id[0] == " ":
                topic_id = topic_id[2:]
            if topic_id.find("Задания ") == 0:
                topic_id = topic_id.replace("Задания ", "")

            catalog_result.append(
                {
                    "topic_id": topic_id,
                    "topic_name": topic_name,
                    "categories": [
                        {
                            "category_id": i["data-id"],
                            "category_name": i.find("a", class_="cat_name").text,
                        }
                        for i in topic.find("div", class_="cat_children").find_all(
                            "div", class_="cat_category"
                        )
                    ],
                }
            )

        return catalog_result

    async def generate_test(self, subject: Subject, problems: dict[str, int] | None = None) -> str:
        """
        Генерирует тест по заданным параметрам

        :param subject: Наименование предмета

        :param problems: Список заданий
        По умолчанию генерируется тест, включающий по одной задаче из каждого задания предмета.
        Так же можно вручную указать одинаковое количество задач для каждогоиз заданий:
        {'full': <кол-во задач>}
        Указать определенные задания с определенным количеством задач для каждого:
        {<номер задания>: <кол-во задач>, ... }
        """

        if problems is None:
            problems = {"full": 1}

        if "full" in problems:
            params = {
                f"prob{i}": problems["full"]
                for i in range(1, len(await self.get_catalog(subject)) + 1)
            }
        else:
            params = {f"prob{i}": problems[i] for i in problems}

        return (
            (
                await self._session.get(
                    f"{self.base_url(subject)}/test?a=generate",
                    params=params,
                    allow_redirects=False,
                )
            )
            .headers["location"]
            .split("id=")[1]
            .split("&nt")[0]
        )

    async def generate_pdf(
        self,
        subject: Subject,
        test_id: int,
        solution: bool = False,
        nums: bool = False,
        answers: bool = False,
        key: bool = False,
        crit: bool = False,
        instruction: bool = False,
        col: str = "",
        tt: str = "",
        pdf: Literal["h", "z", "m", ""] = "",
    ) -> str:
        """
        Генерирует pdf версию теста

        :param subject: Наименование предмета
        :param test_id: Идентифигатор теста
        :param solution: Пояснение
        :param nums: № заданий
        :param answers: Ответы
        :param key: Ключ
        :param crit: Критерии
        :param instruction: Инструкция
        :param col: Нижний колонтитул
        :param tt: Заголовок
        :param pdf: Версия генерируемого pdf документа
        По умолчанию генерируется стандартная вертикальная версия
        h - версия с большими полями
        z - версия с крупным шрифтом
        m - горизонтальная версия
        """

        params = {
            "id": test_id,
            "print": "true",
            "pdf": pdf,
            "sol": str(solution),
            "num": str(nums),
            "ans": str(answers),
            "key": str(key),
            "crit": str(crit),
            "pre": str(instruction),
            "dcol": col,
            "tt": tt,
        }

        return urljoin(
            self.base_url(subject),
            (
                await self._session.get(
                    f"{self.base_url(subject)}/test", params=params, allow_redirects=False
                )
            ).headers["location"],
        )
