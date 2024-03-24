import asyncio
import io
import json
import logging
import os
import subprocess
import unicodedata
from time import sleep
from urllib.parse import urljoin

import aiohttp
import cairosvg
import PIL
import requests
from bs4 import BeautifulSoup
from PIL import Image

from pix2tex.cli import LatexOCR
from sdamgia.exceptions import IncorrectGiaTypeError, ProbBlockIsNoneError


class SdamGIA:
    def __init__(self, gia_type: str = "oge"):
        gia_type = gia_type.lower()
        if gia_type not in ["oge", "ege"]:
            raise IncorrectGiaTypeError(gia_type)

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

    async def get_problem_latex_by_id(
        self, subject: str, problem_id: str, session: aiohttp.ClientSession
    ) -> dict:
        async with session.get(
            f"{self.SUBJECT_BASE_URL[subject]}/problem?id={problem_id}"
        ) as page_html:
            soup = BeautifulSoup(
                (await page_html.text()).replace("\xa0", " "), "lxml"
            )  # .replace("\xa0", " "), 'html.parser')

        prob_block = soup.find("div", class_="prob_maindiv")

        if prob_block is None:
            raise ProbBlockIsNoneError()

        # print(len(prob_block.find_all('div', class_='proby')))
        # condition_html = (
        #     str(prob_block.find_all("div", class_="pbody")[0])
        #     .replace("/get_file", f"{self._SUBJECT_BASE_URL[subject]}/get_file")
        #     .replace("−", "-")
        # )
        # solution_html = (
        #     str(prob_block.find_all("div", class_="pbody")[1])
        #     .replace("/get_file", f"{self._SUBJECT_BASE_URL[subject]}/get_file")
        #     .replace("−", "-")
        # )

        for i in prob_block.find_all("img"):
            if "sdamgia.ru" not in i["src"]:
                i["src"] = self.SUBJECT_BASE_URL[subject] + i["src"]

        problem_url = f"{self.SUBJECT_BASE_URL[subject]}/problem?id={problem_id}"
        topic_id = " ".join(prob_block.find("span", {"class": "prob_nums"}).text.split()[1:][:-2])

        condition, solution, answer, problem_analogs = {}, {}, "", []
        try:
            condition_element = soup.find_all("div", {"class": "pbody"})[0]

            condition_html = str(condition_element)

            # condition_element = BeautifulSoup("".join([str(i) for i in condition_element]),
            # "lxml")
            condition_image_links = [
                i.get("src") for i in condition_element.find_all("img", class_="tex")
            ]

            condition_tex_dict = await self.get_latex_from_url_list(condition_image_links, session)

            for img_tag in condition_element.find_all("img", class_="tex"):
                img_tag.replace_with(condition_tex_dict.get(img_tag.get("src")))
            condition = {
                "text": condition_element.text.replace("−", "-"),
                "html": condition_html,
                "images": condition_image_links
                + [i.get("src") for i in condition_element.find_all("img")],
            }
        except IndexError:
            pass

        try:
            solution_element = prob_block.find("div", class_="solution")
            if solution_element is None:
                solution_element = prob_block.find_all("div", class_="pbody")[1]

            solution_html = str(solution_element)

            solution_image_links = [
                i.get("src") for i in solution_element.find_all("img", class_="tex")
            ]

            solution_tex_dict = await self.get_latex_from_url_list(solution_image_links, session)

            for img_tag in solution_element.find_all("img", class_="tex"):
                img_tag.replace_with(solution_tex_dict.get(img_tag.get("src")))
            solution = {
                "text": solution_element.text.replace("Решение. ", "").strip(),
                "html": solution_html,
                "images": solution_image_links
                + [i.get("src") for i in solution_element.find_all("img")],
            }
            # SOLUTION['text'] = text
        except IndexError:
            pass
        except AttributeError:
            pass

        try:
            answer = prob_block.find("div", {"class": "answer"}).text.replace("Ответ: ", "")
        except IndexError:
            pass
        except AttributeError:
            pass

        condition["text"] = unicodedata.normalize("NFKC", condition["text"])
        solution["text"] = unicodedata.normalize("NFKC", solution["text"])

        problem_analogs = sorted([i for i in problem_analogs if all(j.isdigit() for j in i)])

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

    async def get_image_object_from_url(
        self, url: str, session: aiohttp.ClientSession
    ) -> tuple[str, PIL.Image]:
        async with session.get(url) as response:
            byte_string = await response.text()
            png_bytes = cairosvg.svg2png(bytestring=byte_string)
            buffer = io.BytesIO(png_bytes)
            image = Image.open(buffer)
            # svg_path = '/'.join(url.split('/')[:-2])
            # print(svg_path)
            return url, image

    @staticmethod
    async def image_object_to_latex(self, image: PIL.Image) -> str:
        model = LatexOCR()
        return "$%s$" % model(image)

    async def get_latex_from_url_list(self, image_links, session: aiohttp.ClientSession):
        condition_image_tasks = [
            asyncio.create_task(self.get_image_object_from_url(url, session))
            for url in image_links
        ]
        images_data = await asyncio.gather(*condition_image_tasks)

        string_tex_list = [
            await self.image_object_to_latex(url_and_image_pair[1])
            for url_and_image_pair in images_data
        ]

        # string_tex_list = [(images_data[i][0], tex) for i, tex in enumerate(string_tex_list)]
        # print(string_tex_list)
        # tex_dict = {url: tex for url, tex in string_tex_list}
        return {images_data[i][0]: string_tex_list[i] for i in range(len(images_data))}

    async def scrap_problem_without_text_by_id(
        self, subject: str, problem_id: str, session: aiohttp.ClientSession
    ) -> dict:
        async with session.get(
            f"{self.SUBJECT_BASE_URL[subject]}/problem", params={"id": problem_id}
        ) as page_html:
            soup = BeautifulSoup(
                (await page_html.text()).replace("\xa0", " "), "lxml"
            )  # .replace("\xa0", " ")

        prob_block = soup.find("div", class_="prob_maindiv")
        # print(probBlock)
        if prob_block is None:
            raise ProbBlockIsNoneError()

        for i in prob_block.find_all("img"):
            if "sdamgia.ru" not in i["src"]:
                i["src"] = urljoin(self.SUBJECT_BASE_URL[subject], i["src"])

        problem_url = f"{self.SUBJECT_BASE_URL[subject]}/problem?id={problem_id}"
        topic_id = " ".join(prob_block.find("span", class_="prob_nums").text.split()[1:][:-2])

        condition, solution, answer, problem_analogs = {}, {}, "", []
        try:
            condition_element = soup.find_all("div", class_="pbody")[0]

            condition_html = str(condition_element)

            # condition_element = BeautifulSoup(''.join([str(i) for i in condition_element]),
            # 'lxml')
            condition_image_links = [
                i.get("src") for i in condition_element.find_all("img", class_="tex")
            ]

            condition = {
                "text": "",
                "html": condition_html,
                "images": condition_image_links
                + [i.get("src") for i in condition_element.find_all("img")],
            }
        except IndexError:
            pass

        try:
            solution_element = prob_block.find("div", class_="solution")
            if solution_element is None:
                solution_element = prob_block.find_all("div", class_="pbody")[1]

            solution_html = str(solution_element)

            solution_image_links = [
                i.get("src") for i in solution_element.find_all("img", class_="tex")
            ]

            solution = {
                "text": "",
                "html": solution_html,
                "images": solution_image_links
                + [i.get("src") for i in solution_element.find_all("img")],
            }
            # SOLUTION['text'] = text
        except IndexError:
            pass
        except AttributeError:
            pass

        try:
            answer = prob_block.find("div", class_="answer").text.replace("Ответ: ", "")
        except IndexError:
            pass
        except AttributeError:
            pass

        problem_analogs = [
            i.get("href").replace("/problem?id=", "")
            for i in prob_block.find_all("div", class_="minor")[0].find_all("a")
            if problem_id not in i.get("href")
        ]
        problem_analogs = sorted([i for i in problem_analogs if all(j.isdigit() for j in i)])
        return {
            "problem_id": problem_id,
            "subject": subject,
            "condition": condition,
            "solution": solution,
            "answer": answer,
            "analogs": problem_analogs,
            "topic_id": topic_id,
            "url": problem_url,
            "gia_type": self.GIA_TYPE,
        }

    async def search(self, subject: str, query: str) -> list[str]:
        """
        Поиск задач по запросу

        :param subject: Наименование предмета
        :type subject: str

        :param query: Запрос
        :type query: str
        """
        problem_ids = []
        params = {"search": query, "page": 1}
        async with aiohttp.ClientSession() as session:
            while True:
                async with session.get(
                    urljoin(self.SUBJECT_BASE_URL[subject], "/search", params=params)
                ) as response:
                    soup = BeautifulSoup(await response.text(), "lxml")
                    ids = [
                        i.text.split()[-1] for i in soup.find_all("span", {"class": "prob_nums"})
                    ]
                    if len(ids) == 0:
                        break
                    problem_ids.extend(ids)
        return problem_ids

    def get_test_by_id(self, subject, test_id):
        """
        Получение списка задач, включенных в тест

        :param subject: Наименование предмета
        :type subject: str

        :param test_id: Идентификатор теста
        :type test_id: str
        """
        doujin_page = requests.get(f"{self.SUBJECT_BASE_URL[subject]}/test?id={test_id}")
        soup = BeautifulSoup(doujin_page.content, "html.parser")
        return [i.text.split()[-1] for i in soup.find_all("span", {"class": "prob_nums"})]

    async def get_theme_by_id(
        self, subject: str, theme_id: str, session: aiohttp.ClientSession
    ) -> list[str]:
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

    def get_catalog(self, subject):
        """
        Получение каталога заданий для определенного предмета

        :param subject: Наименование предмета
        :type subject: str
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

    def generate_test(self, subject: str, problems=None) -> str:
        """
        Генерирует тест по заданным параметрам

        :param subject: Наименование предмета
        :type subject: str

        :param problems: Список заданий
        По умолчанию генерируется тест, включающий по одной задаче из каждого задания предмета.
        Так же можно вручную указать одинаковое количество задач для каждогоиз заданий:
        {'full': <кол-во задач>}
        Указать определенные задания с определенным количеством задач для каждого:
        {<номер задания>: <кол-во задач>, ... }
        :type problems: dict
        """

        if problems is None:
            problems = {"full": 1}

        if "full" in problems:
            params = {
                f"prob{i}": problems["full"] for i in range(1, len(self.get_catalog(subject)) + 1)
            }
        else:
            params = {f"prob{i}": problems[i] for i in problems}
        # print(params)
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
        testid: str,
        solution="",
        nums="",
        answers="",
        key="",
        crit="",
        instruction="",
        col="",
        tt="",
        pdf=True,
    ):
        """
        Генерирует pdf версию теста

        :param subject: Наименование предмета
        :type subject: str

        :param testid: Идентифигатор теста
        :type testid: str

        :param solution: Пояснение
        :type solution: bool

        :param nums: № заданий
        :type nums: bool

        :param answers: Ответы
        :type answers: bool

        :param key: Ключ
        :type key: bool

        :param crit: Критерии
        :type crit: bool

        :param instruction: Инструкция
        :type instruction: bool

        :param col: Нижний колонтитул
        :type col: str

        :param tt: Заголовок
        :type tt: str

        :param pdf: Версия генерируемого pdf документа
        По умолчанию генерируется стандартная вертикальная версия
        h - версия с большими полями
        z - версия с крупным шрифтом
        m - горизонтальная версия
        :type pdf: str

        """

        params = {
            "id": testid,
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


def make_pdf_from_html(html: str, output_file_path: str):
    if "<html>" not in html or "body" not in html:
        html = "<html><body>%s</body></html>" % html
    subprocess.Popen(
        [
            "/usr/bin/pandoc",
            "-",
            "-f",
            "html",
            "-o",
            output_file_path,
            "-t",
            "latex",
            "-V",
            "fontenc=T2A",
        ],
        stdin=subprocess.PIPE,
    ).communicate(input=f"<html><body>{html}</body></html>".encode())


def make_problem_pdf_from_data(data: dict):
    make_pdf_from_html(
        "<b>Условие:</b>" + data["condition_html"] + data["solution_html"],
        output_file_path=f'{data["subject"]}-{data["problem_id"]}.pdf',
    )


def create_pdf_from_problem_data(data: dict):
    tex = (
        "\\documentclass{article}\n"
        + "\\usepackage[T2A]{fontenc}\n\\usepackage[utf8]{inputenc}\n\\usepackage[russian]{babel}"
        + "\n\\begin{document}\n"
        + "\\section{%s}\n\n" % data.get("id")
        + data.get("condition").get("text")
        + "\n\n"
        + "\\subsection{Решение:}\n\n"
        + data.get("solution").get("text")
        + "\n\n\\end{document}"
    )
    print(tex)
    temp_file_path = f"{data.get('id')}-{data.get('subject')}.tex"
    pdf_file_path = f"{data.get('id')}-{data.get('subject')}.pdf"
    with open(temp_file_path, "w") as f:
        f.write(tex)
    sleep(10)
    try:
        subprocess.Popen(["/usr/bin/pdflatex", temp_file_path, "-o", pdf_file_path])
    finally:
        os.remove(temp_file_path)


async def test():
    async with aiohttp.ClientSession() as session:
        sdamgia = SdamGIA(gia_type="ege")
        subject = "inf"
        id = "35914"
        data = await sdamgia.scrap_problem_without_text_by_id(subject, id, session)
        print(json.dumps(data, indent=4, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(test())
