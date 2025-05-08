from typing import Annotated
from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


app = FastAPI()

engine = create_async_engine("sqlite+aiosqlite:///mydb.db", echo=True)

new_async_session = async_sessionmaker(engine, expire_on_commit=False)


async def get_session():
    async with new_async_session() as session:
        yield session


SessionDep = Annotated[AsyncSession, Depends(get_session)]

class Base(DeclarativeBase):
    pass


class BookModel(Base):
    __tablename__ = "books"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str]
    author: Mapped[str]


class BookSchema(BaseModel):
    title: str
    author: str


class BookGetSchema(BaseModel):
    id: int
    title: str
    author: str


@app.post("/setup")  # Создаём одну таблицу с книгами (в результате в корне проекта создаётся файл БД - mydb.db)
async def setup_database():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)


@app.post("/books")  # добавление книги
async def add_book(book: BookSchema, session: SessionDep) -> BookSchema:
    new_book = BookModel(
        title=book.title,
        author=book.author,
    )
    session.add(new_book)
    await session.commit()
    return book


from pydantic import BaseModel, Field


class PaginationParams(BaseModel):  # Параметры пагинации. Пагинация - возвращение результатов с сервера не сразу, а частями; чтобы получить
                                    # нужный результат, в запросе нужно указать параметры.
    limit: int = Field(20, ge=1, le=100, description="Количество элементов на странице")
    offset: int = Field(0, ge=0, description="Смещение для пагинации")  # offset - это как-бы 'сдвиг' при формировании результата запроса


PaginationDep = Annotated[PaginationParams, Depends(PaginationParams)]


@app.get("/books") # получение книги/книг из БД (параметры пагинации задаются по умолчанию или же может задавать сам клиент)
async def get_books(session: SessionDep, pagination: PaginationDep) -> list[BookGetSchema]:
    query = (
        select(BookModel)
        .limit(pagination.limit)
        .offset(pagination.offset)
    )
    result = await session.execute((query))
    return result.scalars().all()


@app.delete("/books/{book_id}")  # удаление ненужной книги по id-шнику
async def delete_book(book_id: int, session: SessionDep):
    book = await session.get(BookModel, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="Книга не найдена")

    await session.delete(book)
    await session.commit()
    return {"detail": f"Книга с id={book_id} удалена"}


# обновим модель запроса (сделаем поля опциональными):
class BookUpdateSchema(BaseModel):
    title: str | None = None
    author: str | None = None


@app.put("/books/{book_id}", response_model=BookGetSchema)  # "ручка" обновления (редактирование книги)
                                                                 # Позволяет клиенту обновить title и author у существующей записи по id.
async def update_book(book_id: int, book_data: BookUpdateSchema, session: SessionDep):
    book = await session.get(BookModel, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="Книга не найдена")

    if book_data.title is not None:
        book.title = book_data.title
    if book_data.author is not None:
        book.author = book_data.author

    await session.commit()
    await session.refresh(book)  # Обновим объект после коммита
    return book
