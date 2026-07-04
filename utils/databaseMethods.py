import json
from collections import OrderedDict

import aiosqlite

from utils import service
from utils.types import AsyncLRUTTLCache, Filter, FiltersGroup, Join, User


class DbQueryReturn:
    def __init__(self, cur, fetchone, fetchall):
        self.cur = cur
        self.fetchone: tuple = fetchone
        self.fetchall: tuple = fetchall


class DatabaseMethodsBase:
    def __init__(self, bot: "service.Bot"):
        self.db: aiosqlite.Connection = bot.db
        self.bot = bot
        self.cacheSettings = {
            "long": {"maxsize": 1024, "ttl": 7200},
            "mid": {"maxsize": 1024, "ttl": 900},
            "short": {"maxsize": 1024, "ttl": 300},
        }

    async def _clearCache(self):
        for attr_name in dir(self):
            if attr_name.startswith("_cache") and attr_name.endswith("Store"):
                cache_store: AsyncLRUTTLCache = getattr(self, attr_name)
                await cache_store.clear()

    async def _getCached(self, store: AsyncLRUTTLCache, key: str):
        try:
            cached = await store.get(key)
        except Exception:
            cached = None

        if cached is not None:
            return cached
        return None

    async def _getStored(self, store: AsyncLRUTTLCache | None = None):
        caches: dict[str, OrderedDict] = {}
        if not store:
            for attr_name in dir(self):
                if attr_name.startswith("_cache") and attr_name.endswith("Store"):
                    cache_store: AsyncLRUTTLCache = getattr(self, attr_name)
                    caches[attr_name] = cache_store.store

        return caches

    async def execute(self, query: str, *params):
        ftdquery = " ".join([line.strip() for line in query.splitlines()]).strip()

        self.bot.log(f'Query: "{ftdquery}"', f"Params: {params}", type="db")
        fetch = await self.db.execute(query, *params)
        await self.db.commit()
        fetchall = await fetch.fetchall()

        if fetchall != []:
            fetchone = fetchall[0]
        else:
            fetchone = None

        self.bot.log("Fetchall", fetchall, type="db")
        self.bot.log("Fetchone", fetchone, type="db")

        return DbQueryReturn(fetch, fetchone, fetchall)

    async def adressedUpdate(self, tableName, filters: list[Filter], **updates):
        self.bot.log(
            "Start dbm.adressedUpdate",
            f"tableName: {tableName}",
            f"filters: {[f'{filter.column}={filter.value}' for filter in filters]}",
            f"updates: {updates}",
            type="pos",
        )
        # """Update only the columns provided in `updates` for the row with `keyVal`.

        # This function validates column names against the table schema (via
        # `PRAGMA table_info`) to prevent SQL injection through column names.
        # Values are passed as parameters to keep queries safe.
        # """

        # Apply convertToToggles to updates before proceeding
        # updates = self.convertToToggles(**updates)

        cols_info = (await self.execute(f"PRAGMA table_info({tableName})")).fetchall
        valid_columns = {row[1] for row in cols_info}

        set_parts = []
        params = []

        for col, val in updates.items():
            if col not in valid_columns:
                raise ValueError(f"Unknown column: {col}")

            if isinstance(val, str) and val.startswith("CASE"):
                set_parts.append(f'"{col}" = {val}')
            else:
                set_parts.append(f'"{col}" = ?')
                if isinstance(val, bool):
                    params.append(1 if val else 0)
                else:
                    params.append(val)

        # params.append(keyVal)
        # query = f"UPDATE {tableName} SET {', '.join(set_parts)} WHERE {keyColumn} = ?"

        # await self.update()

        await self.update(tableName, filters=filters, **updates)

        # await self.execute(query, tuple(params))
        # await self.db.commit()

    def convertToToggles(self, **updates):
        upds = {}
        for key in updates:
            updated = updates[key]
            if updates[key] == "toggle":
                updated = f"CASE {key} WHEN 1 THEN 0 WHEN 0 THEN 1 END"
            upds[key] = updated

        return upds

    async def create(self, table: str, data: dict):
        self.bot.log(
            f"Start dbm.create for {table}",
            ", ".join([f"{k}: {v}" for k, v in data.items()]),
            type="pos",
        )

        fields = {
            k: (1 if v else 0) if isinstance(v, bool) else v for k, v in data.items()
        }

        columns = [f'"{k}"' for k in fields.keys()]
        values = list(fields.values())
        placeholders = ["?" for _ in values]

        query = f"""
	INSERT INTO {table}
			({", ".join(columns)})
	VALUES
		({", ".join(placeholders)})
		"""
        await self.execute(query, values)

    async def createTable(
        self,
        table: str,
        columns: dict[str, str],
        ifNotExists: bool = True,
        alter: bool = True,
    ):
        self.bot.log(
            f"Start dbm.createTable for {table}",
            ", ".join([f"{k}: {v}" for k, v in columns.items()]),
            type="pos",
        )
        exists = "IF NOT EXISTS" if ifNotExists else ""
        cols = [f'"{name}" {definition}' for name, definition in columns.items()]

        await self.execute(f"""
    CREATE TABLE {exists} {table}
        ({", ".join(cols)})
        """)

        if alter:
            existing_cols = set()
            try:
                cols_info = (await self.execute(f"PRAGMA table_info({table})")).fetchall
                existing_cols = {row[1] for row in cols_info}
            except Exception:
                pass

            for name, definition in columns.items():
                if name not in existing_cols:
                    await self.execute(
                        f'ALTER TABLE {table} ADD COLUMN "{name}" {definition}'
                    )

    def generateWhereClauses(self, filters: list[Filter] | list[FiltersGroup]):
        where_clauses: list[str] = []
        params: list = []

        def _quote_col(col: str) -> str:
            # don't quote if it's a qualified column (contains dot) or already quoted
            col = str(col)
            if "." in col or col.startswith('"') or col.endswith('"'):
                return col
            return f'"{col}"'

        for filter_item in filters or []:
            # Group of filters (AND / OR)
            if isinstance(filter_item, FiltersGroup):
                group_clauses: list[str] = []
                for flt in filter_item.filters or []:
                    col = _quote_col(flt.column)
                    op = (flt.operator or "=").upper()
                    val = flt.value

                    # dict-valued special filter (e.g. {'op': 'IS NOT', 'val': 'NULL'})
                    if isinstance(val, dict):
                        op = val.get("op", op)
                        v = val.get("val")
                        # if val is a literal SQL fragment (like NULL), insert directly
                        if v is None or (isinstance(v, str) and v.upper() == "NULL"):
                            group_clauses.append(f"{col} {op} NULL")
                        else:
                            group_clauses.append(f"{col} {op} ?")
                            params.append(v)
                        continue

                    # IN operator handling
                    if op == "IN":
                        # list/tuple -> placeholders
                        if isinstance(val, (list, tuple)) and len(val) > 0:
                            placeholders = ", ".join(["?" for _ in val])
                            group_clauses.append(f"{col} IN ({placeholders})")
                            params.extend(val)
                        # preformatted tuple string like "(1,2)" (Filter may have converted it)
                        elif (
                            isinstance(val, str)
                            and val.strip().startswith("(")
                            and val.strip().endswith(")")
                        ):
                            group_clauses.append(f"{col} IN {val}")
                        # empty list -> always false
                        elif val is None or (
                            isinstance(val, (list, tuple)) and len(val) == 0
                        ):
                            group_clauses.append("0")
                        else:
                            group_clauses.append(f"{col} IN (?)")
                            params.append(val)
                        continue

                    # IS / IS NOT with None
                    if op in ("IS", "IS NOT") and (
                        val is None or (isinstance(val, str) and val.upper() == "NULL")
                    ):
                        group_clauses.append(f"{col} {op} NULL")
                        continue

                    # column reference (e.g. "k.ownerId") - no param
                    if (
                        isinstance(val, str)
                        and "." in val
                        and not (
                            val.strip().startswith("(") or val.strip().startswith("'")
                        )
                    ):
                        group_clauses.append(f"{col} {flt.operator} {val}")
                        continue

                    # Default case - use placeholder
                    group_clauses.append(f"{col} {flt.operator} ?")
                    params.append(val)

                # join group's clauses with operator and wrap in parentheses
                if group_clauses:
                    where_clauses.append(
                        "(" + f" {filter_item.operator} ".join(group_clauses) + ")"
                    )
                continue

            # Single Filter
            col = _quote_col(filter_item.column)
            op = filter_item.operator.upper()
            val = filter_item.value

            if isinstance(val, dict):
                op = val.get("op", op)
                v = val.get("val")
                if v is None or (isinstance(v, str) and v.upper() == "NULL"):
                    where_clauses.append(f"{col} {op} NULL")
                    continue
                where_clauses.append(f"{col} {op} ?")
                params.append(v)
                continue

            if op == "IN":
                if isinstance(val, (list, tuple)) and len(val) > 0:
                    placeholders = ", ".join(["?" for _ in val])
                    where_clauses.append(f"{col} IN ({placeholders})")
                    params.extend(val)
                    continue

                if (
                    isinstance(val, str)
                    and val.strip().startswith("(")
                    and val.strip().endswith(")")
                ):
                    where_clauses.append(f"{col} IN {val}")
                    continue
                # empty -> false
                if val is None or (isinstance(val, (list, tuple)) and len(val) == 0):
                    where_clauses.append("0")
                    continue
                where_clauses.append(f"{col} IN (?)")
                params.append(val)
                continue

            if op in ("IS", "IS NOT") and (
                val is None or (isinstance(val, str) and val.upper() == "NULL")
            ):
                where_clauses.append(f"{col} {op} NULL")
                continue

            if (
                isinstance(val, str)
                and "." in val
                and not (val.strip().startswith("(") or val.strip().startswith("'"))
            ):
                where_clauses.append(f"{col} {filter_item.operator} {val}")
                continue

            where_clauses.append(f"{col} {filter_item.operator} ?")
            params.append(val)

        return where_clauses, params

    def generateJoinClauses(self, joins: list[Join]):
        join_clauses, params = [], []
        for join in joins:
            join_clause = f"{join.type} {join.table}"
            if join.alias:
                join_clause += f" {join.alias}"

            # Формируем условия JOIN
            if join.filters:
                join_conditions = []

                for filter in join.filters:
                    if isinstance(filter.value, dict):
                        # Специальные операторы (IS NOT NULL и т.д.)
                        op = filter.operator
                        val = filter.value
                        join_conditions.append(f"{filter.column} {op} {val}")
                    elif isinstance(filter.value, str) and "." in filter.value:
                        # Это ссылка на другую колонку
                        join_conditions.append(f"{filter.column} = {filter.value}")
                    else:
                        # Это значение для подстановки
                        join_conditions.append(f"{filter.column} = ?")
                        params.append(filter.value)

                join_clause += " ON " + " AND ".join(join_conditions)

            join_clauses.append(join_clause)

        return join_clauses, params

    async def read(
        self,
        table: str,
        columns: list[str],
        joins: list[Join] = [],
        filters: list[Filter] = [],
        orderBy: str = None,
        orderDir: str = "DESC",
        limit: int = -1,
        offset: int = 0,
    ):
        _joingen = self.generateJoinClauses(joins)
        join_clauses = _joingen[0]
        params = [*_joingen[1]]

        _wheregen = self.generateWhereClauses(filters)
        where_clauses = _wheregen[0]
        params = [*params, *_wheregen[1]]

        query = f"""
SELECT DISTINCT {", ".join((f'"{column}"' if "." not in column else column) for column in columns)}
FROM {table}
{" ".join(join_clauses) if join_clauses else ""}
{f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""}
{f"ORDER BY {orderBy} {orderDir}" if orderBy else ""}
{f"LIMIT {limit}" if limit > -1 else ""}
{f"OFFSET {offset}" if offset > 0 else ""}
"""
        result = await self.execute(query, tuple(params))
        return result

    async def update(self, table: str, filters: list[Filter], **updates):
        """Update row from dict.

        {key: newValue}"""

        self.bot.log(
            f"Start dbm.update for {table}",
            f"filters: {[f'{filter.column}={filter.value}' for filter in filters]}",
            f"updates: {updates}",
            type="pos",
        )
        updates = {
            k: (1 if v else 0) if isinstance(v, bool) else v for k, v in updates.items()
        }

        set_parts = []
        params = []
        for col, val in updates.items():
            set_parts.append(f'"{col}" = ?')
            params.append(val)

        where_clauses = []
        if filters:
            for filter in filters:
                if isinstance(filter.value, dict):
                    # Специальные операторы (IS NOT NULL и т.д.)
                    op = filter.value.get("op", "=")
                    val = filter.value.get("val")
                    where_clauses.append(
                        f"{filter.column if '.' in filter.column else f'"{filter.column}"'} {op} {val}"
                    )
                elif isinstance(filter.value, str) and "." in filter.value:
                    # Это ссылка на другую колонку
                    where_clauses.append(
                        f"{filter.column if '.' in filter.column else f'"{filter.column}"'} = {filter.value}"
                    )
                else:
                    # Обычное значение для подстановки
                    where_clauses.append(
                        f"{filter.column if '.' in filter.column else f'"{filter.column}"'} = ?"
                    )
                    params.append(filter.value)

        query = f"""
UPDATE {table}
SET {", ".join(set_parts)}
WHERE {" AND ".join(where_clauses)}
"""
        await self.execute(query, params)

    async def delete(self, table: str, filters: list[Filter]):
        self.bot.log(
            f"Start dbm.delete from {table}",
            f"Filters: {[f'{filter.column}={filter.value}' for filter in filters]}",
            type="pos",
        )
        where_clauses, params = self.generateWhereClauses(filters)

        query = f"""
DELETE FROM {table}
WHERE {" AND ".join(where_clauses)}
"""
        await self.execute(query, tuple(a for a in params))

    def _buildCacheKey(self, prefix: str, **kwargs) -> str:
        """Строит строковый ключ кэша из произвольных аргументов."""
        return f"{prefix}:" + json.dumps(kwargs, sort_keys=True, default=str)

    async def _readFromCache(
        self, store: AsyncLRUTTLCache, key: str, cacheOverwrite: bool
    ):
        """Возвращает кэшированное значение или None если надо перечитать."""
        if cacheOverwrite:
            return None
        try:
            cached = await store.get(key)
            return cached if cached is not None else None
        except Exception:
            return None

    async def _writeToCache(self, store: AsyncLRUTTLCache, key: str, value):
        """Сохраняет значение в кэш, подавляя ошибки."""
        try:
            await store.set(key, value)
        except Exception:
            pass


