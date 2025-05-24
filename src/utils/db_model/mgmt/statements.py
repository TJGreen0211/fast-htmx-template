class JoinTypes(object):
    LEFT = 'LEFT'
    INNER = 'INNER'
    LEFT_OUTER = 'LEFT OUTER'
    RIGHT = 'RIGHT'
    OUTER = 'OUTER'
    RIGHT_OUTER = 'RIGHT OUTER'
    FULL_OUTER = 'FULL OUTER'
    CROSS = 'CROSS'
    HASH = 'HASH'


class KeywordFunctions(object):
    MIN = 'MIN(',
    MAX = 'MAX(',
    COUNT = 'COUNT(',
    DATE = 'DATE(',
    COUNT = 'COUNT(',
    DISTINCT = 'DISTINCT('


class DBDrivers(object):
    SQLITE = 'pysqlite'
    POSTGRES = 'postgres'
    MYSQL = 'pymysql'

    @classmethod
    def bind(cls, driver: str) -> str:
        if driver == cls.SQLITE:
            return ":{}"
        elif driver == cls.POSTGRES:
            return "%({})s"
        elif driver == cls.MYSQL:
            return "%({})s"
        else:
            raise ValueError(f"Unsupported driver: {driver}")


class QueryStatement(object):
    statement_format = {
        "select": {
            "pysqlite": "SELECT{columns}FROM{tables}{wheres}{group_bys}{order_bys}{limits}{offsets}",
            "pymysql": "SELECT{columns}FROM{tables}{wheres}{group_bys}{order_bys}{limits}{offsets}"
        },
        "select_for_update": {
            "pysqlite": "SELECT{columns}FROM{tables}{wheres}{group_bys}{order_bys}{limits} FOR UPDATE",
            "pymysql": "SELECT{columns}FROM{tables}{wheres}{group_bys}{order_bys}{limits} FOR UPDATE"
        },
        "insert": {
            "pysqlite": "INSERT INTO {table} ({columns}) VALUES ({values})",
            "pymysql": "INSERT INTO {table} ({columns}) VALUES ({values})"
        },
        "update": {
            "pysqlite": "UPDATE {tables}{updates}{wheres}",
            "pymysql": "UPDATE {tables}{updates}{wheres}{limits}"
        },
        "delete": {
            "pysqlite": "DELETE FROM {qualified_table} WHERE rowid IN (SELECT rowid FROM {tables}{wheres}{limits})",
            "pymysql": "DELETE FROM{tables}{wheres}{limits}"
        },
        "primary_keys": {
            "pysqlite": "SELECT name as Field FROM PRAGMA_TABLE_INFO('{table}') WHERE pk = 1",
            "pymysql": "SHOW COLUMNS FROM {table} WHERE `Key` = 'PRI'"
        },
    }

    def __init__(self, driver: DBDrivers):
        self.driver = driver if driver else DBDrivers.SQLITE

    @property
    def select(self) -> str:
        return self.statement_format['select'][self.driver]

    @property
    def select_for_update(self) -> str:
        return self.statement_format['select_for_update'][self.driver]

    @property
    def insert(self) -> str:
        return self.statement_format['insert'][self.driver]

    @property
    def update(self) -> str:
        return self.statement_format['update'][self.driver]

    @property
    def delete(self) -> str:
        return self.statement_format['delete'][self.driver]

    @property
    def primary_keys(self) -> str:
        return self.statement_format['primary_keys'][self.driver]
