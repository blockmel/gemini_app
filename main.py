
from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import vertexai
from vertexai.preview.generative_models import GenerativeModel, Part

from google.oauth2 import service_account
from bs4 import BeautifulSoup
import requests
from PIL import Image
from io import BytesIO

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
import base64
import tempfile

# Konfiguration
PROJECT_ID = "innovationsproject"
REGION = "us-central1"
CREDENTIALS_FILE = "innovationsproject-9c904d36deb8.json"

# GCP Auth
credentials = service_account.Credentials.from_service_account_file(CREDENTIALS_FILE)
vertexai.init(project=PROJECT_ID, location=REGION, credentials=credentials)

# Modell initialisieren
model = GenerativeModel("gemini-2.0-flash-001")

# FastAPI einrichten
app = FastAPI()
templates = Jinja2Templates(directory="templates")

def extract_css_content(soup, base_url):
    css_code = ""
    # Inline-Styles
    for style in soup.find_all("style"):
        css_code += style.get_text() + "\n"
    # Verlinkte CSS-Dateien
    for link in soup.find_all("link", rel="stylesheet"):
        href = link.get("href")
        if href:
            if href.startswith("//"):
                href = "https:" + href
            elif href.startswith("/"):
                href = base_url + href
            try:
                css_resp = requests.get(href)
                if css_resp.status_code == 200:
                    css_code += css_resp.text + "\n"
            except:
                continue
    return css_code.strip()

def take_screenshot(url):
    try:
        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")

        with tempfile.TemporaryDirectory() as tmpdirname:
            driver_path = os.path.join(tmpdirname, "chromedriver.exe")  # Optional, falls nötig
            driver = webdriver.Chrome(options=options)
            driver.set_window_size(1200, 800)
            driver.get(url)
            screenshot = driver.get_screenshot_as_png()
            driver.quit()
            return screenshot
    except Exception as e:
        print("Screenshot-Fehler:", e)
        return None

@app.get("/", response_class=HTMLResponse)
def form_get(request: Request):
    return templates.TemplateResponse("form.html", {"request": request, "response": None})

@app.post("/", response_class=HTMLResponse)
async def form_post(request: Request, url: str = Form(None), file: UploadFile = File(None)):
    contents = []

    # if prompt:
    #     contents.append(Part.from_text(prompt))

    try:
        if url:
            contents.append(Part.from_text("Bewerte das Farbkonzept bezüglich WCAG 2.0 und gebe wenn nötig konkrete Farbverbesserungsvorschläge mit Farbwerten. Gebe deine Antwort in folgendem Format: Allgemeines Feedback zur Webseite: Gebe hier in maximal 3 kurzen Sätzen ein allgemeines Feedback zum Farbkonzept.; Konkrete Probleme: Gebe hier alle konkreten Probleme im folgendem Format an. Gib jedem Problem die Überschrift Problem “X”. Setze für X die Problem-Nummer ein: Folgendes Problem liegt vor: Benenne hier das Problem.; Hier liegt das Problem: Gebe hier konkret an, wo das Problem vorliegt; Mit folgendem Farbwert kann es verbessert werden: Gebe hier sowohl den aktuellen Farbwert an als auch den Farbwert zur Verbesserung. Gebe dabei nicht mehr als einen Verbesserungsvorschlag an."))
            resp = requests.get(url)
            soup = BeautifulSoup(resp.text, "html.parser")
            css_code = extract_css_content(soup, url)
            if css_code:
                contents.append(Part.from_text(f"CSS-Code der Seite:\n{css_code}"))
            screenshot = take_screenshot(url)
            if screenshot:
                contents.append(Part.from_image(screenshot))

        elif file:
            contents.append(Part.from_text("Analysiere das Bild und bewerte das Farbkonzept bezüglich WCAG 2.0 und gebe wenn nötig konkrete Farbverbesserungsvorschläge mit Farbwerten. Gebe deine Antwort in folgendem Format: Allgemeines Feedback zum Bild: Gebe hier in maximal 3 kurzen Sätzen ein allgemeines Feedback zum Farbkonzept.; Konkrete Probleme: Gebe hier alle konkreten Probleme im folgendem Format an. Gib jedem Problem die Überschrift Problem “X”. Setze für X die Problem-Nummer ein: Folgendes Problem liegt vor: Benenne hier das Problem.; Hier liegt das Problem: Gebe hier konkret an, wo das Problem vorliegt; Mit folgendem Farbwert kann es verbessert werden: Gebe hier sowohl den aktuellen Farbwert an als auch den Farbwert zur Verbesserung. Gebe dabei nicht mehr als einen Verbesserungsvorschlag an."))
            image_data = await file.read()
            image_part = Part.from_data(data=image_data, mime_type=file.content_type)
            contents.append(image_part)

        response = model.generate_content(contents)
        return templates.TemplateResponse("form.html", {"request": request, "response": response.text})

    except Exception as e:
        return templates.TemplateResponse("form.html", {"request": request, "response": f"Fehler bei der Verarbeitung: {str(e)}"})
