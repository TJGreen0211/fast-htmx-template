"""
:date_created: 2022-06-15
"""
import json
import sys
import time
import typing
import logging
from typing import Any, ClassVar
# from pymysql import IntegrityError
from typing_extensions import Self
from pydantic import BaseModel, ConfigDict, JsonValue, PrivateAttr, Field as _Field
from pydantic._internal._model_construction import ModelMetaclass

from .utils.statements import JoinType
from .db_connection import DBQuery, DirectDBConnection
from .utils.terms import QueryFilter, Term

logging.basicConfig(stream=sys.stdout)
logger = logging.getLogger(__name__)
logger.setLevel(logging.CRITICAL)


def Field(
    primary_key: bool=None,
    foreign_keys: Term=None,
    join: JoinType=None,
    alias: str=None,
    foreign_key: Term=None,
    **kwargs
):
    json_schema_extra = {}
    for key, value in {
        'primary_key': primary_key,
        'foreign_keys': foreign_keys,
        'join': join,
        'alias': alias,
        'foreign_key': foreign_key
    }.items():
        if value:
            json_schema_extra[key] = value
    kwargs.update(json_schema_extra)
    return _Field(**kwargs)


class DBModelUniqueKey(BaseModel):
    key: tuple
    conflict: typing.Optional[str]


class DBModelMetadata(BaseModel):
    unique_keys: typing.Optional[list[DBModelUniqueKey]]


class DBModelException(Exception):
    """Exception class for DBQuery errors"""
    pass


class DBMetaModel(object):
    def __init__(
        self, name: str, model: Any, listable: bool, foreign_keys: Term, join: JoinType=JoinType.LEFT, alias: str=None
    ):
        self.name = name
        self.model = model
        self.foreign_keys = foreign_keys
        self.listable = listable
        self.join = join if join else JoinType.LEFT
        self.mapping = None
        self.alias = alias


class QueryNode(object):
    def __init__(self, current: Any, neighbor: Any):
        self.current = current
        self.neighbor = neighbor

    def __repr__(self):
        return f'{self.current.__name__} -> {self.neighbor.__name__}'


class QueryGraph:
    def __init__(self, _query: DBQuery, vertices: dict[str, DBMetaModel]):
        self.V = [v.model for v in vertices.values()]
        self.num_nodes = len(self.V)
        self.graph = [[] for _ in self.V]
        self.vertices = vertices

        self.selects: dict[str, DBQuery] = {
            v.model.__name__: DBQuery(v.model.schema_, v.model.table_).select(
                *v.model._model_columns() if not v.listable else [None]
            ) for v in vertices.values()
        }

        self.select = _query
        if len(self.V) > 1:
            for vertex in vertices.values():
                if vertex.foreign_keys:
                    self.add_edge(vertex.model, vertex.foreign_keys.right.model)

            self.select = self.bfs(self.V[0])

        seen = set()
        seen_add = seen.add
        self.table_order = [
            x for x in [x.rsplit('.', 1)[0] for x in self.select._columns] if not (x in seen or seen_add(x))
        ]

    @property
    def query(self):
        return self.select.select(*self.V[0]._model_columns())

    def add_edge(self, u: str, v: str):
        self.graph[self.V.index(u)].append(self.V.index(v))
        self.graph[self.V.index(v)].append(self.V.index(u))

    def bfs(self, start) -> DBQuery:
        visited = [False] * self.num_nodes
        queue = []
        order: list[QueryNode] = []

        queue.append(self.V.index(start))
        visited[self.V.index(start)] = True

        while queue:
            current = queue.pop(0)
            for neighbor in self.graph[current]:
                if not visited[neighbor]:
                    # TODO: Reverse bfs so second loop can be skipped
                    order.append(QueryNode(self.V[current], self.V[neighbor]))
                    queue.append(neighbor)
                    visited[neighbor] = True

        for item in reversed(order):
            foreign_key = None
            for v in self.vertices.values():
                if v.model == item.neighbor:
                    v.mapping = next(x.name for x in self.vertices.values() if x.model == item.current)
                    foreign_key = v

            if not foreign_key:
                raise DBModelException(f"No foreign key defined for {item.neighbor}")

            select = self.selects[item.current.__name__].join(
                self.selects[item.neighbor.__name__],
                foreign_key.foreign_keys.left,
                foreign_key.foreign_keys.right.name,
                join_type=foreign_key.join
            )

            self.selects[item.current.__name__] = select

        return self.selects[start.__name__]


