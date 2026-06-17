"""Main App."""
# Run using
# source venv/Scripts/activate
# invoke run
# Enable/DisableType Checking
# python.analysis.typeCheckingMode

from typing import List

from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from src.routers import user
from src.routers import dashboard
from src.routers import templates


app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

#: Configure CORS
origins = [
    "http://localhost:5000",
    "http://localhost:8080",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Hx-Push-Url"]
)

app.include_router(user.router)
app.include_router(dashboard.router)


#: Describe all Pydantic Response classes
class ResponseBase(BaseModel):
    status: str
    code: int
    messages: List[str] = []


class PongResponse(ResponseBase):
    data: str = "Pong!"


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@app.get("/ping", response_model=PongResponse)
def return_pong():
    return {"status": "ok", "code": 200}


#: Start application
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
