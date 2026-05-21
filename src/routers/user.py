"""Login routes."""
from datetime import timedelta
from typing import Annotated, Union

from fastapi import APIRouter, Header, Depends, HTTPException, status, Request
from fastapi.responses import RedirectResponse
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from src.models.user import UserInfos
from src.utils import config
from src.controllers.login import validate_user
from src.auth.jwt_handler import LoginUser, create_access_token, get_current_user, ACCESS_TOKEN_EXPIRE_MINUTES
from src.controllers.signup import SignupForm, SignupController

router = APIRouter()
templates = Jinja2Templates(directory="templates")
PROTECTED = [Depends(get_current_user)]


class UserForm(BaseModel):
    name: str
    email: str
    phone: str
    eventType: str
    message: str


@router.get("/login-page", response_class=HTMLResponse)
async def login_page(request: Request, hx_request: Annotated[Union[str, None], Header()] = None):

    # if hx_request:
    return templates.TemplateResponse(
        headers={'HX-Trigger': 'loadFolderContents'},
        request=request,
        name="user/user_login.html",
        context={}
    )


@router.get("/signup-page", response_class=HTMLResponse)
async def signup_page(request: Request, hx_request: Annotated[Union[str, None], Header()] = None):

    # if hx_request:
    return templates.TemplateResponse(
        headers={'HX-Trigger': 'loadFolderContents'},
        request=request,
        name="user/user_signup.html",
        context={}
    )


@router.post('/user/login')
async def login(request: Request, user: OAuth2PasswordRequestForm = Depends()):
    user = await validate_user(user)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    token = jsonable_encoder(access_token)

    response = templates.TemplateResponse(
        name="main.html",
        request=request,
        context={"user": user.username}
    )
    response.set_cookie(
        "Authorization",
        value=f"Bearer {token}",
        httponly=True,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES,
        expires=ACCESS_TOKEN_EXPIRE_MINUTES,
        samesite=config.cookie_options_samesite,
        secure=config.cookie_options_secure,
    )

    return response


@router.post('/user/logout', dependencies=[Depends(get_current_user)])
async def logout(request: Request, current_user: LoginUser = Depends(get_current_user)):
    response = RedirectResponse(url="/login-page", status_code=302)

    response.delete_cookie(
        "Authorization",
        httponly=True,
        samesite=config.cookie_options_samesite,
        secure=config.cookie_options_secure,
    )

    return response


@router.get("/user/whoami", response_model=LoginUser, dependencies=[Depends(get_current_user)])
async def read_users_me(request: Request, current_user: LoginUser = Depends(get_current_user)):
    if current_user:
        return templates.TemplateResponse(
            name="main.html",
            request=request,
            context={"user": current_user.username}
        )

    return templates.TemplateResponse(
        name="user/user_login.html",
        request=request,
        context={}
    )


@router.post("/user/signup", response_class=HTMLResponse)
async def signup(
    request: Request,
    # data: Annotated[AccessPassForm, Form()],
    hx_request: Annotated[Union[str, None], Header()] = None,
    # username: str = Form(),
    # password: str = Form(),
):
    data = await request.form()
    signup_form = SignupForm(**dict((x, y) for x, y in list(data.items())))

    user = SignupController().create_user(signup_form)

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    token = jsonable_encoder(access_token)

    response = templates.TemplateResponse(
        name="main.html",
        request=request,
        context={"user": user.username}
    )
    response.set_cookie(
        "Authorization",
        value=f"Bearer {token}",
        httponly=True,
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES,
        expires=ACCESS_TOKEN_EXPIRE_MINUTES,
        samesite=config.cookie_options_samesite,
        secure=config.cookie_options_secure,
    )

    return response


@router.get("/user/list", dependencies=[Depends(get_current_user)])
async def get_user_list(request: Request, hx_request: Annotated[Union[str, None], Header()] = None,):
    if hx_request:
        users = UserInfos.load().users
        return templates.TemplateResponse(
            name="user/user_list.html",
            request=request,
            context={"users": [{
                "username": u.username,
                "registered": True,
                "first_name": u.metadata.first_name,
                "last_name": u.metadata.last_name,
                "id": u.id,
            } for u in users]}
        )

    return users