class DBModelMeta(ModelMetaclass):
    def __new__(mcs, name, bases, attrs):
        # Custom new for BaseModel Metaclass to override default behaviour
        cls = super().__new__(mcs, name, bases, attrs)
        if not cls.__base__ == BaseModel:
            # Set schema and table listable classes
            if cls._is_multiple():
                cls.schema_ = cls._listable()[0].get('type').schema_
                cls.table_ = cls._listable()[0].get('type').table_
            # Check for a pk
            if not cls._is_multiple() and not cls._primary_keys():
                raise DBModelException('At least one primary key is required for a base model.')
            if not cls.table_:
                raise DBModelException('Table and schema are required.')

            subclasses = cls._subclasses()
            listable = cls._listable()

            base = {'name': cls.__name__, 'type': cls.__base__ if (
                subclasses or (listable and not cls._is_multiple())) else cls, 'list': False}

            submodels = subclasses + listable
            vertices = {base['name']: DBMetaModel(base['name'], base['type'], False, {})}

            # Legacy Foreign Keys. No longer supported use foreign_keys instead
            for m in submodels + [base]:
                for field_name, field_info in m['type'].model_fields.items():
                    if field_info.json_schema_extra and field_info.json_schema_extra.get('foreign_key'):
                        fk = field_info.json_schema_extra.get('foreign_key')
                        if fk.model in [x['type'] for x in submodels + [base]]:
                            vertices[m['name']] = DBMetaModel(
                                m['name'],
                                m['type'],
                                m['list'],
                                getattr(m['type'], field_name) == fk)

            for m in submodels:
                if not vertices.get(m['name']):
                    vertices[m['name']] = DBMetaModel(
                        m['name'],
                        m['type'],
                        m['list'],
                        m['meta'].get('foreign_keys'),
                        m['meta'].get('join'),
                        m['meta'].get('alias')
                    )
            # Joins and fields are set at class creation so we get those here
            # so this doesn't have to run every time .load() is called
            cls._query_graph = QueryGraph(DBQuery(cls.schema_, cls.table_), vertices)
            cls._qualified_table_name = '.'.join([x for x in [cls.schema_, cls.table_] if x])
            cls._base = base['type']

        return cls

    def __getattribute__(cls, key):
        if key in ["model_fields", "__dict__"]:
            return super().__getattribute__(key)
        if key not in cls.model_fields:
            return super().__getattribute__(key)
        # Allows for accessing terms as class attributes (e.g, Location.account_id)
        return Term(key, cls.model_fields[key].annotation, model=cls)

    @property
    def as_sql(self):
        if self._is_multiple():
            return self._listable()[0].get('type')._query_graph.query.as_sql
        return self._query_graph.query.as_sql


