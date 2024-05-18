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
pip install git+https://github.com/dinaprk/sdamgia-api.git
```

### poetry

You can add `sdamgia` as a dependency with the following command:

```shell
poetry add git+https://github.com/dinaprk/sdamgia-api.git
```

Or by directly specifying it in the configuration like so:

```toml
[tool.poetry.dependencies]
sdamgia = { git = "https://github.com/dinaprk/sdamgia-api.git" }
```

## Basic usage

Because SdamgiaAPI client is asynchronous, it needs to be initialized in asynchronous context:

```python
from sdamgia import SdamgiaAPI
from sdamgia.types import GiaType, Subject

async with SdamgiaAPI(gia_type=GiaType.EGE, subject=Subject.MATH) as sdamgia:
    problem_id = 26596
    problem = sdamgia.get_problem(problem_id, subject=Subject.MATH)
    print(problem)
    print(problem.url)
```
