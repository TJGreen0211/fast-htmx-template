import sys
from invoke.tasks import task


@task
def update_deps(c):
    """Pin all dependencies and upgrade environment."""
    c.run("pip-compile --upgrade")
    c.run(
        "pip-compile --upgrade --output-file dev-requirements.txt dev-requirements.in"
    )
    c.run("pip install --upgrade -r requirements.txt -r dev-requirements.txt")


@task(optional=['port'])
def run(c, port: int=5000):
    """Start Uvicorn server with hot reloading on port 5000."""
    venv_python = "venv\\Scripts\\python.exe" if sys.platform == "win32" else "venv/bin/python"
    cmd = f"{venv_python} -m uvicorn src.app:app --reload --host localhost --port {port}"
    c.run(cmd)


@task(optional=['refresh'])
def migrate(c, refresh=False):
    """Migrate database tables"""
    cmd = f"python -m src.migrate {'--refresh' if refresh else ''}"
    c.run(cmd)


@task
def run_reorder_imports(c):
    """Run imports reordering."""
    c.run("reorder-python-imports --application-directories=.:src:tests")


@task
def run_black(c):
    """Run Black formatter."""
    c.run("black src/")
    c.run("black tests/")


@task
def run_flake8(c):
    """Run flake8."""
    c.run("flake8")


@task(run_reorder_imports, run_black, run_flake8)
def run_lint_format(c):
    """Run chained import reorder, black and flake8."""
    print("Done")


@task
def certbot(c):
    c.run("sudo certbot renew")
