"""Standard page envelope used by every list endpoint."""
from fastapi import Query
from pydantic import BaseModel

MAX_PAGE_SIZE = 100


class PageParams(BaseModel):
    page: int = 1
    size: int = 25


def page_params(
    page: int = Query(1, ge=1),
    size: int = Query(25, ge=1, le=MAX_PAGE_SIZE),
) -> PageParams:
    return PageParams(page=page, size=size)


class Page[T](BaseModel):
    items: list[T]
    page: int
    size: int
    total: int

    @classmethod
    def of(cls, items: list[T], params: PageParams, total: int) -> "Page[T]":
        return cls(items=items, page=params.page, size=params.size, total=total)
