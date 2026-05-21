from typing import Optional, Self
from pydantic import Field
from datetime import datetime
from passlib.context import CryptContext

from src.utils.db_model.db_model import DBModel


class Role(DBModel):
    schema_ = ''
    table_ = 'role'

    id: int = Field(primary_key=True)
    name: str
    created: datetime = Field(default=datetime.now())
    modified: datetime = Field(default=datetime.now())


class Roles(DBModel):
    schema_ = Role.schema_
    table_ = Role.table_

    roles: list[Role]


class Registration(DBModel):
    schema_ = ''
    table_ = 'registration'

    id: int = Field(primary_key=True)
    username: str
    password: str
    role_id: Optional[int]
    last_login: Optional[datetime]
    created: Optional[datetime]
    modified: Optional[datetime]


class User(DBModel):
    schema_ = ''
    table_ = 'user'

    id: int = Field(primary_key=True)
    username: str
    password: str
    role_id: Optional[int]
    last_login: Optional[datetime]
    created: Optional[datetime]
    modified: Optional[datetime]

    @classmethod
    def create(cls, **kwargs: Self):
        kwargs.update(
            password=CryptContext(schemes=["bcrypt"], deprecated="auto").hash(kwargs.get('password'))
        )
        return super(User, cls).create(**kwargs)


class UserMeta(DBModel):
    schema_ = ''
    table_ = 'user_meta'

    id: int = Field(primary_key=True)
    user_id: int = Field(foreign_key=User.id)
    first_name: str
    last_name: str
    phone: str
    created: Optional[datetime]
    modified: Optional[datetime]


class Users(DBModel):
    schema_ = User.schema_
    table_ = User.table_

    users: list[User]


class UserInfo(User):
    metadata: Optional[UserMeta]


class UserInfos(DBModel):
    schema_ = User.schema_
    table_ = User.table_

    users: list[UserInfo]
