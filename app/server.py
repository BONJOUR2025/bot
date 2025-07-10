from fastapi import FastAPI
from .api import create_app

app: FastAPI = create_app()
