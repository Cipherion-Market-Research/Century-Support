from fastapi import FastAPI, APIRouter

app = FastAPI()
router = APIRouter()


@app.get("/health")
def health():
    return {"ok": True}


@router.get("/v0/latest")
def latest():
    return {"price": 0}


@router.post("/v0/predict")
def predict():
    return {"ok": True}
