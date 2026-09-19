from fastapi import FastAPI


def test_main_exposes_asgi_app() -> None:
    from devin_flow import main

    assert isinstance(main.app, FastAPI)
    assert main.app.title == "devin-flow"
