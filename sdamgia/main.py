import asyncio
import io
import json
import os
import subprocess
from time import sleep

import PIL
import aiohttp
import cairosvg
from PIL import Image
from bs4 import BeautifulSoup
import requests

from pix2tex.cli import LatexOCR

from exceptions import IncorrectGiaTypeException, ProbBlockIsNoneException


class SdamGIA:
    def __init__(self, gia_type: str = 'oge'):
        if gia_type.lower() not in ['oge', 'ege']:
            raise IncorrectGiaTypeException(gia_type)

        self.GIA_TYPE = gia_type

        self.BASE_DOMAIN = 'sdamgia.ru'

        self.SUBJECT_BASE_URL = {
            'math': f'https://math-{gia_type}.{self.BASE_DOMAIN}', 'mathb': f'https://mathb-ege.{self.BASE_DOMAIN}',
            'phys': f'https://phys-{gia_type}.{self.BASE_DOMAIN}',
            'inf': f'https://inf-{gia_type}.{self.BASE_DOMAIN}',
            'rus': f'https://rus-{gia_type}.{self.BASE_DOMAIN}',
            'bio': f'https://bio-{gia_type}.{self.BASE_DOMAIN}',
            'en': f'https://en-{gia_type}.{self.BASE_DOMAIN}',
            'chem': f'https://chem-{gia_type}.{self.BASE_DOMAIN}',
            'geo': f'https://geo-{gia_type}.{self.BASE_DOMAIN}',
            'soc': f'https://soc-{gia_type}.{self.BASE_DOMAIN}',
            'de': f'https://de-{gia_type}.{self.BASE_DOMAIN}',
            'fr': f'https://fr-{gia_type}.{self.BASE_DOMAIN}',
            'lit': f'https://lit-{gia_type}.{self.BASE_DOMAIN}',
            'sp': f'https://sp-{gia_type}.{self.BASE_DOMAIN}',
            'hist': f'https://hist-{gia_type}.{self.BASE_DOMAIN}',
        }
        # self.tesseract_src = 'tesseract'

        # proxy_url = "85.26.146.169:80"
        # proxy_host, proxy_port = proxy_url.split(':')

        # Set up the proxy information in the requests library format
        # self.proxies = {
        #     'http': f'http://{proxy_host}:{proxy_port}',
        #     'https': f'http://{proxy_host}:{proxy_port}'
        # }

    def __replace_text_with_symbols(self, text: str):
        return text.replace(r'\angle', '∠').replace('градусов', '°').replace('плюс', '+').replace('−', '-')

    def get_problem_by_id(self, subject, id):
        """
        Получение информации о задаче по ее идентификатору

        :param subject: Наименование предмета
        :type subject: str

        :param id: Идентификатор задачи
        :type subject: str
        """
        print(f'{self.SUBJECT_BASE_URL[subject]}/problem?id={id}')
        doujin_page = requests.get(
            f'{self.SUBJECT_BASE_URL[subject]}/problem?id={id}')
        soup = BeautifulSoup(doujin_page.text.replace("\xa0", " "), 'html.parser')

        probBlock = soup.find('div', {'class': 'prob_maindiv'})
        # print(probBlock)
        if probBlock is None:
            return "ProbBlock is None"
        # print(probBlock)
        condition_html = str(probBlock.find_all('div', class_="pbody")[0]).replace('/get_file',
                                                                                   f'{self.SUBJECT_BASE_URL[subject]}/get_file').replace(
            '−', '-')
        solution_html = str(probBlock.find_all('div', class_="pbody")[1]).replace('/get_file',
                                                                                  f'{self.SUBJECT_BASE_URL[subject]}/get_file').replace(
            '−', '-')

        for i in probBlock.find_all('img'):
            if not 'sdamgia.ru' in i['src']:
                i['src'] = self.SUBJECT_BASE_URL[subject] + i['src']

        URL = f'{self.SUBJECT_BASE_URL[subject]}/problem?id={id}'
        TOPIC_ID = ' '.join(probBlock.find(
            'span', {'class': 'prob_nums'}).text.split()[1:][:-2])
        ID = id

        CONDITION, SOLUTION, ANSWER, ANALOGS = {}, {}, '', []
        try:
            soup = BeautifulSoup(doujin_page.text.replace("\xa0", " "), 'html.parser')
            condition_element = soup.find_all('div', {'class': 'pbody'})[0]
            CONDITION = {'text': condition_element.text.replace('−', '-'),
                         'images': [i['src'] for i in condition_element.find_all('img')]
                         }
        except IndexError:
            pass

        try:
            # soup = BeautifulSoup(doujin_page.text.replace("\xa0", " "), 'html.parser')
            # print(soup)
            solution_element = probBlock.find_all('div', class_='pbody')[1]
            # text = solution_element.get_text(strip=True)
            # print(text)

            # Replace img tags with their alt attributes
            # print(len(solution_element.find_all('img', class_='tex')))
            # for img_tag in list(solution_element.find_all('img', class_='tex')):
            #     # print(type(img_tag), img_tag)
            #     alt_attr = img_tag.get('alt')
            #     img_tag.insert_after(alt_attr)
            #     img_tag.decompose()
            # text = ''
            # for img_tag in solution_element.find_all('img', class_='tex')[1:]:
            #     text += img_tag.text
            #     print(img_tag.text)
            # alt_attr = img_tag['alt']
            # text += alt_attr
            # img_tag.replace_with(str(alt_attr))
            #
            # print(solution_element)
            SOLUTION = {'text': solution_element.text.replace('−', '-'),
                        'images': [i['src'] for i in solution_element.find_all('img')]
                        }
            # SOLUTION['text'] = text
        except IndexError:
            pass
        except AttributeError:
            pass

        try:
            ANSWER = probBlock.find(
                'div', {'class': 'answer'}).text.replace('Ответ: ', '').replace('−', '-')
        except IndexError:
            pass
        except AttributeError:
            pass

        try:
            ANALOGS = [i.text for i in probBlock.find(
                'div', {'class': 'minor'}).find_all('a')]
            if 'Все' in ANALOGS:
                ANALOGS.remove('Все')
        except IndexError:
            pass
        except AttributeError:
            pass

        return {'id': ID, 'topic': TOPIC_ID, 'condition_html': condition_html, "solution_html": solution_html,
                'condition': CONDITION, 'solution': SOLUTION, 'answer': ANSWER, 'analogs': ANALOGS, 'url': URL}

    async def get_problem_latex_by_id(self, subject: str, id: str, session: aiohttp.ClientSession):
        # print(f'{self._SUBJECT_BASE_URL[subject]}/problem?id={id}')
        async with session.get(f'{self.SUBJECT_BASE_URL[subject]}/problem?id={id}') as page_html:
            soup = BeautifulSoup((await page_html.text()).replace("\xa0", " "),
                                 'lxml')  # .replace("\xa0", " "), 'html.parser')

        prob_block = soup.find('div', class_='prob_maindiv')
        # print(probBlock)
        if prob_block is None:
            raise ProbBlockIsNoneException
        # print(probBlock)
        # print(prob_block)
        # print(len(prob_block.find_all('div', class_='proby')))
        # condition_html = str(prob_block.find_all('div', class_="pbody")[0]).replace('/get_file',
        #                                                                            f'{self._SUBJECT_BASE_URL[subject]}/get_file').replace(
        #     '−', '-')
        # solution_html = str(prob_block.find_all('div', class_="pbody")[1]).replace('/get_file',
        #                                                                           f'{self._SUBJECT_BASE_URL[subject]}/get_file').replace(
        #     '−', '-')
        #
        #

        for i in prob_block.find_all('img'):
            if not 'sdamgia.ru' in i['src']:
                i['src'] = self.SUBJECT_BASE_URL[subject] + i['src']

        problem_url = f'{self.SUBJECT_BASE_URL[subject]}/problem?id={id}'
        topic_id = ' '.join(prob_block.find(
            'span', {'class': 'prob_nums'}).text.split()[1:][:-2])
        problem_id = id

        condition, solution, answer, problem_analogs = {}, {}, '', []
        try:
            condition_element = soup.find_all('div', {'class': 'pbody'})[0]

            condition_html = str(condition_element)

            # condition_element = BeautifulSoup(''.join([str(i) for i in condition_element]), 'lxml')
            condition_image_links = [i.get('src') for i in condition_element.find_all('img', class_='tex')]

            condition_tex_dict = await self.get_latex_from_url_list(condition_image_links, session)

            for img_tag in condition_element.find_all('img', class_='tex'):
                img_tag.replace_with(condition_tex_dict.get(img_tag.get('src')))
            condition = {'text': condition_element.text.replace('−', '-'),
                         'html': condition_html,
                         'images': condition_image_links + [i.get('src') for i in condition_element.find_all('img')]
                         }
        except IndexError:
            pass

        try:
            solution_element = prob_block.find('div', class_='solution')
            if solution_element is None:
                solution_element = prob_block.find_all('div', class_='pbody')[1]

            solution_html = str(solution_element)

            solution_image_links = [i.get('src') for i in solution_element.find_all('img', class_='tex')]

            solution_tex_dict = await self.get_latex_from_url_list(solution_image_links, session)

            for img_tag in solution_element.find_all('img', class_='tex'):
                img_tag.replace_with(solution_tex_dict.get(img_tag.get('src')))
            solution = {'text': solution_element.text.replace('Решение. ', '').strip(),
                        'html': solution_html,
                        'images': solution_image_links + [i.get('src') for i in solution_element.find_all('img')]
                        }
            # SOLUTION['text'] = text
        except IndexError:
            pass
        except AttributeError:
            pass

        try:
            answer = prob_block.find(
                'div', {'class': 'answer'}).text.replace('Ответ: ', '')
        except IndexError:
            pass
        except AttributeError:
            pass

        return {'condition': condition, 'solution': solution, 'answer': answer, 'problem_id': problem_id,
                'topic_id': topic_id, 'analogs': problem_analogs, 'url': problem_url, 'subject': subject,
                "gia_type": self.GIA_TYPE}

    async def get_image_object_from_url(self, url: str, session: aiohttp.ClientSession):
        async with session.get(url) as response:
            byte_string = await response.text()
            png_bytes = cairosvg.svg2png(bytestring=byte_string)
            buffer = io.BytesIO(png_bytes)
            image = Image.open(buffer)
            # svg_path = '/'.join(url.split('/')[:-2])
            # print(svg_path)
            return url, image

    async def image_object_to_latex(self, image: PIL.Image) -> str:
        model = LatexOCR()
        return "$%s$" % model(image)

    async def get_latex_from_url_list(self, image_links, session: aiohttp.ClientSession):
        condition_image_tasks = [asyncio.create_task(self.get_image_object_from_url(url, session)) for url in
                                 image_links]
        images_data = await asyncio.gather(*condition_image_tasks)

        string_tex_list = [await self.image_object_to_latex(url_and_image_pair[1]) for url_and_image_pair in images_data]

        # string_tex_list = [(images_data[i][0], tex) for i, tex in enumerate(string_tex_list)]
        # print(string_tex_list)
        # tex_dict = {url: tex for url, tex in string_tex_list}
        tex_dict = {images_data[i][0]: string_tex_list[i] for i in range(len(images_data))}
        return tex_dict

    def search(self, subject, request, page=1):
        """
        Поиск задач по запросу

        :param subject: Наименование предмета
        :type subject: str

        :param request: Запрос
        :type request: str

        :param page: Номер страницы поиска
        :type page: int
        """
        doujin_page = requests.get(
            f'{self.SUBJECT_BASE_URL[subject]}/search?search={request}&page={str(page)}')
        soup = BeautifulSoup(doujin_page.content, 'html.parser')
        return [i.text.split()[-1] for i in soup.find_all('span', {'class': 'prob_nums'})]

    def get_test_by_id(self, subject, testid):
        """
        Получение списка задач, включенных в тест

        :param subject: Наименование предмета
        :type subject: str

        :param testid: Идентификатор теста
        :type testid: str
        """
        doujin_page = requests.get(
            f'{self.SUBJECT_BASE_URL[subject]}/test?id={testid}')
        soup = BeautifulSoup(doujin_page.content, 'html.parser')
        return [i.text.split()[-1] for i in soup.find_all('span', {'class': 'prob_nums'})]

    def get_category_by_id(self, subject, categoryid, page=1):
        """
        Получение списка задач, включенных в категорию

        :param subject: Наименование предмета
        :type subject: str

        :param categoryid: Идентификатор категории
        :type categoryid: str

        :param page: Номер страницы поиска
        :type page: int
        """

        doujin_page = requests.get(
            f'{self.SUBJECT_BASE_URL[subject]}/test?&filter=all&theme={categoryid}&page={page}')
        soup = BeautifulSoup(doujin_page.content, 'html.parser')
        return [i.text.split()[-1] for i in soup.find_all('span', {'class': 'prob_nums'})]

    def get_catalog(self, subject):
        """
        Получение каталога заданий для определенного предмета

        :param subject: Наименование предмета
        :type subject: str
        """

        doujin_page = requests.get(
            f'{self.SUBJECT_BASE_URL[subject]}/prob_catalog')
        soup = BeautifulSoup(doujin_page.content, 'html.parser')
        catalog = []
        CATALOG = []

        for i in soup.find_all('div', {'class': 'cat_category'}):
            try:
                i['data-id']
            except:
                catalog.append(i)

        for topic in catalog[1:]:
            TOPIC_NAME = topic.find(
                'b', {'class': 'cat_name'}).text.split('. ')[1]
            TOPIC_ID = topic.find(
                'b', {'class': 'cat_name'}).text.split('. ')[0]
            if TOPIC_ID[0] == ' ':
                TOPIC_ID = TOPIC_ID[2:]
            if TOPIC_ID.find('Задания ') == 0:
                TOPIC_ID = TOPIC_ID.replace('Задания ', '')

            CATALOG.append(
                dict(
                    topic_id=TOPIC_ID,
                    topic_name=TOPIC_NAME,
                    categories=[
                        dict(
                            category_id=i['data-id'],
                            category_name=i.find(
                                'a', {'class': 'cat_name'}).text
                        )
                        for i in
                        topic.find('div', {'class': 'cat_children'}).find_all('div', {'class': 'cat_category'})]
                )
            )

        return CATALOG

    def get_fipi_catalog(self, subject):
        """
        Получение каталога заданий для определенного предмета

        :param subject: Наименование предмета
        :type subject: str
        """

        doujin_page = requests.get(
            f'{self.SUBJECT_BASE_URL[subject]}/prob_catalog')
        soup = BeautifulSoup(doujin_page.content, 'html.parser')
        catalog = []
        CATALOG = []

        for i in soup.find_all('div', {'class': 'cat_category'}):
            try:
                i['data-id']
            except:
                catalog.append(i)

        for topic in catalog[1:]:
            TOPIC_NAME = topic.find(
                'b', {'class': 'cat_name'}).text.split('. ')[1]
            TOPIC_ID = topic.find(
                'b', {'class': 'cat_name'}).text.split('. ')[0]
            if TOPIC_ID[0] == ' ':
                TOPIC_ID = TOPIC_ID[2:]
            if TOPIC_ID.find('Задания ') == 0:
                TOPIC_ID = TOPIC_ID.replace('Задания ', '')

            CATALOG.append(
                dict(
                    topic_id=TOPIC_ID,
                    topic_name=TOPIC_NAME,
                    categories=[
                        dict(
                            category_id=i['data-id'],
                            category_name=i.find(
                                'a', {'class': 'cat_name'}).text.replace('(банк ФИПИ)', '').strip()
                        )
                        for i in
                        topic.find('div', {'class': 'cat_children'}).find_all('div', {'class': 'cat_category'}) if
                        "(банк ФИПИ)" in i.text]
                )
            )

        return CATALOG

    def get_category_problems(self, subject, categoty_id):
        response = requests.get(f'{self.SUBJECT_BASE_URL[subject]}/test?filter=all&category_id={categoty_id}')

        soup = BeautifulSoup(response.text, 'html.parser')
        problem_ids = [int(i.find('a').get('href').replace('/problem?id=', '')) for i in
                       soup.find_all('span', class_='prob_nums')]
        return problem_ids

    def generate_test(self, subject, problems=None):
        """
        Генерирует тест по заданным параметрам

        :param subject: Наименование предмета
        :type subject: str

        :param problems: Список заданий
        По умолчанию генерируется тест, включающий по одной задаче из каждого задания предмета.
        Так же можно вручную указать одинаковое количество задач для каждого из заданий: {'full': <кол-во задач>}
        Указать определенные задания с определенным количеством задач для каждого: {<номер задания>: <кол-во задач>, ... }
        :type problems: dict
        """

        if problems is None:
            problems = {'full': 1}

        if 'full' in problems:
            params = {f'prob{i}': problems['full'] for i in range(
                1, len(self.get_catalog(subject)) + 1)}
        else:
            params = {f'prob{i}': problems[i] for i in problems}
        # print(params)
        return requests.get(f'{self.SUBJECT_BASE_URL[subject]}/test?a=generate', params=params,
                            allow_redirects=False).headers['location'].split('id=')[1].split('&nt')[0]

    def generate_pdf(self, subject: str, testid: str, solution='', nums='',
                     answers='', key='', crit='',
                     instruction='', col='', tt='', pdf=True):
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

        params = dict(
            id=testid,
            print="true",
            pdf=pdf,
            sol=solution,
            num=nums,
            ans=answers,
            key=key,
            crit=crit,
            pre=instruction,
            dcol=col
        )

        return self.SUBJECT_BASE_URL[subject] + requests.get(f'{self.SUBJECT_BASE_URL[subject]}/test', params=params,
                                                             allow_redirects=False).headers['location']


