import json
import datetime
import string
import random
from typing_extensions import Self

from .statements import DBDrivers, SQLFunction


class PreparedStatement(object):
    def __init__(self, statement: str, value: str, name: str, bind: str) -> None:
        self.statement = statement
        self.value = value
        self.bind = bind.format(name)
        self.name = name
        self._format = bind
        self.query_args = {name: self.value}


class QueryFilter(object):
    # TODO: Depecate for Term class
    GREATER_THAN = '>'
    LESS_THAN = '<'
    EQUALS = '='
    BETWEEN = 'BETWEEN'
    NOT_EQUALS = '<>'
    IS_NULL = 'IS'
    IS_NOT_NULL = 'IS NOT'
    LIKE = 'LIKE'
    AS = 'as'
    IN = 'IN'
    NOT_IN = 'NOT IN'

    def __init__(self, column: str, value: str,
                 col_format: str='{}', operator: str='=', is_join: bool=False,
                 position=0, driver=DBDrivers.SQLITE) -> None:
        self.column = column
        self.value = value
        self.operator = operator
        self.col_format = col_format  # Cannot be null
        self.is_join = is_join
        self.position = position
        self._bind_format = DBDrivers.bind(driver)

    @property
    def as_sql(self) -> str:
        return f"{self._column_as_sql} {self._operator_as_sql} {self._value_as_sql}".strip()

    @property
    def prepare(self) -> PreparedStatement:
        chars = string.ascii_lowercase + string.digits
        name = ''.join(random.choice(chars) for _ in range(6))+f"{self.column}{self.position}"
        bind = self._bind_format.format(name)
        statement = f"{self._column_as_sql} {self._operator_as_sql} {bind}".strip()

        return PreparedStatement(statement, self._value_as_sql, name, self._bind_format)

    @property
    def _value_as_sql(self) -> str:
        ret_val = self.value
        if self.is_join:
            return ret_val
        if self.value is None:
            return None
        if isinstance(ret_val, int):
            return ret_val
        if isinstance(ret_val, list):
            return tuple(ret_val) if ret_val else ("NULL",)
            # ret_val = ','.join([str(x) if isinstance(x, int) else f'{x}' for x in ret_val])
            # return f"({ret_val if ret_val else 'NULL'})"
        if isinstance(ret_val, str):
            ret_val = str(ret_val)
        if isinstance(ret_val, dict):
            ret_val = json.dumps(ret_val, default=str)
        if isinstance(ret_val, datetime.date):
            ret_val = ret_val.strftime('%Y-%m-%dT%H:%M:%S')
        if isinstance(ret_val, bytes):
            return ret_val

        return f'{ret_val}'
        # return f'\'{ret_val}\''

    @property
    def _operator_as_sql(self) -> str:
        ret_val = self.operator
        if ret_val == self.AS:
            return self.AS if self.value else ''
        if self.value is None:
            return self.IS_NULL if ret_val == self.EQUALS else \
                self.IS_NOT_NULL if ret_val == self.NOT_EQUALS else ret_val
        if isinstance(self.value, list):
            if ret_val not in [self.EQUALS, self.NOT_EQUALS]:
                raise ValueError(f"Operand not supported {ret_val}")
            return self.IN if ret_val == self.EQUALS else self.NOT_IN
        return ret_val

    @property
    def _column_as_sql(self) -> str:
        return self.col_format.format(self.column)


class DBTermMeta(type):
    def __new__(cls, *args, **kwargs):
        return super().__new__(cls, *args, **kwargs)

    def __getattribute__(cls, key):
        # TODO: Allow for chaining of Terms from DBModel without specifying type
        # Currently works like AccountApiKey.api_key.type.api_key
        # Want AccountApiKey.api_key.api_key
        # Conflict is likely caused by DBModelMeta
        # return Term(key, cls.model_fields[key].annotation, model=cls)
        return super().__getattribute__(key)


