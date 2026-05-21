---
name: dbmodel
description: DBModel ORM framework for SQLite — model definition, queries, joins, CRUD, and migrations. Use when working with database models in server/src/models/ or writing queries with DBModel, Field, Term, DBQuery.
---

# DBModel ORM Framework

A Pydantic-based ORM built on top of SQLite for the DIHP app. All database models live in `server/src/models/`. The framework is implemented in `server/src/utils/db_model/`.

## Core Imports

```python
from src.utils.db_model.db_model import DBModel, Field
from src.utils.db_model.utils.statements import JoinType
```

## Defining Models

Every model requires `schema_` and `table_` class variables. Use `Field(primary_key=True)` to mark auto-increment primary keys.

```python
class Horse(DBModel):
    schema_ = ''
    table_ = 'horse'

    id: int = Field(primary_key=True)
    name: str
    owner_id: int
    created: datetime = Field(default=datetime.now())
    modified: datetime = Field(default=datetime.now())
```

### Field Types

- `int`, `str`, `float`, `bool` — standard types
- `bytes` — BLOB storage (images, binary data)
- `dict` — JSON columns (stored as TEXT, auto-serialized)
- `date`, `datetime` — date/time with DEFAULT CURRENT_TIMESTAMP support in migrations
- `Optional[T]` — nullable fields
- Nested `DBModel` — joined sub-models
- Nested `BaseModel` (from pydantic) — parsed from JSON columns
- `list[Model]` — one-to-many relationships

### Defaults

Use `Field(default=...)` for non-null defaults. Primary keys with `default=None` are auto-increment.

```python
combined: bool = Field(default=False)
metadata: Optional[dict]
created: datetime = Field(default=datetime.now())
```

## List Models (Querying Multiple Records)

To load multiple records, define a list wrapper model. The list model inherits `schema_` and `table_` from the base model:

```python
class Horses(DBModel):
    schema_ = Horse.schema_
    table_ = Horse.table_

    data: list[Horse]
```

Access results via the list field name (e.g., `horses.data`).

## Joins and Relationships

### Single Sub-model Join (One-to-One or Optional)

Define the relationship with `foreign_keys` using a comparison expression. The format is `Child.foreign_key == Parent.parent_key`.

```python
class EntryInfo(Entry):
    horse: Horse = Field(
        foreign_keys=Horse.id == Entry.horse_id,
        join=JoinType.INNER
    )
    rider: Person = Field(
        foreign_keys=Person.id == Entry.rider_id,
        join=JoinType.INNER
    )
```

### List Sub-model Join (One-to-Many)

Use `list[Model]` type annotation with `foreign_keys`:

```python
class ClassEntries(Class):
    entries: list[EntryInfo] = Field(
        foreign_keys=Entry.class_id == Class.id,
        join=JoinType.LEFT
    )
    live_data: Optional[LiveClass] = Field(
        foreign_keys=LiveClass.class_id == Class.id
    )
```

### Join Types

Import from `src.utils.db_model.utils.statements`:
- `JoinType.LEFT` (default)
- `JoinType.INNER`
- `JoinType.LEFT_OUTER`, `JoinType.RIGHT`, `JoinType.OUTER`, `JoinType.RIGHT_OUTER`, `JoinType.FULL_OUTER`, `JoinType.CROSS`, `JoinType.HASH`

### Legacy Foreign Key

Use `foreign_key=Model.field` for simple back-references (older pattern, still works):

```python
class UserMeta(DBModel):
    user_id: int = Field(foreign_key=User.id)
```

## CRUD Operations

### Load (Read)

```python
# Single record — returns instance or empty model
horse = Horse.load(Horse.name == "Spirit")

# Multiple records
horses = Horses.load(Horse.owner_id == 123)
# Access: horses.data

# With limit/offset
horses = Horses.load(limit=10, offset=20)
horses = Horses.load(limit=None)  # no limit

# With ordering
locations = MapLocations.load(
    order_by=(MapLocation.type, MapLocation.name.asc()),
    limit=None
)

# Multiple filter conditions (AND)
entries = Entries.load(
    Entry.class_id == 5,
    Entry.position != None
)

# LIKE queries
users = UserInfos.load(UserInfo.username.like(f"%{name}%"))

# Load with joined data
class_entries = ClassEntries.load(Class.show_id == 1)
# class_entries.entries contains joined EntryInfo objects
```

### Create

```python
# Basic create
person = Person.create(
    first="John",
    last="Doe",
    usef_id=1,
    city="New York",
    state="NY",
    country="US"
)

# Create with nested BaseModel (dict accepted for JSON columns)
show = Show.create(
    name="Spring Show",
    start_date=date(2026, 3, 15),
    end_date=date(2026, 3, 17),
    metadata={"ring": "A"}
)
```