def make_pdf_from_html(html: str, output_file_path: str):
    if ("<html>" or "body") not in html:
        html = "<html><body>%s</body></html>" % html
    ps = subprocess.Popen(["echo", "<html><body>%s</body></html>" % html], stdout=subprocess.PIPE)
    # subprocess.check_output(["pandoc", '--standalone', "-", "-f", "html", "-o", output_file_path.replace('.pdf', '.tex'), "-t", "latex", "-V", "fontenc=T2A"],
    #                         stdin=ps.stdout)
    subprocess.check_output(["pandoc", "-", "-f", "html", "-o", output_file_path, "-t", "latex", "-V", "fontenc=T2A"],
                            stdin=ps.stdout)


def make_problem_pdf_from_data(data: dict):
    make_pdf_from_html("<b>Условие:</b>" + data['condition_html'] + data['solution_html'],
                       output_file_path=f'{data["subject"]}-{data["problem_id"]}.pdf')


def create_pdf_from_problem_data(data: dict):
    tex = "\documentclass{article}\n" + "\\usepackage[T2A]{fontenc}\n\\usepackage[utf8]{inputenc}\n\\usepackage[russian]{babel}\n" +\
          "\\begin{document}\n" + "\\section{%s}\n\n" % data.get('id') + data.get('condition').get('text') + '\n\n' + \
          "\\subsection{Решение:}\n\n" + data.get('solution').get('text') + "\n\n\\end{document}"
    print(tex)
    temp_file_path = f"{data.get('id')}-{data.get('subject')}.tex"
    pdf_file_path = f"{data.get('id')}-{data.get('subject')}.pdf"
    with open(temp_file_path, 'wt') as f:
        f.write(tex)
    sleep(10)
    try:
        subprocess.Popen(['pdflatex', temp_file_path, '-o', pdf_file_path])
    finally:
        os.remove(temp_file_path)
    # ps = subprocess.Popen(["echo", tex], stdout=subprocess.PIPE)
    # subprocess.check_output(["pandoc", '--standalone', "-", "-f", "html", "-o", output_file_path.replace('.pdf', '.tex'), "-t", "latex", "-V", "fontenc=T2A"],
    #                         stdin=ps.stdout)
    # subprocess.check_output(["pandoc", "-", "-f", "html", "-o", output_file_path, "-t", "latex", "-V", "fontenc=T2A"],
    #                         stdin=ps.stdout)


async def main():
    async with aiohttp.ClientSession() as session:
        # image = await sdamgia.get_image_from_url('https://oge.sdamgia.ru/formula/svg/9f/9f566993380f9ec1cf063c2acb4d3d98.svg',
        #                            session)
        # image.show()
        subject = 'math'
        id = '311309'
        data = (await sdamgia.get_problem_latex_by_id(subject, id, session))
        print(json.dumps(data, indent=4, ensure_ascii=False))
        # create_pdf_from_problem_data(data)
        # print(data['condition']['text'])
        # print(data['solution']['text'])


if __name__ == '__main__':
    sdamgia = SdamGIA()
    # subject = 'math'
    # id = '642419'
    asyncio.run(main())
    # data = sdamgia.get_problem_by_id(subject, id)
    # print(json.dumps(data, indent=4, ensure_ascii=False))
    # make_problem_pdf_from_data(data)
