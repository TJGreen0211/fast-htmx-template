# DBModel

Documentation for the DBModel class

## Documentation

Uses pydantic as the base for type hinting and serialization. Further documentation on pydantic can be found [here](https://docs.pydantic.dev/latest/)

## Usage/Examples

### Basic Model Setup

A DBModel class requires a `schema_` and a `table_` for the base model. This is the base table that all queries will be run on. For the fields expected to be returned from the table they can be declared as pydantic fields.

```python
class Location(DBModel):
    schema_ = 'access_control'
    table_ = 'location'

    location_id: int = Field(primary_key=True)
    metadata: LocationMetadata
    created: datetime
    modified: datetime
    account_id: int
    public_id: str
    pulsem_account_id: int
```

In the model you will see in the `metadata` field there is another class called `LocationMetadata`. This class will attempt to load a a dictionary from the database into a pydantic BaseModel. `LocationMetadata` is defined below:

```python
class LocationMetadata(BaseModel):
    name: str
    address: Optional[LocationAddress]
    hs_10dlc: Optional[int] = 0
    description: Optional[str] = None
    twilio_verified: Optional[str] = ""
    marketing_opt_in: Optional[bool] = False
    external_account_id: Optional[str] = ""
```

BaseModels can be chained so `LocationMetadata` has another BaseModel called `LocationAddress`, the data returned will be contained in these classes. This allows essentiall allows json columns to be represented as a class. The entire code for `access_control.location` would then look like:

```python
class LocationAddress(BaseModel):
    city: Optional[str]
    state: Optional[str]
    street: Optional[str]
    country: Optional[str]
    street2: Optional[str]
    zipcode: Optional[str]


class LocationMetadata(BaseModel):
    name: str
    address: Optional[LocationAddress]
    hs_10dlc: Optional[int] = 0
    description: Optional[str] = None
    twilio_verified: Optional[str] = ""
    marketing_opt_in: Optional[bool] = False
    external_account_id: Optional[str] = ""


class Location(DBModel):
    schema_ = 'access_control'
    table_ = 'location'

    location_id: int = Field(primary_key=True)
    metadata: LocationMetadata
    created: datetime
    modified: datetime
    account_id: int
    public_id: str
    pulsem_account_id: int
```

DBModel supports all [Standard Library Types](https://docs.pydantic.dev/latest/api/standard_library_types/)

### Joining Tables

DBModels can be combined to join tables.

To join a table a foreign key needs to be defined. This uses the [Field](https://docs.pydantic.dev/latest/concepts/fields/) function from pydantic. So taking the `Location` example from above we can add a foreign key to the `Account` table on `account_id`.

```python
class Location(DBModel):
    schema_ = 'access_control'
    table_ = 'location'

    location_id: int = Field(primary_key=True)
    metadata: LocationMetadata
    created: datetime
    modified: datetime
    account_id: int = Field(foreign_key=Account.account_id)
    public_id: str
    pulsem_account_id: int

```

Account DBModel is defined as

```python
class Account(DBModel):
    schema_ = 'access_control'
    table_ = 'account'

    account_id: int = Field(primary_key=True)
    financial_id: int
    created: datetime
    modified: datetime
    metadata: AccountMetadata
    public_id: str
```

The class to create the composite query would then look like:

```python
class AccountLocation(Account):
    location: Location
```

As SQL this would look like:

```sql
SELECT
    access_control.account.account_id,
    access_control.account.financial_id,
    access_control.account.created,
    access_control.account.modified,
    access_control.account.metadata,
    access_control.account.public_id,
    access_control.location.location_id,
    access_control.location.metadata,
    access_control.location.created,
    access_control.location.modified,
    access_control.location.account_id,
    access_control.location.public_id,
    access_control.location.pulsem_account_id
FROM
    access_control.account
    LEFT JOIN access_control.location ON access_control.location.account_id = access_control.account.account_id
WHERE
    ...
LIMIT
    ...
```

### Data Functions

#### Loading

Data can be loaded using the standard operators in python. As a basic example taking the `Location` DBModel from above we can load data from the database like so:

```python
location = Location.load(Location.location_id == 1)
```

This will return a pydantic DBModel if the record exists else it will return `None`

To list the data we can define a list DBModel for `Location`:

```python
class Locations(DBModel):
    schema_ = 'access_control'
    table_ = 'location'

    locations: list[Location]
```

This can be loaded the same way as `Location`

```python
locations = Locations.load(Location.location_id == 1)
```

It will return a DBModel with a list of `Location` objects under:

```python
locations.locations
```

Query parameters can also be added for composite queries. Taking the `AccountLocations` DBModel as an example we can apply query filter to location and account tables:

```python
class AccountLocation(Account):
    location: Location

account_location = AccountLocation.load(
  Account.account_id == 1,
  Location.public_id == 'Test' & Location.created > '2024-11-25'
)
```

Full list of operators supported below:

##### *Comparison*

| Term               | Operator | Usage                                      |
| :------------------- | :--------- | :------------------------------------------- |
| Equal              | `==`     | `Location.location_id == 1`          |
| Not Equal          | `<>`     | `Location.public_id <> 'test'`       |
| Greater Than       | `>`      | `Location.modified > datetime.now()` |
| Greater Than Equal | `>=`     | `Location.created >= '2019-09-17'`   |
| Less Than          | `<`      | `Location.modified < '2019-09-17'`   |
| Less Than Equal    | `<=`     | `Location.created <= datetime.now()` |

##### *Bitwise*

| Term | Operator | Usage                                                                          |
| :----- | :--------- | :----------------------------------------------------------------------------- |
| AND  | `&`      | `Location.location_id == 1 & Location.created <= datetime.now()`   |
| OR   | `\|`     | `Location.location_id == 1 \|  Location.public_id == 'not a test'` |
| XOR  | `^`      | `Location.location_id == 1 ^ Location.location_id == 2`            |

##### *Arithmetic*

| Term     | Operator | Usage                             |
| :--------- | :--------- | :---------------------------------- |
| Add      | `+`      | `Location.location_id + 1`  |
| Subtract | `-`      | `Location.location_id - 1`  |
| Multiply | `*`      | `Location.account_id * 10`  |
| Divide   | `/`      | `Location.account_id / 10`  |
| Modulo   | `%`      | `Location.location_id % 10` |

##### *Logical*

| Term    | Operator    | Usage                                                                                |
| :-------- | :------------ | :------------------------------------------------------------------------------------- |
| IS      | `==`        | `Location.public_id == None`                                                   |
| IS NOT  | `!=`        | `Location.public_id == None`                                                   |
| IN      | `==`        | `Location.location_id == [1, 2, 10, 123]`                                      |
| BETWEEN | `between()` | `Location.created.between(datetime.now(), datetime.now() - timedelta(days=1))` |
| LIKE    | `like()`    | `Location.metadata.like('%test%')`                                             |

#### Creating

To create a record use the `create` class method. This will return a DBModel object if the record was successfully created.

Taking the Location object again we can create a location with:

```python
location = Location.create(
    account_id=1,
    public_id='testing',
    pulsem_account_id=2,
    metadata=LocationMetadata(
        name='Some Business Name',
        description='Test Business',
        external_account_id='Testing'
      )
    )
```

**Note:** for BaseModel fields (e.g. `LocationMetadata` from above) dictionary values are also supported:

```python
metadata={
    name: 'Some Business Name',
    description: 'Test Business',
    external_account_id: 'Testing'
}
```

Any Field marked with a `primary_key` will not be populated on creation as the model assumes this is an AutoIncrement field handled by the database.

Defaults are also supported for non-null fields if they are declared in the DBModel:

```python
class FreeTrialMapping(DBModel):
    schema_ = "subscription"
    table_ = "free_trial_mapping"

    id: int = Field(default=None, primary_key=True)
    location_id: int
    expiry_date: date = Field(default=date.today() + timedelta(days=14))
    is_expired: bool = False
    onboarding_complete: bool = False
    pcheck_count: int = 100
```

The create statement for this class would then become:

```python
FreeTrialMapping.create(location_id=1)
```

As all other fields have a default value. More documentation on pydantic default values [here](https://docs.pydantic.dev/latest/concepts/fields/).

#### Saving

Saving objects is supported. Taking the `Location` model we can modify data with:

```python
location = Location.load(Location.location_id == 1)

location.public_id = '12345'

location.save()
```

This can also be done with the BaseModel classes:

```python
location.metadata.name = 'Some Business Name'
location.metadata.address.city = 'London'

location.save()
```

#### Deleting

To delete a record simply call `delete()` on the DBModel object:

```python
locations = Locations.load(Location.location_id == 1)

location.delete()
```

**Note**: Cascade deletes are currently not supported. This was removed over concerns of unintentionally deleting records.

## Todo

- Support for nested `list[]`
- Type hinting to DBModel `field`
- Deprecate `kwargs` in `load` in favor of `field`
