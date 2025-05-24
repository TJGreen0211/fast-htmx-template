import sys
import inspect
import typing
from datetime import datetime, date

from ..db_connection import DBQuery
from ..db_model import DBModel


class DBUtility(object):
    field_mapping = {
        int: "INTEGER",
        float: "FLOAT",
        str: "VARCHAR(255)",
        date: "DATE",
        datetime: "DATETIME",
        bytes: "BLOB",
        bool: "BOOLEAN",
        dict: "TEXT",
    }

    @classmethod
    def drop(cls, table: DBModel):
        qualified_name = '.'.join([x for x in [table.schema_, table.table_] if x])
        with DBQuery(table.schema_, table.table_) as conn:
            conn.execute(f"DROP TABLE IF EXISTS {qualified_name}")

    @classmethod
    def migrate(cls, table: DBModel, drop_table=True):
        if drop_table:
            cls.drop(table)
        columns = []
        for name, field in table.model_fields.items():
            annotated_type, nullable = (
                typing.get_args(field.annotation)[0], typing.get_args(field.annotation)[1] is type(None)) \
                if len(typing.get_args(field.annotation)) == 2 else (field.annotation, False)
            primary_key = (field.json_schema_extra or {}).get("primary_key")

            try:
                f_str = f"{name} {cls.field_mapping[annotated_type]}"
            except Exception:
                # Default to TEXT if no mapping exists
                f_str = f"{name} TEXT"

            if (name in ['created', 'modified'] and annotated_type == datetime):
                f_str = f_str + " DEFAULT CURRENT_TIMESTAMP"

            f_str = f_str + " PRIMARY KEY AUTOINCREMENT" if primary_key else f_str
            f_str = f_str if nullable or primary_key else f_str + " NOT NULL"

            columns.append(f_str)

        column_str = ',\n'.join(columns)
        try:
            metadata = '\n'.join([
                "UNIQUE (" + ', '.join(key for key in uk.key) + ")" + f" ON CONFLICT {uk.conflict}"
                for uk in table.metadata_.unique_keys
            ])
        except AttributeError:
            metadata = ""
        sql = f"CREATE TABLE {table.table_}(\n{column_str}\n{',' + metadata if metadata else ""})"

        with DBQuery(table.schema_, table.table_) as conn:
            conn.execute(sql)

        return sql

    @classmethod
    def migrate_all(cls, module):
        for name, obj in inspect.getmembers(sys.modules[__name__]):
            print(name)
            if inspect.isclass(obj):
                print(obj)

    @classmethod
    def table_to_model(cls, schema: str, table: str) -> str:
        field_mapping = {
            "int": "int",
            "float": "float",
            "varchar": "str",
            "text": "str",
            "json": "dict",
            "timestamp": "datetime",
            "datetime": "datetime",
            "tinyint": "bool",
            "date": "date",
            "bit": "bool",
            "double": "float",
            "mediumtext": "str",
            "longtext": "str",
        }
        data = []
        with DBQuery(schema, table) as conn:
            data = conn.execute(f"SHOW COLUMNS FROM {conn.qualified_table_name}")
        if not data:
            raise ValueError("Table not found")

        model_str = "class "
        model_str = model_str + "".join(x.capitalize() for x in table.lower().split("_"))

        model_str = model_str + "(DBModel):"
        model_str = model_str + f"\n    schema_ = '{schema}'"
        model_str = model_str + f"\n    table_ = '{table}'\n"
        model_str = model_str + "\n    "
        model_str = model_str + "    ".join(
            (f"{field['Field']}: "
             f"{'Optional[' if field['Null'] == 'YES' else ''}"
             f"{field_mapping[field['Type'].split('(')[0]]}"
             f"{']' if field['Null'] == 'YES' else ''}"
             f"{' = Field(primary_key=True)' if field['Key'] == 'PRI' else ''}\n")
            for field in data)
        return model_str
