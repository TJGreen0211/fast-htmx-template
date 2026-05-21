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
        with DBQuery(table.schema_, table.table_) as conn:
            conn.execute(f"DROP TABLE IF EXISTS {table._qualified_table_name}")

    @classmethod
    def migrate(cls, table: DBModel, drop_table=False):
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

        column_str = ',\n    '.join(columns)
        try:
            metadata = '\n'.join([
                "UNIQUE (" + ', '.join(key for key in uk.key) + ")" + f" ON CONFLICT {uk.conflict}"
                for uk in table.metadata_.unique_keys
            ])
        except AttributeError:
            metadata = ""

        fk_strs = []
        # for name, value in table.model_fields.items():
        #     if value.json_schema_extra and value.json_schema_extra.get('foreign_key'):
        #         fk = value.json_schema_extra.get('foreign_key')
        #         fk_strs.append((
        #             f"CONSTRAINT `fk_{table.table_}_{name}` "
        #             f"FOREIGN KEY (`{name}`) REFERENCES {fk.qualified_table_name} (`{fk.name}`)"
        #         ))
        fk_str = ",\n".join(fk_strs)
        fk_str = f",\n    {fk_str}" if fk_str else ""

        sql = (
            f"CREATE TABLE IF NOT EXISTS {table._qualified_table_name}("
            f"\n    {column_str}{',' + metadata if metadata else ''}{fk_str}\n);"
        )

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

        model_name = "".join(x.capitalize() for x in table.lower().split("_"))
        model_str = f"class {model_name}"

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

        list_str = "class "
        list_str = list_str + model_name + 's'
        list_str = list_str + "(DBModel):"
        list_str = list_str + f"\n    schema_ = {model_name}.schema_"
        list_str = list_str + f"\n    table_ = {model_name}.table_\n"
        list_str = list_str + "\n    "
        list_str = list_str + f"{table}s: list[{model_name}]"

        return f"{model_str}\n\n{list_str}\n"

    @classmethod
    def sql_str_to_model(cls, cls_name: str, sql: str) -> str:
        base_path = 'from kilimanjaro_src.db.'
        keywords = [
            'select', 'from', 'join', 'left', 'right', 'inner', 'outer',
            'full', 'cross', 'hash', 'on', 'and', 'between', 'as'
        ]

        sql_parts = [s.strip().lower() for s in sql.split(' ') if s]
        base_table = ''
        joins = {}

        current_join = ''
        for i, part in enumerate(sql_parts):
            if part == 'from':
                base_table = sql_parts[i+1]

            if part == 'join':
                join = part
                if sql_parts[i-1] in keywords:
                    join = sql_parts[i-1] + ' ' + join
                if sql_parts[i-2] in keywords:
                    join = sql_parts[i-2] + ' ' + join
                current_join = sql_parts[i+1]
                joins[current_join] = {'join': join}
                if sql_parts[i+2] not in keywords:
                    alias = sql_parts[i+2]

                joins[current_join]['alias'] = alias if alias else ''

            if current_join:
                if part == 'on':
                    joins[current_join]['on'] = sql_parts[i+1]

                if part == '=':
                    joins[current_join]['to'] = sql_parts[i+1]

            if part == 'and':
                current_join = None

            if part == ';':
                break

        import_paths = {'db_model.db_model': ['Field']}

        model_name = "".join(x.capitalize() for x in base_table.split('.')[-1].lower().split("_"))
        model_str = f"class {cls_name}({model_name}):\n"
        for key, value in joins.items():
            key_location: str = key.split('.')[0]

            key_table: str = key.split('.')[-1]
            key_class_name = "".join(x.capitalize() for x in key_table.lower().split("_"))

            key_location: str = f"models.{key.split('.')[0]}"
            import_paths[key_location] = import_paths[key_location] + [key_class_name] if import_paths.get(
                key_location) else [key_class_name]

            join_class_name = ''
            join_to = value.get('to').split('.')[0]
            for x, y in joins.items():
                if y.get('alias') == join_to:
                    join_class_name = x.split('.')[-1]
            join_class_name = "".join(x.capitalize() for x in join_class_name.lower().split("_"))

            model_str = model_str + f"\t{key_table}: {key_class_name} = Field(\n"
            model_str = model_str + f"\t\tforeign_keys={key_class_name}.{value.get('on').split('.')[-1]} == "
            model_str = model_str + f"{join_class_name}.{value.get('to').split('.')[-1]}, join=JoinType.INNER)\n"
            model_str = model_str.replace('\t', '    ')

        import_str = ''
        for key, value in import_paths.items():
            import_str = import_str + f"{base_path}{key} import {', '.join(value)}\n"

        return f"{import_str}\n\n{model_str}"
