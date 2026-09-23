from fastapi import APIRouter

from app.api import agent_runs, auth, chat, conversations, documents, knowledge, schema, system

api_router = APIRouter(prefix="/api")
for module in (auth, chat, conversations, documents, knowledge, schema, agent_runs, system):
    api_router.include_router(module.router)
