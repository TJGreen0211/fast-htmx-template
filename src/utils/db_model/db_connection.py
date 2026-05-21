import logging

from typing import Union
from copy import copy

from sqlalchemy import create_engine
from sqlalchemy.pool import QueuePool
# from pymysql import IntegrityError, InternalError, ProgrammingError
from .utils.terms import QueryFilter, Term
from .utils.statements import DBDrivers, JoinType, QueryStatement
from src.utils.config import logging_level, db_conn_str

logging.basicConfig(format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)
logger.setLevel(logging_level)


DB_CONNECTION_POOL = create_engine(
    db_conn_str,
    echo=True,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=5,
    pool_recycle=3600,
    poolclass=QueuePool,
)


class DBModelConfig:
    driver = DBDrivers.SQLITE


class DirectDBConnection(object):
    """
    Basic functionality to allow direct DB queries to be run
    """
    exit_exception_type = None
    rollback = None

    def __init__(self, db_name: str=None, rollback: bool=False):
        self.db_name = db_name
        self._cursor = None
        self.column_names = None
        self._conn = None
        self.query_data = None
        self.description = None
        self.conn_driver = DBDrivers.SQLITE

    def __enter__(self):
        self._open_db_connection()
        return self

    def __exit__(self, exception_type, exception_value, traceback):
        if exception_type is not None:
            logger.error(f"Failed when exiting DirectDBConnection, error: {exception_value}")
        self._close_db_connection()

    @property
    def as_list(self) -> list:
        """
        Returns all records for a query
        """
        # Store in case we need it later
        if self.query_data:
            return [dict(zip(self.column_names, row))
                    for row in self.query_data]
        return []

    @property
    def as_dict(self) -> dict:
        """
        Returns a single record
        Use this when we only expect one record to be returned.
        If multiple records are returned it will return a random one.
        """
        if self.query_data and len(self.query_data) > 0:
            return dict(zip(self.column_names, self.query_data))
        return {}

    def execute_procedure(self, procedure, *args) -> list:
        self._cursor = self._conn.cursor()
        self._cursor.callproc(procedure, args)
        self.description = self._cursor.description
        if self.description:
            self.column_names = [col[0] for col in self.description]
            self.query_data = self._cursor.fetchall()

        return self.as_list

    def execute(self, sql_string, query_args=(), commit=False, multiple=True) -> Union[list, dict]:
        """
        Fetch the data
        """
        data = None
        last_row_id = 0
        logger.debug(sql_string)
        logger.debug(query_args)

        try:
            self._cursor = self._conn.cursor()
            self._cursor.execute(sql_string, query_args)
            if commit:
                last_row_id = self._cursor.lastrowid
                self._conn.commit()

            if last_row_id:
                # Insert update or delete so set multiple to false since we only get the last_row_id
                multiple = False
                self.column_names = ['last_row_id']
                self.query_data = [last_row_id]
            else:
                self.description = self._cursor.description
                if self.description:
                    self.column_names = [col[0] for col in self.description]
                    self.query_data = self._cursor.fetchall() if multiple else self._cursor.fetchone()

            data = self.as_list if multiple else self.as_dict

            return data

        # except InternalError as e:
        #     if e.args[0] == 1644:
        #         raise HandledException(e.args[1], severity='error')
        # except ProgrammingError as e:
        #     raise HandledException(e.args[1], severity='error')
        except Exception:
            raise

    def _open_db_connection(self):
        """
        Open Connection to specified DSN.
        """

        try:
            self._conn = DB_CONNECTION_POOL.raw_connection()
            # logger.debug(DB_CONNECTION_POOL.pool.status())
            self.conn_driver = DB_CONNECTION_POOL.driver
        except Exception:
            logger.error(f"Cannot connect to DB using conn str={DB_CONNECTION_POOL.url}.")
            raise

    def _close_db_connection(self):
        """
        Close out the connection for the sp. It handles roll backs, committing, and closing.
        """
        try:
            if self._cursor:
                self._cursor.close()
            if self._conn:
                if not self.rollback:
                    self._conn.commit()
                # Return the cursor to the pool
                self._conn.close()
                self._conn = None
        except Exception:
            logger.error("Cannot close connection")
            del self._conn
            del self._cursor


