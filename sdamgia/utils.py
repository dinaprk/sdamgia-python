import os
import subprocess

from .enums import GiaType, Subject
from .types import Problem, _base_url


def base_url(gia_type: GiaType, subject: Subject) -> str:
    """Create base url for certain GIA type and subject."""
    return _base_url(gia_type=gia_type, subject=subject)


def create_pdf_from_html(html: str, output_file_path: str) -> None:
    """Create a PDF file from HTML content.

    Args:
        html: The HTML content from which the PDF will be generated.
        output_file_path: The path to save the generated PDF file.
    """
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


def create_problem_pdf_html(problem: Problem) -> None:
    """Create a PDF file from HTML representation of a problem."""
    create_pdf_from_html(
        html=f"<b>Условие:</b>{problem.condition.html}{problem.solution.html}",  # type: ignore[union-attr]
        output_file_path=f"{problem.subject}-{problem.gia_type}-{problem.id}.pdf",
    )


def create_problem_pdf_tex(problem: Problem) -> None:
    """Create a PDF file from LaTeX representation of a problem."""
    tex = (
        "\\documentclass{article}\n"
        "\\usepackage[T2A]{fontenc}\n\\usepackage[utf8]{inputenc}\n"
        "\\usepackage[russian,english]{babel}\n"
        "\\usepackage{amsmath}\n\\usepackage{amssymb}\n"
        "\\usepackage{hyperref}\n\\hypersetup{colorlinks=true,urlcolor=blue}\n\n"
        "\\begin{document}\n"
        f"\\section{{\\href{{{problem.id}}}{{{problem.url}}}\n\n"
        "\\subsection{Условие:}\n\n"
        f"{problem.condition.text}\n\n"  # type: ignore[union-attr]
        "\\subsection{Решение:}\n\n"
        f"{problem.solution.text}\n\n"  # type: ignore[union-attr]
        "\\end{document}"
    )

    temp_file_path = f"{problem.id}-{problem.subject}.tex"
    pdf_file_path = temp_file_path.replace(".tex", ".pdf")
    with open(temp_file_path, "w") as f:
        f.write(tex)
    try:
        subprocess.Popen(["/usr/bin/pdflatex", temp_file_path, "-o", pdf_file_path])
    finally:
        os.remove(temp_file_path)
