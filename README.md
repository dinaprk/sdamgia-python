# SdamGIA API

Unofficial API for SdamGIA educational portal for exam preparation.

## Structure of the Site

To make it easier to understand how the SdamGIA problems database is structured, I suggest using the following scheme:

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

Each problem, test, theme or category has its own *unique* 32-bit integer ID.

## Installing

**Python 3.10 or above is required.**

Currently, only installation from source is available.

### pip

Installing the library with `pip` is quite simple:

```shell
pip install git+https://github.com/dinaprk/sdamgia-python
```

### poetry

You can add `sdamgia` as a dependency with the following command:

```shell
poetry add git+https://github.com/dinaprk/sdamgia-python
```

Or by directly specifying it in the configuration like so:

```toml
[tool.poetry.dependencies]
sdamgia = { git = "https://github.com/dinaprk/sdamgia-python.git" }
```

## Documentation

You can find the documentation [here](https://dinaprk.github.io/sdamgia-python).

## Basic usage

Because SdamgiaAPI client is asynchronous, it needs to be initialized in asynchronous context:

```python
import asyncio
import dataclasses
import json

from sdamgia import SdamgiaAPI
from sdamgia.types import GiaType, Problem, Subject


def problem_to_json(problem: Problem) -> str:
    return json.dumps(dataclasses.asdict(problem), indent=4, ensure_ascii=False)


async def main() -> None:
    async with SdamgiaAPI(gia_type=GiaType.EGE, subject=Subject.MATH) as sdamgia:
        problem_id = 26596
        problem = await sdamgia.get_problem(problem_id, subject=Subject.MATH)
        print(problem_to_json(problem))
        print(problem.url)

if __name__ == "__main__":
    asyncio.run(main())
```

Or without context manager:

```python
from sdamgia import SdamgiaAPI
from sdamgia.types import GiaType, Subject

async def main() -> None:
    sdamgia = SdamgiaAPI(gia_type=GiaType.EGE, subject=Subject.MATH)
    # ... do something with client
    await sdamgia.close()  # this line is mandatory
```