class QueryException(Exception):
    """Exception class for DBQuery errors"""
    pass


class TransactionTypes(object):
    SELECT = 'select'
    INSERT = 'insert'
    UPDATE = 'update'
    DELETE = 'delete'
    SELECT_FOR_UPDATE = 'select_for_update'


class DBQuery(DirectDBConnection):
    """
    Stateless query runner built on top of the DirectDBConnection.
    """

    def __init__(self, schema: str, table: str='', conn=None):
        """Define the base table to run the queries from.

        :param schema: Database schema
        :type schema: str
        :param table: Database table
        :type table: str

        :param conn: Reusable connection so a new one does not have to be created for each query.
            This is not normally used but can be to speed up queries
            defaults to None
        :type conn: DirectDBConnection._conn, optional
        """
        super().__init__()
        self.schema = schema
        self.table = table
        if conn:
            self._conn = conn
        self.transaction_type = None
        self.transactions: list[str] = []

        # TODO: This was a quick fix and needs to be reworked
        self.keywords = ['MIN(', 'MAX(', 'COUNT(', 'DATE(', 'COUNT(', 'DISTINCT(', 'DATE_FORMAT(', 'CONCAT(',
                         'JSON_UNQUOTE(', 'JSON_EXTRACT(']

        self.joins: list['DBQuery'] = []
        self.on: list[QueryFilter] = []
        self.columns: list = []
        self.wheres: list[Term] = []
        self.group_bys: list[Union[list, str]] = []
        self.order_bys: list[Union[list, str]] = []
        self.inserts: list[Term] = []
        self.updates: list[Term] = []
        self.select_for_update_keys = []
        self.offsets: int = None
        self.limits: int = None
        self.duplicate_key_update = False
        self.count_as: QueryFilter = []
        self.order_by_dir = "DESC"
        self.query_args: dict = {}
        self.term_count: int = 0

        self.join_on: QueryFilter = None
        self.join_type: str = None
        self.parent_table: str = None
        self.multiple = False

    def _parse_kwargs(self, **kwargs) -> list[Term]:
        terms = []
        for key, value in kwargs.items():
            # Legacy code patch. Convert everything to a term
            term = Term(key, type(value), schema=self.schema, table=self.table, position=self.term_count)

            if isinstance(value, tuple):
                term.left = value[0].format(key)
                term.right = value[2]
                term.operator = value[1]
            else:
                term = term == value

            terms.append(term)
            self.term_count = self.term_count + 1
        return terms

    def _builder(func):
        def _copy(self, *args, **kwargs):
            self_copy = copy(self)  # if getattr(self, "immutable", True) else self
            result = func(self_copy, *args, **kwargs)

            # Return self if the inner function returns None.
            # We can chain builders together if the inner function returns something different
            # (This will likely want to be used to move some of the functionality to their own classes).
            if result is None:
                return self_copy

            return result

        return _copy

    @_builder
    def from_(self, table_name) -> 'DBQuery':
        self.table = table_name

    @_builder
    def join(self, table: 'DBQuery', join_from: str, join_to: str, join_type='LEFT') -> 'DBQuery':
        table.join_type = join_type
        join_value = f"{self.qualified_table_name}.{join_to}"
        table.join_on = QueryFilter(join_from, join_value, is_join=True)
        table.parent_table = f"{self.qualified_table_name}"
        # Don't use append - append returns a copy of self and causes undefined behavior
        self.joins = [table] + [x for x in self.joins]

    def inner_join(self, table: 'DBQuery', join_from: str, join_to: str) -> 'DBQuery':
        return self.join(table, join_from, join_to, join_type=JoinType.INNER)

    def left_join(self, table: 'DBQuery', join_from: str, join_to: str) -> 'DBQuery':
        return self.join(table, join_from, join_to, join_type=JoinType.LEFT)

    def left_outer_join(self, table: 'DBQuery', join_from: str, join_to: str) -> 'DBQuery':
        return self.join(table, join_from, join_to, join_type=JoinType.LEFT_OUTER)

    def right_join(self, table: 'DBQuery', join_from: str, join_to: str) -> 'DBQuery':
        return self.join(table, join_from, join_to, join_type=JoinType.RIGHT)

    def outer_join(self, table: 'DBQuery', join_from: str, join_to: str) -> 'DBQuery':
        return self.join(table, join_from, join_to, join_type=JoinType.OUTER)

    def right_outer_join(self, table: 'DBQuery', join_from: str, join_to: str) -> 'DBQuery':
        return self.join(table, join_from, join_to, join_type=JoinType.RIGHT_OUTER)

    def full_outer_join(self, table: 'DBQuery', join_from: str, join_to: str) -> 'DBQuery':
        return self.join(table, join_from, join_to, join_type=JoinType.FULL_OUTER)

    def cross_join(self, table: 'DBQuery', join_from: str, join_to: str) -> 'DBQuery':
        return self.join(table, join_from, join_to, join_type=JoinType.CROSS)

    def hash_join(self, table: 'DBQuery', join_from: str, join_to: str) -> 'DBQuery':
        return self.join(table, join_from, join_to, join_type=JoinType.HASH)

    @_builder
    def select(self, *args) -> 'DBQuery':
        self.transaction_type = TransactionTypes.SELECT
        self.transactions = [TransactionTypes.SELECT]
        self.columns = [x for x in args]
        if set(self.columns) == {None}:
            self.columns = []
        elif not self.columns:
            self.columns = "*"

    @_builder
    def for_update(self, *args, **kwargs) -> 'DBQuery':
        self.transaction_type = TransactionTypes.SELECT_FOR_UPDATE
        self.transactions = [TransactionTypes.SELECT_FOR_UPDATE, TransactionTypes.UPDATE, TransactionTypes.SELECT]
        self.updates = self._parse_kwargs(**kwargs)
        if not self.updates:
            raise TypeError("No arguments supplied")
        self.select_for_update_keys = [x for x in args]

    @_builder
    def insert(self, *args: list[dict], select=True, **kwargs) -> 'DBQuery':
        self.transaction_type = TransactionTypes.INSERT
        self.transactions = [TransactionTypes.INSERT]
        if select:
            self.transactions = [TransactionTypes.INSERT, TransactionTypes.SELECT]
        self.columns = "*"
        if args:
            self.inserts = [self._parse_kwargs(**x) for x in args]
        else:
            self.inserts = self._parse_kwargs(**kwargs)

    @_builder
    def update(self, select=True, **kwargs) -> 'DBQuery':
        self.transaction_type = TransactionTypes.UPDATE
        self.transactions = [TransactionTypes.UPDATE]
        if select:
            self.transactions = [TransactionTypes.UPDATE, TransactionTypes.SELECT]
        self.updates = self._parse_kwargs(**kwargs)
        if not self.updates:
            raise TypeError("No arguments supplied")
        self.columns = "*"

    @_builder
    def delete(self) -> 'DBQuery':
        self.transaction_type = TransactionTypes.DELETE
        self.transactions = [TransactionTypes.DELETE]

    @_builder
    def where(self, *args, **kwargs) -> 'DBQuery':
        arr = self._parse_kwargs(**kwargs)
        if args:
            arr.extend(args)
        if not arr:
            raise TypeError("No arguments supplied")

        self.wheres = arr

    @_builder
    def group_by(self, *args) -> 'DBQuery':
        self.group_bys = [x for x in args]

    @_builder
    def order_by(self, *args) -> 'DBQuery':
        self.order_bys = [x for x in args]

    @_builder
    def asc(self) -> 'DBQuery':
        self.order_by_dir = "ASC"

    @_builder
    def desc(self) -> 'DBQuery':
        self.order_by_dir = "DESC"

    @_builder
    def limit(self, lim: int) -> 'DBQuery':
        self.limits = lim

    @_builder
    def offset(self, off: int) -> 'DBQuery':
        self.offsets = off

    @_builder
    def on_duplicate_key_update(self, **kwargs) -> 'DBQuery':
        self.duplicate_key_update = True
        self.transactions.append(TransactionTypes.UPDATE)
        self.updates = self._parse_kwargs(**kwargs)
        if not self.updates:
            raise TypeError("No arguments supplied")

    @_builder
    def count(self, count_as='') -> 'DBQuery':
        # TODO: Deprecate this builder and remove
        self.count_as = QueryFilter('count(*)', count_as, operator='as')

    @property
    def qualified_table_name(self):
        if not self.table:
            raise QueryException("No table defined, add a from_ statement")
        return '.'.join([x for x in [self.schema, self.table] if x])

    def _qualify_keywords(self, column: str) -> str:
        # keyword_index = [y in column for y in self.keywords]
        keyword_index = [y in "DATE_FORMAT(fetch_date, '%Y-%m') as label" for y in self.keywords]

        if True in keyword_index:
            keyword_index = self.keywords[keyword_index.index(True)]

            return column.replace(keyword_index, f"{keyword_index}{self.qualified_table_name}.")
        return column

    @property
    def _prepare_columns(self) -> str:
        columns = ''

        columns = ', '.join(
            [self._qualify_keywords(x) if any([y in x for y in self.keywords])
             else f"{self.qualified_table_name}.`{x}`".replace('`*`', '*') for x in self.columns]
        )
        if self.count_as:
            columns = self.count_as.as_sql
        join_columns = ', '.join([x._prepare_columns for x in self.joins if x._prepare_columns])
        columns = ', '.join([x for x in [columns, join_columns] if x]).strip()

        return f" {columns} " if columns else ""

    @property
    def _columns(self) -> list[str]:
        c = [f"{self.qualified_table_name}.{x}" for x in self.columns]
        [c.extend(x._columns) for x in self.joins if x.columns]
        return c

    @property
    def _prepare_wheres(self) -> str:
        stmnt_query_args = {}
        stmnt_wheres = []
        for stmnt in self.wheres:
            where = stmnt.prepare
            if isinstance(where.value, tuple):
                bind_ins = []
                for i, value in enumerate(where.value):
                    nb = f"{where.name}_{i}"
                    bind_ins.append(where._format.format(nb))
                    stmnt_query_args.update({f"{where.name}_{i}": value})
                s = '('+','.join(bind_ins)+')'
                stmnt_wheres.append(where.statement.replace(where.bind, s))
            else:
                stmnt_query_args.update(where.query_args)
                stmnt_wheres.append(self._qualify_keywords(where.statement))

        self.query_args.update(stmnt_query_args)
        wheres = ' AND '.join(stmnt_wheres)

        join_wheres = []
        join_query_args = {}
        for x in self.joins:
            stmnt, query_args = x._prepare_wheres
            join_wheres.append(stmnt)
            join_query_args.update(query_args)

        join_wheres = ' AND '.join([x for x in join_wheres if x])

        self.query_args.update(stmnt_query_args)
        self.query_args.update(join_query_args)

        wheres = ' AND '.join([x for x in [wheres, join_wheres] if x]).strip()
        if self.parent_table:
            return f"{wheres}" if wheres else "", self.query_args
        return f" WHERE {wheres} " if wheres else ""

    @property
    def _prepare_updates(self) -> str:
        stmnt_query_args = {}
        stmnt_updates = []
        for stmnt in self.updates:
            update = stmnt.prepare
            if isinstance(update.value, tuple):
                bind_ins = []
                for i, value in enumerate(update.value):
                    nb = f"{update.name}_{i}"
                    bind_ins.append(update._format.format(nb))
                    stmnt_query_args[f"{update.name}_{i}"] = value
                s = '('+','.join(bind_ins)+')'
                stmnt_updates.append(update.statement.replace(update.bind, s))
            else:
                stmnt_query_args[update.name] = update.value
                stmnt_updates.append(update.statement)

        self.query_args.update(stmnt_query_args)

        # The replace was a quick fix. It needs to be handled in Term
        updates = ', '.join([x.replace(' IS ', ' = ') for x in stmnt_updates])
        if self.conn_driver == DBDrivers.SQLITE:
            updates = ', '.join([x.replace(f'{self.qualified_table_name}.', '') for x in stmnt_updates])

        join_updates = ', '.join([x for x in [x._prepare_updates for x in self.joins] if x])
        updates = ', '.join([x for x in [updates, join_updates] if x]).strip()

        if self.parent_table:
            return f"{updates}" if updates else ""

        return f" SET {updates.replace('IS', '=')} " if updates else ""

    @property
    def _prepare_inserts(self) -> str:
        stmnt_inserts = []
        if self.multiple:
            for insert in self.inserts:
                insert_values = []
                for stmnt in insert:
                    value = stmnt.prepare
                    self.query_args.update(value.query_args)
                    insert_values.append(value.bind)
                stmnt_inserts.append(', '.join(insert_values))

        else:
            for stmnt in self.inserts:
                value = stmnt.prepare
                self.query_args.update(value.query_args)
                stmnt_inserts.append(value.bind)

        return '),('.join(stmnt_inserts) if self.multiple else ', '.join(stmnt_inserts)

    @property
    def _prepare_order_bys(self) -> str:
        for x in self.order_bys:
            if (isinstance(x, Term) and x.order_dir) and (x.order_dir == 'RANDOM' or 'SUBSTR' in x.order_dir):
                if x.order_dir == 'RANDOM':
                    return ' ORDER BY RANDOM() '
                else:
                    return f' ORDER BY {x.order_dir} '
        return ' ORDER BY ' + ', '.join([
            f"{self.qualified_table_name}.{x} {self.order_by_dir}" if isinstance(x, str) else
            f"{x.qualified_table_name}.{x.name} {x.order_dir if x.order_dir else 'DESC'}"
            for x in self.order_bys
        ]) if self.order_bys else ''

    @property
    def _prepare_tables(self) -> str:
        table = self.qualified_table_name
        join_tables = ' '.join([x._prepare_tables for x in self.joins])
        if self.parent_table:
            table = (f" {self.join_type} JOIN {self.qualified_table_name} "
                     f"ON {self.qualified_table_name}.{self.join_on.as_sql} ")
        table = ' '.join([x for x in [table, join_tables] if x]).strip()
        return f" {table} "

    @property
    def _prepare_limits(self):
        if self.multiple:
            return '' if not self.limits else f' LIMIT {self.limits} '
        else:
            return ' LIMIT 1 '

    @property
    def _prepare_offsets(self):
        if self.limits:
            return '' if not self.offsets else f' OFFSET {self.offsets} '
        return ''

    @property
    def _prepare_group_bys(self):
        group_bys = ', '.join([
            f"{x}" if isinstance(x, str) else
            f"{x}" if isinstance(x, int) else
            f"{x.qualified_table_name}.{x.name}" for x in self.group_bys
        ])
        return f' GROUP BY {group_bys}' if group_bys else ''

    def _sql_to_string(self, sql: str):
        bind_format = DBDrivers.bind(self.conn_driver or DBDrivers.SQLITE)
        format_str = sql
        for key, value in self.query_args.items():
            format_str = format_str.replace(bind_format.format(key), str(QueryFilter(key, value)._value_as_sql))
        return format_str

    @property
    def prepare(self) -> str:
        """
        Prepare SQL statement to be executed.

        :return: Transaction SQL string
        :rtype: str
        """
        self.query_args = {}

        query_format = QueryStatement(self.conn_driver)
        if self.transaction_type == TransactionTypes.SELECT_FOR_UPDATE:
            return query_format.select_for_update.format(
                columns=self._prepare_columns, tables=self._prepare_tables, wheres=self._prepare_wheres,
                group_bys=self._prepare_group_bys, order_bys=self._prepare_order_bys, limits=self._prepare_limits)

        if self.transaction_type == TransactionTypes.SELECT:
            return query_format.select.format(
                columns=self._prepare_columns, tables=self._prepare_tables, wheres=self._prepare_wheres,
                group_bys=self._prepare_group_bys, order_bys=self._prepare_order_bys, limits=self._prepare_limits,
                offsets=self._prepare_offsets)

        if self.transaction_type == TransactionTypes.INSERT:
            # WITH an_alias AS (SELECT * FROM "customers") SELECT * FROM an_alias
            column_mapping = self.inserts[0] if self.multiple else self.inserts
            insert_columns = ', '.join([f'`{x.column}`' for x in column_mapping])

            return query_format.insert.format(
                table=self.qualified_table_name, columns=insert_columns, values=self._prepare_inserts)

        if self.transaction_type == TransactionTypes.UPDATE:
            return query_format.update.format(
                tables=self._prepare_tables, updates=self._prepare_updates,
                wheres=self._prepare_wheres, limits=self._prepare_limits)

        if self.transaction_type == TransactionTypes.DELETE:
            tables_sql = self._prepare_tables
            # This is a multi-table delete limit is not supported
            if 'JOIN' in tables_sql:
                return f"DELETE {self.qualified_table_name} FROM{tables_sql}{self._prepare_wheres}"
            else:
                return query_format.delete.format(
                    qualified_table=self.qualified_table_name,
                    tables=tables_sql, wheres=self._prepare_wheres, limits=self._prepare_limits
                )

        return ''

    @property
    def as_sql(self) -> str:
        return self._sql_to_string(self.prepare)

    def _run(self) -> Union[list[dict], dict]:
        query_format = QueryStatement(self.conn_driver)
        if not self.transactions:
            raise QueryException("No transaction type is defined. Use select, insert, update, or delete.")

        data = [] if self.multiple else {}
        for transaction_type in self.transactions:
            self.transaction_type = transaction_type
            if self.transaction_type in [TransactionTypes.UPDATE, TransactionTypes.DELETE]:
                if not self.wheres:
                    raise QueryException(f"A where clause must be defined for {self.transaction_type}.")
                if (len(self.wheres) == 1 and self.wheres[0].right is None):
                    raise QueryException(f"Cannot {self.transaction_type} on null where clause")

            commit = self.transaction_type in [
                TransactionTypes.INSERT, TransactionTypes.UPDATE, TransactionTypes.DELETE
            ]
            if self.transaction_type == TransactionTypes.SELECT and TransactionTypes.INSERT in self.transactions:
                pks = self.execute(query_format.primary_keys.format(table=self.qualified_table_name))
                if data:
                    # This means primary key is an auto-increment id and we can use that to run the select
                    self.wheres = [Term(pks[0].get('Field'), schema=self.schema, table=self.table) == [
                        data.get('last_row_id') + i for i in range(len(self.inserts))]]
                else:
                    # else we grab the PK from the insert data
                    self.wheres = [QueryFilter(
                        pk.get('Field'),
                        next((insert.right for insert in self.inserts if insert.column == pk.get('Field')), None)
                    ) for pk in pks]

            try:
                sql = self.prepare
                data = self.execute(sql, self.query_args, commit=commit, multiple=self.multiple)
            # except IntegrityError:
            #     if not self.duplicate_key_update:
            #         raise
            except Exception:
                raise

            if self.transaction_type == TransactionTypes.SELECT_FOR_UPDATE:
                if not data:
                    return [] if self.multiple else {}
                if isinstance(data, list):
                    self.wheres = [Term(column, schema=self.schema, table=self.table) == [x[column] for x in data]
                                   for column in self.select_for_update_keys]
                else:
                    self.wheres = [Term(column, schema=self.schema, table=self.table) == data[column]
                                   for column in self.select_for_update_keys]

        if self.transaction_type in [TransactionTypes.INSERT, TransactionTypes.UPDATE, TransactionTypes.DELETE]:
            data = [{'status': True}] if self.multiple else {'status': True}
        return data

    @property
    def run_multiple(self) -> list[dict]:
        self.multiple = True
        return self.run

    @property
    def run(self) -> dict:
        if self._conn:
            return self._run()
        with self:
            return self._run()
