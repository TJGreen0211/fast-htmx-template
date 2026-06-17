"""Login routes."""
from datetime import timedelta
from typing import Annotated, Union

from fastapi import Header, Depends, HTTPException, status, Request
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from fastapi.responses import HTMLResponse
from fastapi.security import OAuth2PasswordRequestForm

from src.utils import config
from src.controllers.login import validate_user
from src.auth.jwt_handler import (
    LoginUser,
    create_access_token,
    get_current_user,
    get_optional_current_user,
    ACCESS_TOKEN_EXPIRE_MINUTES,
)
from src.controllers.signup import SignupForm, SignupController
from . import router, templates


PROTECTED = [Depends(get_current_user)]


@router.get("/user/navbar")
async def navbar(request: Request, current_user: Union[LoginUser, None] = Depends(get_optional_current_user)):
    return templates.TemplateResponse(
        name="user/navbar.html",
        request=request,
        context={"logged_in": current_user is not None, "user": current_user}
    )


@router.get("/login-page", response_class=HTMLResponse)
async def login_page(request: Request, hx_request: Annotated[Union[str, None], Header()] = None):
    if hx_request:
        return templates.TemplateResponse(
            request=request,
            name="user/user_login.html",
            context={}
        )

    return templates.TemplateResponse(
        name="wrapper.html",
        request=request,
        context={"fragment_template": "user/user_login.html"}
    )


@router.get("/signup-page", response_class=HTMLResponse)
async def signup_page(request: Request, hx_request: Annotated[Union[str, None], Header()] = None):
    if hx_request:
        return templates.TemplateResponse(
            request=request,
            name="user/user_signup.html",
            context={}
        )

    return templates.TemplateResponse(
        name="wrapper.html",
        request=request,
        context={"fragment_template": "user/user_signup.html"}
    )


@router.post('/user/login')
async def login(
    request: Request,
    user: OAuth2PasswordRequestForm = Depends(),
    hx_request: Annotated[Union[str, None], Header()] = None
):
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

    if hx_request:
        response = templates.TemplateResponse(
            name="main.html",
            request=request,
            context={"user": user.username},
            headers={'HX-Trigger': 'refreshNavbar'}
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

    response = JSONResponse({"user": user.username, "token": token})
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
async def logout(request: Request, hx_request: Annotated[Union[str, None], Header()] = None):
    if hx_request:
        response = templates.TemplateResponse(
            name="user/user_login.html",
            request=request,
            context={},
            headers={'HX-Trigger': 'refreshNavbar'}
        )
        response.delete_cookie(
            "Authorization",
            httponly=True,
            samesite=config.cookie_options_samesite,
            secure=config.cookie_options_secure,
        )
        return response

    response = JSONResponse({"message": "Logged out successfully"})
    response.delete_cookie(
        "Authorization",
        httponly=True,
        samesite=config.cookie_options_samesite,
        secure=config.cookie_options_secure,
    )
    return response


@router.get("/user/whoami", response_model=LoginUser, dependencies=[Depends(get_current_user)])
async def read_users_me(
    request: Request,
    current_user: LoginUser = Depends(get_current_user),
    hx_request: Annotated[Union[str, None], Header()] = None
):
    if current_user and hx_request:
        return templates.TemplateResponse(
            name="main.html",
            request=request,
            context={"user": current_user.username}
        )
    elif hx_request:
        return templates.TemplateResponse(
            name="user/user_login.html",
            request=request,
            context={}
        )

    if current_user:
        return templates.TemplateResponse(
            name="wrapper.html",
            request=request,
            context={"fragment_template": "main.html", "user": current_user.username}
        )
    return templates.TemplateResponse(
        name="wrapper.html",
        request=request,
        context={"fragment_template": "user/user_login.html"}
    )


@router.post("/user/signup", response_class=HTMLResponse)
async def signup(
    request: Request,
    hx_request: Annotated[Union[str, None], Header()] = None,
):
    data = await request.form()
    signup_form = SignupForm(**dict((x, y) for x, y in list(data.items())))

    user = SignupController().create_user(signup_form)

    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    token = jsonable_encoder(access_token)

    if hx_request:
        response = templates.TemplateResponse(
            name="main.html",
            request=request,
            context={"user": user.username},
            headers={'HX-Trigger': 'refreshNavbar'}
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

    response = JSONResponse({"user": user.username, "token": token})
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