class Term(object):
    def __init__(
        self, name, type=None, model=None, schema: str='', table: str='', driver=DBDrivers.SQLITE, position=0
    ) -> None:
        self.schema = model.schema_ if model else schema
        self.table = model.table_ if model else table
        self.position = position

        # TODO: Schemas don't really exist in sqlite but can be faked
        # https://www.sqlite.org/lang_attach.html
        if driver == DBDrivers.SQLITE:
            self.schema = ''

        self.qualified_table_name = '.'.join([x for x in [self.schema, self.table] if x])

        self.name = name
        self.model = model._query_graph.V[0] if model else None
        self.left = None
        self.right = None
        self.operator = None
        self.modifier = None
        self.alias = None

        self.compound = False
        self.order_dir = None

        self._bind_format = DBDrivers.bind(driver)

    @property
    def _column_as_sql(self) -> str:
        return False

    @property
    def column(self) -> str:
        return self.name

    @property
    def as_sql(self):
        left = self.left if self.compound else f"{self.qualified_table_name}.{self.left}"
        qf = QueryFilter(left, self.right, operator=self.operator, is_join=self.compound)
        ret = '({})' if self.compound else '{}'
        return ret.format(f"{qf._column_as_sql} {qf._operator_as_sql} {qf._value_as_sql}".strip())

    @property
    def prepare(self) -> PreparedStatement:
        if self.compound:
            r_stmnt = self.right.prepare
            qf = QueryFilter(self.left.statement, self.right, operator=self.operator, is_join=self.compound)

            chars = string.ascii_lowercase + string.digits
            name = ''.join(random.choice(chars) for _ in range(6))+f"{self.name}{self.position}"
            bind = self._bind_format.format(name)
            statement = f"({qf._column_as_sql} {qf._operator_as_sql} {r_stmnt.statement})".strip()

            ret = PreparedStatement(statement, self.left.value, self.left.name, self._bind_format)
            ret.query_args.update(r_stmnt.query_args)
            ret.query_args.update(self.left.query_args)
            return ret

        else:
            dot = '.' if self.left else ''
            left = self.left if self.compound else f"{self.qualified_table_name}{dot}{self.left}"
            if self.modifier:
                left = f"{self.modifier}({left})"
            qf = QueryFilter(left, self.right, operator=self.operator, is_join=self.compound)
            ret = '{}'
            chars = string.ascii_lowercase + string.digits

            name = ''.join(random.choice(chars) for _ in range(6))+f"{self.name}{self.position}"
            bind = self._bind_format.format(name)
            statement = ret.format(f"{qf._column_as_sql} {qf._operator_as_sql} {bind}".strip())

        return PreparedStatement(statement, qf._value_as_sql, name, self._bind_format)

    def _parse(self, left, right, op) -> Self:
        self.left = left
        self.right = right
        self.operator = op
        return self

    ############################################
    # Comparison
    ############################################
    # =	Equal to
    def __eq__(self, other):
        return self._parse(self.name, other, '=')

    # <> Not equal to
    def __ne__(self, other):
        return self._parse(self.name, other, '<>')

    # >	Greater than
    def __gt__(self, other):
        return self._parse(self.name, other, '>')

    # >= Greater than or equal to
    def __ge__(self, other):
        return self._parse(self.name, other, '>=')

    # <	Less than
    def __lt__(self, other):
        return self._parse(self.name, other, '<')

    # <= Less than or equal to
    def __le__(self, other):
        return self._parse(self.name, other, '<=')

    ############################################
    # Bitwise
    ############################################
    # &	Bitwise AND
    def __and__(self, other: 'Term'):
        lt = self.prepare
        rt = other
        self.compound = True
        return self._parse(lt, rt, 'AND')

    # |	Bitwise OR
    def __or__(self, other: 'Term'):
        lt = self.prepare
        rt = other
        self.compound = True
        return self._parse(lt, rt, 'OR')

    # ^	Bitwise exclusive OR
    def __xor__(self, other: 'Term'):
        lt = self.prepare
        rt = other
        self.compound = True
        return self._parse(lt, rt, 'XOR')

    ############################################
    # Arithmetic
    ############################################
    # +	Add
    def __add__(self, other):
        return self._parse(self.name, other, '+')

    # -	Subtract
    def __sub__(self, other):
        return self._parse(self.name, other, '-')

    # *	Multiply
    def __mul__(self, other):
        return self._parse(self.name, other, '*')

    # /	Divide
    def __truediv__(self, other):
        return self._parse(self.name, other, '/')

    # %	Modulo
    def __mod__(self, other):
        return self._parse(self.name, other, '%')

    ############################################
    # Logical
    ############################################
    # IS
    def is_(self, other):
        return self._parse(self.name, other, 'IS')

    # IS NOT
    def is_not(self, other):
        return self._parse(self.name, other, 'IS NOT')

    # IN
    def __contains__(self, other):
        items = other if (isinstance(other, list) or isinstance(other, tuple)) else [other]
        return self._parse(self.name, items, 'IN')

    # BETWEEN TRUE if the operand is within the range of comparisons
    def between(self, a, b):
        rt = Term('') == b
        rt.left = ''
        rt.operator = ''

        lt = self == a
        lt.operator = 'BETWEEN'
        lt = lt.prepare
        self.compound = True
        return self._parse(lt, rt, 'AND')

    # def lconcat(self, t: str):
    #     self.modifier = SQLFunction.CONCAT
    #     self.
    #     rt = t
    #     lt = lt.prepare
    #     # self.compound = True
    #     return self

    # LIKE TRUE if the operand matches a pattern
    def like(self, a):
        return self._parse(self.name, a, 'LIKE')

    def length(self):
        self.modifier = SQLFunction.LENGTH
        return self

    def lcase(self):
        self.modifier = SQLFunction.LOWER
        return self

    def ucase(self):
        self.modifier = SQLFunction.UPPER
        return self

    def trim(self):
        self.modifier = SQLFunction.TRIM
        return self

    def date(self):
        self.modifier = SQLFunction.DATE
        return self

    ############################################
    # Modifiers
    ############################################
    def desc(self):
        self.order_dir = 'DESC'
        return self

    def random(self, seed: int=None):
        'SELECT * FROM content_meta ORDER BY (substr(id * 12345647, length(id) + 2))'
        pk_order_by = self.model._primary_keys()[0]
        if seed:
            self.order_dir = (f"SUBSTR({self.qualified_table_name}.{pk_order_by} * {seed}, "
                              f"LENGTH({self.qualified_table_name}.{pk_order_by}) + 2)")
        else:
            self.order_dir = 'RANDOM'
        return self

    def asc(self):
        self.order_dir = 'ASC'
        return self

    # TODO
    # ALL
    # ANY
