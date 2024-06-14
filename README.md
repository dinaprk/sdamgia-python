# 📚 SdamGIA API

[![License](https://img.shields.io/pypi/l/sdamgia?color=green&style=flat-square)](https://github.com/dinaprk/sdamgia-python/blob/master/LICENSE)
[![Version](https://img.shields.io/pypi/v/sdamgia?style=flat-square)](https://pypi.org/project/sdamgia)
[![Python Version](https://img.shields.io/pypi/pyversions/sdamgia?style=flat-square)](https://pypi.org/project/sdamgia)
[![Status](https://img.shields.io/pypi/status/sdamgia?style=flat-square)](https://pypi.org/project/sdamgia)
[![Documentation](https://img.shields.io/github/actions/workflow/status/dinaprk/sdamgia-python/docs.yml?label=docs&style=flat-square)](https://dinaprk.github.io/sdamgia-python)

Unofficial API for SdamGIA educational portal for exam preparation written in Python.

### ⚠️ Important Note

This library retrieves data by parsing HTML because sdamgia uses server-side rendering, which
is not very reliable, but the only method available at the moment. We strive to keep the API
up to date to work as expected. However, if you encounter any issues,
please [report them](https://github.com/dinaprk/sdamgia-python/issues).

Use of this library is at your own risk. Sdamgia explicitly restricts parsing, and we do not
take responsibility for any legal issues that arise from using this library.

## 📦 Installing

**Python 3.10 or above is required.**

### pip

Installing the library with `pip` is quite simple:

```shell
pip install -U sdamgia
```

For full problem text recognition support `pix2tex` extra is required,
which can be installed like so:

```shell
pip install -U "sdamgia[pix2tex]"
```

### poetry

You can add the library as a dependency like so:

```shell
poetry add sdamgia
```

With full text recognition support:

```shell
poetry add sdamgia --extras pix2tex
```

## 🗂️ Problems database structure

To make it easier to understand how the SdamGIA problems database is structured, I suggest using
the following scheme:

```
SdamGIA
└── GIA type, Subject
    ├── Problem catalog
    │   └── Topic
    │       └── Category
    │           └── Problem
    └── Test
        └── Problem
```

Each problem, test, theme or category has its own *unique* integer ID.

## 📃 Documentation

You can find the documentation [here](https://dinaprk.github.io/sdamgia-python).

## 🚀 Basic usage

Because SdamgiaAPI client is asynchronous, it needs to be initialized in asynchronous context:

```python
import asyncio
import dataclasses
import json

from sdamgia import SdamgiaAPI
from sdamgia.types import Problem
from sdamgia.enums import GiaType, Subject


def problem_to_json(problem: Problem) -> str:
    return json.dumps(dataclasses.asdict(problem), indent=4, ensure_ascii=False)


async def main() -> None:
    async with SdamgiaAPI(gia_type=GiaType.EGE, subject=Subject.MATH) as sdamgia:
        problem_id = 26596
        problem = await sdamgia.get_problem(problem_id, subject=Subject.MATH)
        print(problem_to_json(problem))
        print(problem.url)  # https://math-ege.sdamgia.ru/problem?id=26596


if __name__ == "__main__":
    asyncio.run(main())
```

Or without context manager:

```python
from sdamgia import SdamgiaAPI
from sdamgia.enums import GiaType, Subject


async def main() -> None:
    sdamgia = SdamgiaAPI(gia_type=GiaType.EGE, subject=Subject.MATH)
    # ... do something with client
    await sdamgia.close()  # this line is mandatory
```

## 📜 License

This project is licensed under the LGPLv3+ license - see the
[license file](https://github.com/dinaprk/sdamgia-python/blob/master/LICENSE) for details.
