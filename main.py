
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import vertexai
from vertexai.preview.generative_models import GenerativeModel

import os
from google.oauth2 import service_account

# Konfiguration
PROJECT_ID = "innovationsproject"
REGION = "us-central1"

# GCP Auth
credentials = service_account.Credentials.from_service_account_file(
    "innovationsproject-9c904d36deb8.json"
)

vertexai.init(project=PROJECT_ID, location=REGION, credentials=credentials)

# Modell initialisieren
model = GenerativeModel("gemini-2.0-flash-001")

# FastAPI einrichten
app = FastAPI()
templates = Jinja2Templates(directory="templates")

@app.get("/", response_class=HTMLResponse)
def form_get(request: Request):
    return templates.TemplateResponse("form.html", {"request": request, "response": None})

@app.post("/", response_class=HTMLResponse)
def form_post(request: Request, prompt: str = Form(...)):
    response = model.generate_content(prompt)
    return templates.TemplateResponse("form.html", {"request": request, "response": response.text})
