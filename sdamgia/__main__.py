import asyncio
import io
import json
import logging
import unicodedata
from types import TracebackType
from typing import Any, Literal, Self
from urllib.parse import urljoin

import aiohttp
from bs4 import BeautifulSoup
from cairosvg import svg2png
from PIL import Image
from PIL.Image import Image as ImageType

from sdamgia.exceptions import ProblemBlockNotFoundError
from sdamgia.types import GitType, Subject


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
        async with self._session.get(url=url, **kwargs) as response:
            logging.debug(f"Sent GET request: {response.url}")
            return await response.text()

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
        return {image_links[i]: string_tex_list[i] for i in range(len(images_data))}

    async def get_problem_by_id(
        self,
        subject: Subject,
        problem_id: int,
        recognize_text: bool = False,
    ) -> dict[str, Any]:
        problem_url = f"{self.base_url(subject)}/problem?id={problem_id}"
        problem_html = await self._get(problem_url)
        soup = BeautifulSoup(problem_html.replace("\xa0", " "), "lxml")

        problem_block = soup.find("div", {"class": "prob_maindiv"})

        if problem_block is None:
            raise ProblemBlockNotFoundError()

        for img in problem_block.find_all("img"):
            if self.BASE_DOMAIN not in img["src"]:
                img["src"] = urljoin(self.base_url(subject), img["src"])

        topic_id = int(problem_block.find("span", {"class": "prob_nums"}).text.split()[1])

        try:
            condition_element = soup.find_all("div", {"class": "pbody"})[0]

            condition_html = str(condition_element)

            condition_image_links = [
                i.get("src") for i in condition_element.find_all("img", class_="tex")
            ]

            if recognize_text:
                condition_tex_dict = await self.get_latex_from_url_list(condition_image_links)

                for img_tag in condition_element.find_all("img", class_="tex"):
                    img_tag.replace_with(condition_tex_dict.get(img_tag.get("src")))

                text = condition_element.text.replace("−", "-")
            else:
                text = ""

            condition = {
                "text": text,
                "html": condition_html,
                "images": condition_image_links
                + [i.get("src") for i in condition_element.find_all("img")],
            }
        except (IndexError, AttributeError):
            condition = {"text": "", "html": "", "images": []}

        try:
            solution_element = problem_block.find("div", {"class": "solution"})
            if solution_element is None:
                solution_element = problem_block.find_all("div", class_="pbody")[1]

            solution_html = str(solution_element)

            solution_image_links = [
                i.get("src") for i in solution_element.find_all("img", class_="tex")
            ]

            if recognize_text:
                solution_tex_dict = await self.get_latex_from_url_list(solution_image_links)

                for img_tag in solution_element.find_all("img", class_="tex"):
                    img_tag.replace_with(solution_tex_dict.get(img_tag.get("src")))

                text = solution_element.text.replace("−", "-")
            else:
                text = ""

            solution = {
                "text": text,
                "html": solution_html,
                "images": solution_image_links
                + [i.get("src") for i in solution_element.find_all("img")],
            }
        except (IndexError, AttributeError):
            solution = {"text": "", "html": "", "images": []}

        try:
            answer = problem_block.find("div", {"class": "answer"}).text.replace("Ответ: ", "")
        except (IndexError, AttributeError):
            answer = ""

        condition["text"] = unicodedata.normalize("NFKC", condition["text"])
        solution["text"] = unicodedata.normalize("NFKC", solution["text"])

        problem_analogs = [
            i.get("href").replace("/problem?id=", "")
            for i in problem_block.find_all("div", class_="minor")[0].find_all("a")
            if str(problem_id) not in i.get("href")
        ]
        problem_analogs = sorted([int(i) for i in problem_analogs if i.isdigit()])

        return {
            "condition": condition,
            "solution": solution,
            "answer": answer,
            "problem_id": problem_id,
            "topic_id": topic_id,
            "analogs": problem_analogs,
            "url": problem_url,
            "subject": subject.value,
            "gia_type": self.gia_type.value,
        }

    async def search(self, subject: Subject, query: str) -> list[int]:
        """
        Поиск задач по запросу

        :param subject: Наименование предмета
        :param query: Запрос
        """
        problem_ids = []
        params = {"search": query, "page": 1}
        page = 1
        while True:
            text = await self._get(f"{self.base_url(subject)}/search", params=params)
            soup = BeautifulSoup(text, "lxml")
            ids = [i.text.split()[-1] for i in soup.find_all("span", {"class": "prob_nums"})]
            if len(ids) == 0:
                break
            problem_ids.extend(ids)
            params["page"] += 1
            logging.debug(f"{page=}")
            page += 1
        logging.debug(f"total: {len(problem_ids)}")
        return list(map(int, problem_ids))

    async def get_test_by_id(self, subject: Subject, test_id: int) -> list[int]:
        """
        Получение списка задач, включенных в тест

        :param subject: Наименование предмета
        :param test_id: Идентификатор теста
        """
        text = await self._get(f"{self.base_url(subject)}/test?id={test_id}")
        soup = BeautifulSoup(text, "html.parser")
        return [int(i.text.split()[-1]) for i in soup.find_all("span", {"class": "prob_nums"})]

    async def get_theme_by_id(self, subject: Subject, theme_id: int) -> list[str | int]:
        params: dict[str, int] = {"theme": theme_id, "page": 1}
        problem_ids = []
        while True:
            logging.info(f'Getting theme {theme_id}, page={params["page"]}')
            response_text = await self._get(f"{self.base_url(subject)}/test", params=params)
            soup = BeautifulSoup(response_text, "html.parser")
            ids = soup.find_all("span", class_="prob_nums")
            if not ids:
                break
            ids = [i.find("a").text for i in ids]
            problem_ids.extend(ids)
            params["page"] += 1
        return problem_ids

    async def get_catalog(self, subject: Subject) -> list[dict[str, Any]]:
        """
        Получение каталога заданий для определенного предмета

        :param subject: Наименование предмета
        """

        text = await self._get(f"{self.base_url(subject)}/prob_catalog")
        soup = BeautifulSoup(text, "html.parser")
        catalog = []
        catalog_result = []

        for i in soup.find_all("div", {"class": "cat_category"}):
            try:
                i["data-id"]
            except IndexError:
                catalog.append(i)

        for topic in catalog[1:]:
            topic_name = topic.find("b", {"class": "cat_name"}).text.split(". ")[1]
            topic_id = topic.find("b", {"class": "cat_name"}).text.split(". ")[0]
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
                            "category_name": i.find("a", {"class": "cat_name"}).text,
                        }
                        for i in topic.find("div", {"class": "cat_children"}).find_all(
                            "div", {"class": "cat_category"}
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


async def test() -> None:
    async with SdamGIA(gia_type=GitType.EGE, subject=Subject.MATH) as sdamgia:
        subject = Subject.MATH
        # test_id = 435345
        # print(await sdamgia.generate_pdf(subject, test_id, pdf="m", answers=True))
        # print(await sdamgia.get_test_by_id(subject, test_id))

        problem_id = 26596
        data = await sdamgia.get_problem_by_id(subject, problem_id, recognize_text=False)
        # data = await sdamgia.search(Subject.INFORMATICS, query="исполнитель робот")
        print(json.dumps(data, indent=4, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(test())
