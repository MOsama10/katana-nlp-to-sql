from fastapi import FastAPI
from app.api.query_router import router  # Make sure this path is correct

app = FastAPI()

app.include_router(router)

