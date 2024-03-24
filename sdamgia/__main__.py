import asyncio
import io
import json
import logging
import unicodedata
from typing import Any, Literal
from urllib.parse import urljoin

import aiohttp
import requests
from bs4 import BeautifulSoup
from cairosvg import svg2png
from PIL import Image
from PIL.Image import Image as ImageType

from sdamgia.exceptions import ProblemBlockNotFoundError


class SdamGIA:
    def __init__(self, gia_type: str = "oge"):
        gia_type = gia_type.lower()
        if gia_type not in ["oge", "ege"]:
            raise ValueError(f'gia_type can be "oge" or "ege", not {gia_type}')

        self.GIA_TYPE = gia_type

        self.BASE_DOMAIN = "sdamgia.ru"

        subjects = [
            "math",
            "phys",
            "inf",
            "rus",
            "bio",
            "en",
            "chem",
            "geo",
            "soc",
            "de",
            "rf",
            "lit",
            "sp",
            "hist",
        ]
        if gia_type == "ege":
            subjects.append("mathb")
        self.SUBJECT_BASE_URL = {
            subject: f"https://{subject}-{gia_type}.{self.BASE_DOMAIN}" for subject in subjects
        }

        self._latex_ocr_model = None

    @staticmethod
    async def get_image_from_url(url: str, session: aiohttp.ClientSession) -> ImageType:
        async with session.get(url) as response:
            byte_string = await response.text()
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
        return f"${self._latex_ocr_model(image)}$"

    async def get_latex_from_url_list(
        self, image_links: list[str], session: aiohttp.ClientSession
    ) -> dict[str, str]:
        condition_image_tasks = [
            asyncio.create_task(self.get_image_from_url(url, session)) for url in image_links
        ]
        images_data: tuple[ImageType] = await asyncio.gather(*condition_image_tasks)
        string_tex_list = tuple(map(self.image_to_tex, images_data))
        return {image_links[i]: string_tex_list[i] for i in range(len(images_data))}

    async def get_problem_by_id(
        self,
        subject: str,
        problem_id: str,
        session: aiohttp.ClientSession,
        recognize_text: bool = False,
    ) -> dict[str, Any]:
        async with session.get(
            f"{self.SUBJECT_BASE_URL[subject]}/problem?id={problem_id}"
        ) as page_html:
            soup = BeautifulSoup((await page_html.text()).replace("\xa0", " "), "lxml")

        prob_block = soup.find("div", {"class": "prob_maindiv"})

        if prob_block is None:
            raise ProblemBlockNotFoundError()

        for i in prob_block.find_all("img"):
            if self.BASE_DOMAIN not in i["src"]:
                i["src"] = self.SUBJECT_BASE_URL[subject] + i["src"]

        problem_url = f"{self.SUBJECT_BASE_URL[subject]}/problem?id={problem_id}"
        topic_id = " ".join(prob_block.find("span", {"class": "prob_nums"}).text.split()[1:][:-2])

        try:
            condition_element = soup.find_all("div", {"class": "pbody"})[0]

            condition_html = str(condition_element)

            condition_image_links = [
                i.get("src") for i in condition_element.find_all("img", class_="tex")
            ]

            if recognize_text:
                condition_tex_dict = await self.get_latex_from_url_list(
                    condition_image_links, session
                )

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
            solution_element = prob_block.find("div", class_="solution")
            if solution_element is None:
                solution_element = prob_block.find_all("div", class_="pbody")[1]

            solution_html = str(solution_element)

            solution_image_links = [
                i.get("src") for i in solution_element.find_all("img", class_="tex")
            ]

            if recognize_text:
                solution_tex_dict = await self.get_latex_from_url_list(
                    solution_image_links, session
                )

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
            answer = prob_block.find("div", {"class": "answer"}).text.replace("Ответ: ", "")
        except (IndexError, AttributeError):
            answer = ""

        condition["text"] = unicodedata.normalize("NFKC", condition["text"])
        solution["text"] = unicodedata.normalize("NFKC", solution["text"])

        problem_analogs = [
            i.get("href").replace("/problem?id=", "")
            for i in prob_block.find_all("div", class_="minor")[0].find_all("a")
            if problem_id not in i.get("href")
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
            "subject": subject,
            "gia_type": self.GIA_TYPE,
        }

    async def search(self, subject: str, query: str) -> list[str]:
        """
        Поиск задач по запросу

        :param subject: Наименование предмета
        :param query: Запрос
        """
        problem_ids = []
        params = {"search": query, "page": 1}
        async with aiohttp.ClientSession() as session:
            while True:
                async with session.get(
                    urljoin(self.SUBJECT_BASE_URL[subject], "/search"), params=params
                ) as response:
                    soup = BeautifulSoup(await response.text(), "lxml")
                    ids = [
                        i.text.split()[-1] for i in soup.find_all("span", {"class": "prob_nums"})
                    ]
                    if len(ids) == 0:
                        break
                    problem_ids.extend(ids)
        return problem_ids

    def get_test_by_id(self, subject: str, test_id: str):
        """
        Получение списка задач, включенных в тест

        :param subject: Наименование предмета
        :param test_id: Идентификатор теста
        """
        doujin_page = requests.get(f"{self.SUBJECT_BASE_URL[subject]}/test?id={test_id}")
        soup = BeautifulSoup(doujin_page.content, "html.parser")
        return [i.text.split()[-1] for i in soup.find_all("span", {"class": "prob_nums"})]

    async def get_theme_by_id(
        self, subject: str, theme_id: str, session: aiohttp.ClientSession
    ) -> list[str | int]:
        params = {"theme": theme_id, "page": 1}
        problem_ids = []
        while True:
            logging.info(f'Getting theme {theme_id}, page={params["page"]}')
            async with session.get(
                urljoin(self.SUBJECT_BASE_URL[subject], "/test"), params=params
            ) as response:
                soup = BeautifulSoup(await response.text(), "html.parser")
                ids = soup.find_all("span", class_="prob_nums")
                if not ids:
                    break
                ids = [i.find("a").text for i in ids]
                problem_ids.extend(ids)
            params["page"] += 1
        return problem_ids

    def get_catalog(self, subject: str) -> list[dict[str, Any]]:
        """
        Получение каталога заданий для определенного предмета

        :param subject: Наименование предмета
        """

        doujin_page = requests.get(f"{self.SUBJECT_BASE_URL[subject]}/prob_catalog")
        soup = BeautifulSoup(doujin_page.content, "html.parser")
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

    def generate_test(self, subject: str, problems: dict[str, int] | None = None) -> str:
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
                f"prob{i}": problems["full"] for i in range(1, len(self.get_catalog(subject)) + 1)
            }
        else:
            params = {f"prob{i}": problems[i] for i in problems}

        return (
            requests.get(
                f"{self.SUBJECT_BASE_URL[subject]}/test?a=generate",
                params=params,
                allow_redirects=False,
            )
            .headers["location"]
            .split("id=")[1]
            .split("&nt")[0]
        )

    def generate_pdf(
        self,
        subject: str,
        test_id: str,
        solution: bool = False,
        nums: bool = False,
        answers: bool = False,
        key: bool = False,
        crit: bool = False,
        instruction: bool = False,
        col: str = "",
        tt: str = "",
        pdf: Literal["h", "z", "m"] = "z",
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
            "sol": solution,
            "num": nums,
            "ans": answers,
            "key": key,
            "crit": crit,
            "pre": instruction,
            "dcol": col,
            "tt": tt,
        }

        return (
            self.SUBJECT_BASE_URL[subject]
            + requests.get(
                f"{self.SUBJECT_BASE_URL[subject]}/test", params=params, allow_redirects=False
            ).headers["location"]
        )


async def test() -> None:
    async with aiohttp.ClientSession() as session:
        sdamgia = SdamGIA(gia_type="ege")
        subject = "math"
        id = "26596"
        # data = await sdamgia.get_problem_latex_by_id(subject, id, session)
        data = await sdamgia.get_problem_by_id(subject, id, session, recognize_text=False)
        print(json.dumps(data, indent=4, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(test())
