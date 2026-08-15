from fastapi import APIRouter

from app.api.routes.bench import router as bench_router
from app.api.routes.experiments import router as experiments_router
from app.api.routes.experiments_lab import router as experiments_lab_router
from app.api.routes.external_data import router as external_data_router
from app.api.routes.generation import router as generation_router
from app.api.routes.health import router as health_router
from app.api.routes.industrial import router as industrial_router
from app.api.routes.knowledge import router as knowledge_router
from app.api.routes.materials import evidence_router, property_router
from app.api.routes.materials import router as materials_router
from app.api.routes.prediction import router as prediction_router
from app.api.routes.projects import router as projects_router
from app.api.routes.reasoning import router as reasoning_router
from app.api.routes.replacement import router as replacement_router
from app.api.routes.simulation import router as simulation_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(materials_router)
api_router.include_router(property_router)
api_router.include_router(evidence_router)
api_router.include_router(projects_router)

api_router.include_router(knowledge_router)

api_router.include_router(generation_router)

api_router.include_router(prediction_router)

api_router.include_router(experiments_router)

api_router.include_router(simulation_router)

api_router.include_router(industrial_router)

api_router.include_router(reasoning_router)

api_router.include_router(experiments_lab_router)
api_router.include_router(external_data_router)

api_router.include_router(replacement_router)

# Phase 12 — intake bench. Registered last so its routes never shadow a scientific endpoint.
api_router.include_router(bench_router)
