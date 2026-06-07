"""Login routes."""
from typing import Annotated, Union

from fastapi import APIRouter, Header, Depends, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from src.models.user import UserInfos
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
