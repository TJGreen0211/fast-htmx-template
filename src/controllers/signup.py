from pydantic import BaseModel, ConfigDict, EmailStr
from pydantic.alias_generators import to_camel
from src.models.user import User, UserInfo


class SignupForm(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
    )
    first_name: str
    last_name: str
    user_email: EmailStr
    user_phone: str
    password: str


class SignupController(object):
    def __init__(self):
        pass

    def create_user(self, data: SignupForm) -> User:
        user = UserInfo.create(**{
            "username": data.user_email,
            "password": data.password,
            "metadata": {
                "first_name": data.first_name,
                "last_name": data.last_name,
                "phone": data.user_phone,
            },
            "notification": {
                "text": True,
                "email": True,
            }

        })
        return user
