"""Dashboard routes."""
from typing import Annotated, Union

from fastapi import APIRouter, Header, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from src.models.user import UserInfos, UserInfo, User
from src.auth.jwt_handler import get_current_user


router = APIRouter()
templates = Jinja2Templates(directory="templates")
PROTECTED = [Depends(get_current_user)]


@router.get("/dashboard/users", dependencies=[Depends(get_current_user)])
async def get_users(request: Request, hx_request: Annotated[Union[str, None], Header()] = None,):
    users = UserInfos.load().users
    user_data = [{
        "username": u.username,
        "registered": True,
        "first_name": u.metadata.first_name if u.metadata else "First",
        "last_name": u.metadata.last_name if u.metadata else "Last",
        "id": u.id,
    } for u in users]

    if hx_request:
        return templates.TemplateResponse(
            name="dashboard/users/index.html",
            request=request,
            context={"users": user_data}
        )

    return templates.TemplateResponse(
        name="wrapper.html",
        request=request,
        context={"fragment_template": "dashboard/users/index.html", "users": user_data}
    )


@router.get("/dashboard/users/list", dependencies=[Depends(get_current_user)])
async def get_user_list(request: Request, hx_request: Annotated[Union[str, None], Header()] = None,):
    users = UserInfos.load().users
    user_data = [{
        "username": u.username,
        "registered": True,
        "first_name": u.metadata.first_name if u.metadata else "First",
        "last_name": u.metadata.last_name if u.metadata else "Last",
        "id": u.id,
    } for u in users]

    if hx_request:
        return templates.TemplateResponse(
            name="dashboard/users/user_list.html",
            request=request,
            context={"users": user_data}
        )

    return RedirectResponse(url="/dashboard/users", status_code=302)


@router.post("/add-user", response_class=HTMLResponse, dependencies=[Depends(get_current_user)])
async def add_user(request: Request):
    data = await request.form()
    username = data.get("username")
    first_name = data.get("first_name", "")
    last_name = data.get("last_name", "")
    password = data.get("password", "")

    if not username or not password:
        raise HTTPException(status_code=400, detail="Email and password are required")

    UserInfo.create(**{
        "username": username,
        "password": password,
        "metadata": {
            "first_name": first_name,
            "last_name": last_name,
            "phone": "",
        },
        "notification": {
            "text": True,
            "email": True,
        }
    })

    return templates.TemplateResponse(
        name="dashboard/users/add_user_success.html",
        request=request,
        context={"username": username},
        headers={"HX-Trigger": "reloadUserList"}
    )


@router.delete("/user/{user_id}", dependencies=[Depends(get_current_user)])
async def remove_user(user_id: int, request: Request, hx_request: Annotated[Union[str, None], Header()] = None):
    user = User.load(User.id == user_id, limit=1)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.delete(cascade=True)

    if hx_request:
        return templates.TemplateResponse(
            name="dashboard/users/user_removed.html",
            request=request,
            context={"username": user.username},
            headers={"HX-Trigger": "reloadUserList"}
        )

    return JSONResponse({"status": True})
