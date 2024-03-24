import os
import subprocess
from time import sleep


def make_pdf_from_html(html: str, output_file_path: str) -> None:
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


def make_problem_pdf_from_data(data: dict) -> None:
    make_pdf_from_html(
        "<b>Условие:</b>" + data["condition_html"] + data["solution_html"],
        output_file_path=f'{data["subject"]}-{data["problem_id"]}.pdf',
    )


def create_pdf_from_problem_data(data: dict) -> None:
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