class DatabaseMethods(DatabaseMethodsBase):
    def __init__(self, bot: "service.Bot"):
        super().__init__(bot)
        self._cacheUsersStore = AsyncLRUTTLCache(**self.cacheSettings["short"])

    async def createUser(self, userId: int, channelId: int, createdAt: int):
        await self.create(
            "users",
            {
                "userId": userId,
                "channelId": channelId,
                "createdAt": createdAt,
            },
        )

    async def readUsers(
        self, userId: int | None = None, cacheOverwrite: bool = False
    ) -> list[User]:
        self.bot.log("Start dbm.readUser", f"userId: {userId}", type="pos")

        cache_key = self._buildCacheKey("readUsers", userId=userId)
        cached = await self._readFromCache(
            self._cacheUsersStore, cache_key, cacheOverwrite
        )
        if cached is not None:
            return cached

        filters = []

        if userId != None:
            filters.append(Filter("userId", userId))

        usersFetch = await self.read(
            "users",
            ["userId", "channelId", "stats", "createdAt", "format"],
            filters=filters,
        )
        usersFetch = usersFetch.fetchall

        toReturn: list[User] = []

        for item in usersFetch:
            toReturn.append(
                User(
                    userId=item[0],
                    channelId=item[1],
                    stats=item[2],
                    createdAt=item[3],
                    format=item[4],
                )
            )

        await self._writeToCache(self._cacheUsersStore, cache_key, toReturn)

        return toReturn

    async def updateUser(self, userId: int, **updates) -> list[User]:
        self.bot.log(
            "Start dbm.updateUser",
            f"userId: {userId}",
            f"Updates: {updates}",
            type="pos",
        )
        await self.adressedUpdate("users", [Filter("userId", userId)], **updates)

        return await self.readUsers(userId=userId)

    async def deleteUser(self, userId: int = None, channelId: int = None):
        self.bot.log("Start dbm.deleteUser", f"userId: {userId}", type="pos")

        if not userId and not channelId:
            raise ValueError("At least one of userId or channelId should not be None!")

        await self.delete(
            "users",
            filters=[
                Filter("userId", userId),
                Filter("channelId", channelId),
            ],
        )
