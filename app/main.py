from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from database import get_db, engine, Base
from prometheus_fastapi_instrumentator import Instrumentator
import redis
import os
import logging

# Setup Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Initialize DB Tables
Base.metadata.create_all(bind=engine)

# Initialize FastAPI App
app = FastAPI(title="DevOps Demo API")

# Initialize Redis Client
redis_client = redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379"))

# --- PROMETHEUS METRICS CONFIGURATION ---
# This line registers your app routes and exposes the /metrics endpoint
Instrumentator().instrument(app).expose(app)
# ----------------------------------------

@app.get("/health")
def health_check():
    try:
        redis_client.ping()
        redis_ok = True
    except Exception as e:
        logger.error(f"Redis ping failed: {e}")
        redis_ok = False
    return {"status": "ok", "redis": redis_ok, "db": True}

@app.get("/")
def root():
    logger.info("Root endpoint hit")
    return {"message": "API is running"}