Primary key fields are auto-populated by the database.

### Save (Update)

```python
horse = Horse.load(Horse.id == 1)
horse.name = "New Name"
horse.save()

# Updating nested models
user = UserInfo.load(User.id == 1)
user.metadata.first_name = "Jane"
user.metadata.save()
user.save()
```

Only modified fields are sent to the database.

### Delete

```python
entry = Entry.load(Entry.id == 5)
entry.delete()
```

## Term Operators (Query Filters)

Access fields as class attributes to build query terms:

### Comparison
| Operator | Example |
|----------|---------|
| `==` | `Horse.id == 1` |
| `!=` | `Horse.name != "test"` |
| `>` | `Event.start_time > datetime.now()` |
| `>=` | `Class.start_time >= "2026-01-01"` |
| `<` | `Horse.id < 100` |
| `<=` | `Person.modified <= datetime.now()` |

### Logical Combination
| Operator | Example |
|----------|---------|
| `&` (AND) | `Horse.owner_id == 1 & Horse.name == "Spirit"` |
| `\|` (OR) | `Horse.id == 1 \| Horse.id == 2` |
| `^` (XOR) | `Horse.id == 1 ^ Horse.id == 2` |

### Special Methods
| Method | Example |
|--------|---------|
| `.like()` | `Person.first.like("%John%")` |
| `.between(a, b)` | `Event.start_time.between(start, end)` |
| `.asc()` | `MapLocation.name.asc()` |
| `.desc()` | `MapLocation.name.desc()` |
| `.random()` | `Horse.id.random()` |
| `.length()` | `Person.first.length()` |
| `.lcase()` / `.ucase()` | `Person.first.lcase()` |
| `.trim()` | `Person.first.trim()` |

## Overriding Create

Override `create()` classmethod for custom behavior (e.g., password hashing):

```python
class User(DBModel):
    @classmethod
    def create(cls, **kwargs):
        if kwargs.get('password'):
            kwargs.update(
                password=bcrypt.hashpw(
                    bytes(kwargs.get('password'), encoding="utf-8"),
                    bcrypt.gensalt(),
                )
            )
        return super(User, cls).create(**kwargs)
```

## DBQuery (Low-Level Queries)

For raw SQL operations, use `DBQuery` directly:

```python
from src.utils.db_model.db_connection import DBQuery, DirectDBConnection

# Direct connection context manager
with DirectDBConnection() as conn:
    result = conn.execute("SELECT * FROM horse WHERE id = ?", (1,))

# Query builder
query = DBQuery('', 'horse').select("*").where(...)
```

## Migrations (DBUtility)

```python
from src.utils.db_model.utils.utility import DBUtility

# Create table from model
sql = DBUtility.migrate(Horse)

# Drop table
DBUtility.drop(Horse)

# Create with drop
DBUtility.migrate(Horse, drop_table=True)
```

Migrations handle:
- Type mapping (int→INTEGER, str→VARCHAR(255), dict→TEXT, bytes→BLOB, etc.)
- Primary key auto-increment
- NOT NULL constraints
- DEFAULT CURRENT_TIMESTAMP for `created`/`modified` datetime fields
- Unique keys from `metadata_`

## Common Patterns in This Project

1. **Empty schema**: All models use `schema_ = ''` (SQLite doesn't use schemas)
2. **List field naming**: Most list models use `data: list[Model]`, some use plural names (`locations: list[Location]`, `users: list[User]`)
3. **Timestamps**: `created` and `modified` with `Field(default=datetime.now())`
4. **Metadata**: `Optional[dict]` for flexible JSON storage
5. **Composite models**: Inherit from a base model and add join fields (e.g., `EntryInfo(Entry)`, `ClassEntries(Class)`, `UserInfo(User)`)
6. **Optional joins**: Use `Optional[Model]` for single optional joins, no `Optional` needed for list joins

## File Structure

```
server/src/utils/db_model/
  db_model.py         # DBModel class, Field, QueryGraph, metaclass
  db_connection.py    # DBQuery, DirectDBConnection, connection pool
  utils/
    terms.py          # Term class, QueryFilter, operators
    statements.py     # JoinType, SQLFunction, DBDrivers, QueryStatement
    utility.py        # DBUtility (migrations, table_to_model)

server/src/models/
  classes.py          # Person, Horse, Show, Class, Entry, LiveClass
  events.py           # Location, Event, Schedule
  user.py             # User, UserMeta, Role, Device, Access, Favorite
  assets.py           # Image, Asset, CountryMapping
  locations.py        # MapTile, MapLocation
```