class DBModel(BaseModel, metaclass=DBModelMeta):
    """
    This class is meant as a drop in replacement for the old base_model classes.
    (e.g: Creatable, Loadable, Savable, etc...). It uses pydantic BaseModel instead of do_py.

    You can use this class to define database queries instead of creating a new stored procedure.
    The same functions are able to be used on a record and the properties defined are able
    to be accessed with dot notation.
    """
    model_config = ConfigDict(validate_assignment=True)

    schema_: ClassVar[str]
    table_: ClassVar[str]
    metadata_: ClassVar[DBModelMetadata]

    _wheres: list = PrivateAttr()
    _order_bys: list = PrivateAttr()
    _group_bys: list = PrivateAttr()
    _offset: int = PrivateAttr(default=0)
    _limit: int = PrivateAttr(default=100)
    _has_more: int = PrivateAttr(default=True)

    _multiple: bool = PrivateAttr(default=False)
    _original_state: dict = PrivateAttr()
    _query: DBQuery = PrivateAttr()
    _statement: str = PrivateAttr(default='')

    _query_graph: QueryGraph = PrivateAttr()
    _base: 'DBModel' = PrivateAttr()
    _qualified_table_name: str = PrivateAttr()

    def __init__(self, **data):
        """Constructor method"""
        super().__init__(**data)
        self._query = DBQuery(self.schema_, self.table_)
        self._original_state = self.model_dump()

    @property
    def _required_keys(self) -> dict:
        current_state = self.model_dump()
        return {
            name: current_state[name] for name in self.model_fields.keys() if name in self._primary_keys()
        }

    @classmethod
    def as_sql(cls) -> str:
        return cls._query_graph.query.as_sql

    @property
    def _modified_fields(self) -> dict:
        update_fields = {}

        mod_state = self.model_dump()
        for key in self._model_columns():
            if self._original_state.get(key) != mod_state.get(key):
                update_fields[key] = mod_state.get(key)
        return update_fields

    @classmethod
    def _primary_keys(cls) -> list:
        if cls._subclasses():
            base = cls.__base__
        elif cls._listable():
            base = cls._listable()[0]['type']
        else:
            base = cls
        return [
            field_name for field_name, field_info in base.model_fields.items()
            if (field_info.json_schema_extra or {}).get('primary_key')
        ]

    @classmethod
    def _foreign_keys(cls, model: 'DBModel') -> DBMetaModel:
        for v in cls._query_graph.vertices.values():
            if v.model == model and not cls._is_multiple():
                return v

    @classmethod
    def _model_columns(cls) -> list:
        return [key for key, value in cls.model_fields.items() if all(
            typing.get_origin(x) is not list and not (isinstance(x, type) and issubclass(x, DBModel))
            for x in list(
                typing.get_args(value.annotation) if (
                    typing.get_args(value.annotation) and typing.get_origin(value.annotation) is not list
                ) else (value.annotation,)
            ))
        ]

    @classmethod
    def _parse_response(cls, data: dict) -> dict:
        for name, field in cls.model_fields.items():
            annotation = typing.get_args(field.annotation)[0] if (
                typing.get_args(field.annotation) and typing.get_origin(field.annotation) is not list
            ) else field.annotation
            try:
                if annotation == dict:
                    data[name] = json.loads(data.get(name))
                elif annotation == list:
                    data[name] = json.loads(data.get(name))
                elif issubclass(annotation, DBModel):
                    data[name] = annotation._parse_response(data.get(name))
                elif issubclass(annotation, BaseModel):
                    data[name] = json.loads(data.get(name))
                elif annotation == JsonValue:
                    data[name] = json.loads(data.get(name))
            except Exception:
                # Let pydantic handle it with a validation error
                pass
        return data

    def _update_model(self, data: dict):
        data = self.__class__.model_validate(self._parse_response(data))
        self.__dict__.update(data)
        self._original_state = self.model_dump()

        return self

    @classmethod
    def _format_data(cls, subclasses: list[dict[str, 'DBModel']], tables: list, item: tuple) -> dict:
        columns = cls._model_columns()
        data = {columns[i]: item[i] for i in range(len(columns))}

        offset = len(columns)
        for table in tables:
            sub = next(iter([
                x for x in subclasses if '.'.join([x for x in [x['type'].schema_, x['type'].table_] if x]) == table
            ]), None)
            if sub:
                columns = sub['type']._model_columns()
                sub_name = sub['name']
                data[sub_name] = {columns[i]: item[i+offset] for i in range(len(columns))}
                offset = offset+len(columns)
                # Null for optional fields
                if all(v is None for v in data[sub_name].values()):
                    data[sub_name] = None
        return data

    @classmethod
    def _subclasses(cls) -> list[dict[str, 'DBModel']]:
        subclasses = []
        for key, value in cls.model_fields.items():
            subclasses.extend([
                {'name': key, 'type': x, 'list': False, 'meta': value.json_schema_extra or {}} for x in list(
                    typing.get_args(value.annotation) if (
                        typing.get_args(value.annotation) and typing.get_origin(value.annotation) is not list
                    ) else (value.annotation,)
                ) if typing.get_origin(x) is not list and (isinstance(x, type) and issubclass(x, DBModel))
            ])

        return subclasses

    @classmethod
    def _listable(cls) -> list[dict[str, 'DBModel']]:
        return [
            {
                'name': key,
                'type': typing.get_args(value.annotation)[0] if typing.get_origin(value.annotation) == list
                else typing.get_args(typing.get_args(value.annotation)[0])[0],
                'list': True,
                'meta': value.json_schema_extra or {}
            }
            for key, value in cls.model_fields.items() if any([
                typing.get_origin(x) is list for x in list(
                    typing.get_args(value.annotation) if (
                        typing.get_args(value.annotation) and typing.get_origin(value.annotation) is not list
                    ) else (value.annotation,)
                )
            ])
        ]

    def __bool__(self):
        if self._is_multiple():
            return any([
                getattr(self, k) if hasattr(self, k) else False for k in dict(self.model_fields.items()).keys()])
        else:
            return True if all([
                (lambda x: getattr(self, x) if hasattr(self, x) else False)(key) for key in self._primary_keys()
            ]) else False

    @classmethod
    def _is_multiple(cls):
        field_values = [value for value in cls.model_fields.values()]
        if len(field_values) == 1 and typing.get_origin(field_values[0].annotation) == list:
            return True
        return False

    def next(self):
        _limit = self._limit if self._is_multiple() else 1
        _offset = self._offset + self._limit if self._offset else self._limit
        if self._is_multiple():
            _order_bys = self._order_bys if self._order_bys else (
                Term(
                    self._listable()[0].get('type')._primary_keys()[0],
                    self._listable()[0].get('type'),
                    schema=self.schema_,
                    table=self.table_),
            )
        else:
            _order_bys = self._order_bys if self._order_bys else (
                Term(
                    self._primary_keys()[0],
                    self.__class__,
                    schema=self.schema_,
                    table=self.table_),
            )

        return self.load(
            *self._wheres,
            order_by=_order_bys,
            limit=_limit,
            offset=_offset
        )

    def prev(self):
        _limit = self._limit if self._is_multiple() else 1

        _offset = self._offset - self._limit if self._offset else self._limit
        if self._offset < 0:
            _offset = 0
        if self._is_multiple():
            _order_bys = self._order_bys if self._order_bys else (
                Term(
                    self._listable()[0].get('type')._primary_keys()[0],
                    self._listable()[0].get('type'),
                    schema=self.schema_,
                    table=self.table_),
            )
        else:
            _order_bys = self._order_bys if self._order_bys else (
                Term(
                    self._primary_keys()[0],
                    self.__class__,
                    schema=self.schema_,
                    table=self.table_),
            )

        return self.load(
            *self._wheres,
            order_by=_order_bys,
            limit=_limit,
            offset=_offset
        )

    def find(self, field: Term, value: Any) -> Any:
        """Find for the first matching attribute in the model

        :param field: field to search on
        :param value: value

        :return: DBModel or None
        """

        # Search term is in the top level model
        if field.name in self._model_columns():
            # Search through model array
            if self._is_multiple():
                attr = getattr(self, self._listable()[0].get('name'))
                if isinstance(attr, list):
                    return next(iter([x for x in attr if getattr(x, field.name) == value]), None)
            # Search for specific matching term
            else:
                return self if getattr(self, field.name) == value else None
        # Search in the listable models
        elif field.model in [x.get('type') for x in self._listable()]:
            subclass = next(iter([x for x in self._listable() if x.get('type') == field.model]), None)
            attr = getattr(self, subclass.get('name'))
            return next(iter([x for x in attr if getattr(x, field.name) == value]), None)
        # Search in the matching submodels
        elif field.model in [x.get('type') for x in self._subclasses()]:
            subclass = next(iter([x for x in self._subclasses() if x.get('type') == field.model]), None)
            attr = getattr(self, subclass.get('name'))
            return attr if getattr(attr, field.name) == value else None
        # Invalid search field
        else:
            raise DBModelException("Invalid search field")

    def find_all(self, field: Term, value: Any) -> list[Any]:
        # Search term is in the top level model
        if field.name in self._model_columns():
            # Search through model array
            if self._is_multiple():
                attr = getattr(self, self._listable()[0].get('name'))
                if isinstance(attr, list):
                    return [x for x in attr if getattr(x, field.name) == value]
            # Search for specific matching term
            else:
                return self if getattr(self, field.name) == value else None
        # Search in the listable models
        elif field.model in [x.get('type') for x in self._listable()]:
            subclass = next(iter([x for x in self._listable() if x.get('type') == field.model]), None)
            attr = getattr(self, subclass.get('name'))
            return [x for x in attr if getattr(x, field.name) == value]
        # Search in the matching submodels
        elif field.model in [x.get('type') for x in self._subclasses()]:
            subclass = next(iter([x for x in self._subclasses() if x.get('type') == field.model]), None)
            attr = getattr(self, subclass.get('name'))
            return attr if getattr(attr, field.name) == value else None
        # Invalid search field
        else:
            raise DBModelException("Invalid search field")

    @classmethod
    def count_(cls, *args: Term) -> int:
        model = cls
        if cls._is_multiple():
            model = cls._listable()[0].get('type')

        # Reconstruct the query so we don't modify the cls QueryGraph
        inner_query = DBQuery(model.schema_, model.table_)
        joins = []
        for v in model._query_graph.selects.values():
            for x in v.joins:
                q = DBQuery(x.schema, x.table)
                q.join_type = x.join_type
                join_from = f"{x.join_on.column}"
                join_to = f"{x.join_on.value}"
                q.join_on = QueryFilter(join_from, join_to, is_join=True)
                q.parent_table = x.qualified_table_name
                joins.append(q)
        inner_query.joins = joins
        terms = [arg for arg in args]
        inner_query = inner_query.select(
            f"COUNT({model._qualified_table_name}.{model._primary_keys()[0]}) as inner_query_count").where(
                *terms).group_by(f"{model._qualified_table_name}.{model._primary_keys()[0]}")
        inner_query.multiple = True
        inner_sql = inner_query.prepare
        # Abusing DBQuery to get the count.
        # This creates a subquery - which should be implemented natively in the future
        outer_query = DBQuery('', f'({inner_sql}) as count').select("COUNT(inner_query_count) as count")
        outer_sql = outer_query.prepare
        outer_query.query_args.update(inner_query.query_args)

        with outer_query:
            return outer_query.execute(outer_sql, outer_query.query_args, multiple=False).get('count')
        return 1

    @classmethod
    def distinct_(cls, *args: Term) -> list['DBModel']:
        """Select distinct rows from the database

        :param args: optional filter terms

        :return: list of DBModel instances
        """
        model = cls
        if cls._is_multiple():
            model = cls._listable()[0].get('type')

        # Reconstruct the query so we don't modify the cls QueryGraph
        inner_query = DBQuery(model.schema_, model.table_)
        joins = []
        for v in model._query_graph.selects.values():
            for x in v.joins:
                q = DBQuery(x.schema, x.table)
                q.join_type = x.join_type
                join_from = f"{x.join_on.column}"
                join_to = f"{x.join_on.value}"
                q.join_on = QueryFilter(join_from, join_to, is_join=True)
                q.parent_table = x.qualified_table_name
                joins.append(q)
        inner_query.joins = joins
        terms = [arg for arg in args]
        inner_query = inner_query.select("*").where(*terms)
        # Add distinct clause
        inner_query = inner_query.distinct()
        inner_sql = inner_query.prepare
        # Abusing DBQuery to get the distinct rows.
        # This creates a subquery - which should be implemented natively in the future
        outer_query = DBQuery('', f'({inner_sql}) as distinct_rows').select("*")
        outer_sql = outer_query.prepare
        outer_query.query_args.update(inner_query.query_args)

        with outer_query:
            result = outer_query.execute(outer_sql, outer_query.query_args, multiple=True)
            return [
                cls._parse_response(
                    cls._format_data(cls._subclasses(), cls._query_graph.table_order, item)
                ) for item in result
            ] if result else []

    @classmethod
    def max_(cls, field: Term) -> 'DBModel':
        # model = cls
        # if cls._is_multiple():
        #     model = cls._listable()[0].get('type')
        raise NotImplementedError("TODO: Implement max_")

    @classmethod
    def min_(cls, field: Term) -> 'DBModel':
        # model = cls
        # if cls._is_multiple():
        #     model = cls._listable()[0].get('type')
        raise NotImplementedError("TODO: Implement min_")

    @classmethod
    def sum_(cls, field: Term) -> 'DBModel':
        # model = cls
        # if cls._is_multiple():
        #     model = cls._listable()[0].get('type')
        raise NotImplementedError("TODO: Implement sum_")

    @classmethod
    def avg_(cls, field: Term) -> 'DBModel':
        # model = cls
        # if cls._is_multiple():
        #     model = cls._listable()[0].get('type')
        raise NotImplementedError("TODO: Implement avg_")

    @classmethod
    def _load(
        cls, conn,
        *terms: Term,
        order_by: tuple=(),
        group_by: tuple=(),
        for_update: tuple=(),
        limit: int=10,
        offset: int=0,
        multiple=False,
        debug=False
    ) -> Self:
        load_start = time.time()
        subclasses = cls._subclasses()
        listable = cls._listable()

        _query = cls._query_graph.query
        if for_update:
            _query = _query.for_update(
                cls._primary_keys()[0], **{update.left: update.right for update in for_update}
            )
        _query._conn = conn

        _query.wheres = [x for x in terms if x.model in cls._query_graph.V]
        _query.offsets = offset
        _query.order_bys = [x for x in order_by if x.model in cls._query_graph.V]

        # If group_by is not specified, we will group by all columns
        # This will keep duplicates from being retuned from listable models
        _query.group_bys = [x for x in group_by if x.model in cls._query_graph.V] if any(group_by) else []

        if not _query.group_bys and not group_by:
            _query.group_bys = [i+1 for i in range(len(_query._prepare_columns.split(',')))]

        data = {}
        if debug:
            print(_query.as_sql)

        if cls._model_columns():  # Is not a list
            if limit and multiple is True:
                _query.limits = limit
            data = _query.run_multiple if multiple is True else _query.run

            if multiple is True:
                data = [
                    cls._parse_response(
                        cls._format_data(subclasses, cls._query_graph.table_order, item)
                    ) for item in _query.query_data
                ] if _query.query_data else []
            else:
                data = cls._parse_response(
                    cls._format_data(
                        subclasses, cls._query_graph.table_order, _query.query_data
                    )
                ) if _query.query_data else {}

        for model in listable:
            base = cls.__base__ if (cls._subclasses() or cls._listable()) else cls
            foreign_key = None

            foreign_key = cls._foreign_keys(model['type'])

            if foreign_key and not data:
                continue

            model_args = list(terms)
            if (foreign_key and data):
                if foreign_key.foreign_keys.right.model == base:
                    model_args = model_args + [Term(foreign_key.foreign_keys.name, model=model['type']) == (
                        list(set(
                            x[foreign_key.foreign_keys.right.name] for x in data
                        )) if isinstance(data, list) else data[foreign_key.foreign_keys.right.name])
                    ]
                else:
                    model_args = model_args + [Term(foreign_key.foreign_keys.name, model=model['type']) == (
                        list(set(
                            x[foreign_key.mapping][foreign_key.foreign_keys.right.name] for x in data
                        )) if isinstance(data, list) else data[foreign_key.mapping][foreign_key.foreign_keys.right.name]
                    )]

            submodel_limit = limit if cls._is_multiple() else None

            listable_data = model['type']._load(
                conn,
                *model_args,
                order_by=order_by,
                group_by=group_by,
                for_update=for_update,
                limit=submodel_limit,
                offset=offset,
                multiple=True,
                debug=debug
            )

            if isinstance(data, list):
                for item in data:
                    if foreign_key.foreign_keys.right.table == cls.table_:
                        item[model['name']] = list(filter(
                            lambda d: d[foreign_key.foreign_keys.name] == item[foreign_key.foreign_keys.right.name],
                            listable_data))
                    else:
                        cs = next(cs for cs in cls._subclasses()
                                  if cs['type'].table_ == foreign_key.foreign_keys.right.table)
                        item[model['name']] = list(filter(
                            lambda d: d[foreign_key.foreign_keys.name] == item[cs['name']][
                                foreign_key.foreign_keys.right.name],
                            listable_data
                        ))

            else:
                data[model['name']] = listable_data

        if multiple is True:
            return data

        if data:
            instance = cls(**cls._parse_response(data))
        else:
            instance = cls.model_construct(**{key: None for key in cls.model_fields.keys()})

        instance._limit = limit
        instance._offset = offset
        instance._wheres = terms
        instance._order_bys = order_by
        instance._group_bys = group_by
        instance._statement = _query

        if debug:
            print(f"Load took {time.time() - load_start} seconds")

        return instance

    @classmethod
    def load(
        cls, *args: Term,
        order_by: tuple=(),
        group_by: tuple=(),
        for_update: tuple=(),
        limit: int=None,
        offset: int=0,
        debug=False,
        **kwargs
    ) -> Self:
        terms = [arg for arg in args]
        # Kwargs are legacy and should not be used
        # Use the class attribute for args (e.g. SomeDBModel.id == 1)
        if kwargs:
            terms.extend([
                Term(key, model=cls) == value for key, value in kwargs.items()
            ])

        # if not all(term.model in cls._query_graph.V for term in terms):
        #     raise DBModelException(f"Invalid term in model: {cls.__name__}")
        with DirectDBConnection() as conn:
            return cls._load(
                conn._conn,
                *terms,
                order_by=order_by if isinstance(order_by, tuple) else (order_by,),
                group_by=group_by if isinstance(group_by, tuple) else (group_by,),
                for_update=for_update if isinstance(for_update, tuple) else (for_update,),
                limit=limit,
                offset=offset,
                debug=debug
            )

    @classmethod
    def _create(cls, conn, select=True, **kwargs) -> Self:
        # Populate any defaults
        temp_construct = cls.model_construct(**cls._parse_response(kwargs))

        data = {}
        for item in cls._model_columns():
            if hasattr(temp_construct, item) and not kwargs.get(item):
                value = getattr(temp_construct, item)
                # Hack to remove terms as they get populated with inherited models
                # This has to do with the metaclass and probably needs to be solved correctly
                # but this works for now...
                if not isinstance(value, Term):
                    kwargs[item] = value

        # We assume that the primary model has to be created before the submodels
        model = cls
        model_name = None

        if cls._is_multiple():
            model = cls._listable()[0].get('type')
            model_name = cls._listable()[0].get('name')
            item_list = []
            for item in kwargs.get(model_name):
                item_list.append({key: value for key, value in item.items() if key in model._model_columns()})
            data[model_name] = DBQuery(model.schema_, model.table_, conn).insert(*item_list, select=select).run_multiple

        else:
            for new_key, new_value in DBQuery(model.schema_, model.table_, conn).insert(
                select=select,
                **{key: value for key, value in kwargs.items() if key in model._model_columns()}
            ).run.items():
                data[new_key] = new_value

        d = data[model_name] if cls._is_multiple() else [data]
        for i, model_data in enumerate(d):
            kwarg_key = kwargs[model_name][i] if cls._is_multiple() else kwargs
            data_key = data[model_name][i] if cls._is_multiple() else data
            for item in model._subclasses():
                sub_data = kwarg_key[item['name']]
                fks = model._foreign_keys(item['type'])
                sub_data[fks.foreign_keys.name] = model_data[fks.foreign_keys.right.name]
                model_data[item['name']] = item['type']._create(conn, **sub_data)
            for item in model._listable():
                sub_data = kwarg_key[item['name']]
                fks = model._foreign_keys(item['type'])
                for val in sub_data:
                    val[fks.foreign_keys.name] = data_key[fks.foreign_keys.right.name]
                model_data[item['name']] = [item['type']._create(conn, **data) for data in sub_data]

        # Validate the data and return
        if select:
            if cls._is_multiple():
                return cls(**cls._parse_response(data))
            return model(**model._parse_response(data))
        return data

    @classmethod
    def create(cls, on_duplicate_update: tuple[Term]=None, select=True, **kwargs) -> Self:
        """Create"""
        with DirectDBConnection() as conn:
            try:
                return cls._create(conn._conn, select=select, **kwargs)
            except Exception as e:
                # if on_duplicate_update:
                #     raise
                #     # for field in on_duplicate_update:
                # else:
                raise e

    def _save(self, conn):
        for item in self._listable():
            if getattr(self, item['name']) is not None:
                setattr(self, item['name'], [model._save(conn) for model in getattr(self, item['name'])])
        for item in self._subclasses():
            if getattr(self, item['name']) is not None:
                setattr(self, item['name'], getattr(self, item['name'])._save(conn))

        if self._modified_fields:
            data = DBQuery(self.schema_, self.table_, conn
                           ).update(**self._modified_fields).where(**self._required_keys).run
            for key, value in self._parse_response(data).items():
                if key in self._model_columns():
                    setattr(self, key, value)

        # Valdate the updates and return the instance
        # TODO: This may be slow for large models
        return self._update_model(self.model_dump())

    def save(self) -> Self:
        """Save"""
        with DirectDBConnection() as conn:
            return self._save(conn._conn)

    def _delete(self, conn, cascade=False) -> bool:
        base_name = self._listable()[0].get('name') if self._is_multiple() else None

        # If cascade delete will run for all sub models
        statuses = []
        if cascade:
            base_model = getattr(self, base_name) if self._is_multiple() else [self]
            for base_item in base_model:
                for item in base_item._listable():
                    statuses.extend([model._delete(
                        conn, cascade=cascade) for model in getattr(base_item, item['name'])])
                for item in base_item._subclasses():
                    statuses.append(getattr(base_item, item['name'])._delete(conn, cascade=cascade))
            statuses = all(statuses) if statuses else True

        if self._is_multiple():
            item_list = []
            for item in getattr(self, base_name):
                item_list.append({key: value for key, value in item._required_keys.items()})

            # Model is empty and there is nothing to delete
            if not item_list:
                return [{'status': False}]

            pks = set().union(*(d.keys() for d in item_list))
            delete_kwargs = {pk: [i.get(pk) for i in item_list] for pk in pks}
            # This should be caught in DBQuery but adding extra safety
            if not delete_kwargs:
                raise DBModelException(f"Error no delete arguments supplied for{self.schema_}.{self.table_}. "
                                       "Please check the model definition")

            return DBQuery(self.schema_, self.table_, conn=conn).delete().where(**delete_kwargs).run_multiple
        else:
            if self._required_keys:
                return DBQuery(self.schema_, self.table_, conn=conn
                               ).delete().where(**self._required_keys).run.get('status')
        return statuses

    def delete(self, cascade=False) -> bool:
        """Delete"""
        with DirectDBConnection() as conn:
            return self._delete(conn._conn, cascade=cascade)
