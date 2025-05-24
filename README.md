# FastAPI HTMX Template

## Development
Running:

```sh
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

python -m uvicorn src.app:app --reload --host localhost --port 5000

#### Invoke tasks

```
invoke -l
Available tasks:

  run-black             Run Black formatter.
  run-flake8            Run flake8.
  run-lint-format       Run chained import reorder, black and flake8.
  run-reorder-imports   Run imports reordering.
  run                   Start Uvicorn server with hot reloading on port 8000.
  update-deps           Pin all dependencies and upgrade environment.
```

## Production

```sh
todo
```
