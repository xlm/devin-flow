from fastapi import FastAPI

from devin_flow import main


def test_main_exposes_asgi_app() -> None:
    assert isinstance(main.app, FastAPI)
    assert main.app.title == "devin-flow"
