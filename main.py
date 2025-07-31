
from fastapi import FastAPI, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import vertexai
from vertexai.preview.generative_models import GenerativeModel, Part

from google.oauth2 import service_account
from bs4 import BeautifulSoup
import requests
from PIL import Image
import os
from PIL import ImageDraw
import io
import re
import json

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from base64 import b64encode
import tempfile

# Konfiguration
PROJECT_ID = "innovationsproject"
REGION = "us-central1"
CREDENTIALS_FILE = "innovationsproject-9c904d36deb8.json"

# GCP Auth
credentials = service_account.Credentials.from_service_account_file(CREDENTIALS_FILE)
vertexai.init(project=PROJECT_ID, location=REGION, credentials=credentials)

# Modell initialisieren
# model = GenerativeModel("gemini-2.0-flash-001")
model = GenerativeModel("gemini-2.5-pro")

# FastAPI einrichten
app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")
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
            driver = webdriver.Chrome(options=options)
            driver.get(url)
            driver.implicitly_wait(10) 
            total_height = driver.execute_script("return document.body.scrollHeight")
            driver.set_window_size(1920, total_height)
            screenshot = driver.get_screenshot_as_png()
            driver.quit()
            return screenshot
    except Exception as e:
        print("Screenshot-Fehler:", e)
        return None
    
def mark_problems_on_image(image_data, problems):
    img = Image.open(io.BytesIO(image_data)).convert("RGBA")
    draw = ImageDraw.Draw(img)

    for problem in problems:
        bbox = problem.get("bounding_box")
        if bbox and len(bbox) == 4:
            x1, y1, x2, y2 = bbox
            draw.rectangle([x1, y1, x2, y2], outline="red", width=4)

    output = io.BytesIO()
    img.save(output, format="PNG")
    return output.getvalue()

def generate_text_output(response_json):
    text_output = f"Allgemeines Feedback:{response_json.get('general_feedback', '')}"

    problems = response_json.get("problems", [])
    if problems:
        text_output += "\n\nGefundene Farbkontrast-Probleme:"
        for problem in problems:
            text_output += "\n\n"
            text_output += f"{problem.get('title', 'Problem')}:\n"
            text_output += f"Folgendes Problem liegt vor: {problem.get('description', '')}\n"
            text_output += f"Hier liegt das Problem: {problem.get('location', '')}\n"
            text_output += f"Aktueller Farbwert: {problem.get('current_color', '')}, Verbesserung: {problem.get('suggested_color', '')}"
    else:
        text_output += "\n\nKeine konkreten Farbprobleme gefunden."

    return text_output


@app.get("/", response_class=HTMLResponse)
def form_get(request: Request):
    return templates.TemplateResponse("form.html", {"request": request, "response": None})

@app.post("/", response_class=HTMLResponse)
async def form_post(request: Request, url: str = Form(None), file: UploadFile = File(None)):
    contents = []
    image_data = None

    try:
        if url:
            screenshot = take_screenshot(url)
            if screenshot:
                img = Image.open(io.BytesIO(screenshot))
                width, height = img.size
                prompt = f"""
                        Analysiere das Farbkonzept der Webseite gemäß WCAG 2.2 AA und gib das Ergebnis ausschließlich im folgenden JSON-Format zurück. Keine weiteren Erklärungen oder Texte. Schreibe deine Antwort auf Deutsch.

                        Das Bild hat eine Auflösung von {width} Pixel in der Breite und {height} Pixel in der Höhe.

                        {{
                        "general_feedback": "Maximal 3 kurze Sätze allgemeines Feedback zum Farbkonzept.",
                        "problems": [
                            {{
                            "title": "Problem X",
                            "description": "Was ist das Problem?",
                            "location": "Wo auf der Webseite tritt das Problem auf?",
                            "current_color": "z.B. #FFFFFF",
                            "suggested_color": "z.B. #000000",
                            "bounding_box": [x1, y1, x2, y2]
                            }}
                        ]
                        }}

                        Wichtig: Die bounding_box muss die exakten Pixelkoordinaten [x1, y1, x2, y2] angeben, bezogen auf das gesamte Bild. 
                        - Der Ursprung (0,0) ist die obere linke Ecke des Bildes.
                        - (x1, y1) ist die obere linke Ecke der Box.
                        - (x2, y2) ist die untere rechte Ecke der Box.
                        - Gib die Box so eng wie möglich um das betroffene Element an (z. B. nur um den Text, nicht den ganzen Button oder Bereich).

                        Wenn keine Lokalisierung möglich ist, setze bounding_box auf null.
                        Fülle das X bei title mit der Problem-Nummerierung aus der Liste der Probleme.

                        Wenn keine Probleme existieren, gib eine leere Liste bei "problems" zurück.
                        """
                contents.append(Part.from_text(prompt))
                resp = requests.get(url)
                soup = BeautifulSoup(resp.text, "html.parser")
                css_code = extract_css_content(soup, url)
                if css_code:
                    contents.append(Part.from_text(f"CSS-Code der Seite:\n{css_code}"))
            
                contents.append(Part.from_data(data=screenshot, mime_type="image/png"))
                image_data = screenshot

            else:
                prompt = """
                        Analysiere das Farbkonzept der Webseite gemäß WCAG 2.2 AA und gib das Ergebnis ausschließlich im folgenden JSON-Format zurück. Keine weiteren Erklärungen oder Texte. Schreibe deine Antwort auf Deutsch.

                        {
                        "general_feedback": "Maximal 3 kurze Sätze allgemeines Feedback zum Farbkonzept.",
                        "problems": [
                            {
                            "title": "Problem X",
                            "description": "Was ist das Problem?",
                            "location": "Wo auf der Webseite tritt das Problem auf?",
                            "current_color": "z.B. #FFFFFF",
                            "suggested_color": "z.B. #000000",
                            "bounding_box": [x1, y1, x2, y2]
                            }
                        ]
                        }

                        Wichtig: Die bounding_box muss die exakten Pixelkoordinaten [x1, y1, x2, y2] angeben, bezogen auf das gesamte Bild. 
                        - Der Ursprung (0,0) ist die obere linke Ecke des Bildes.
                        - (x1, y1) ist die obere linke Ecke der Box.
                        - (x2, y2) ist die untere rechte Ecke der Box.
                        - Gib die Box so eng wie möglich um das betroffene Element an (z. B. nur um den Text, nicht den ganzen Button oder Bereich).

                        Wenn keine Lokalisierung möglich ist, setze bounding_box auf null.
                        Fülle das X bei title mit der Problem-Nummerierung aus der Liste der Probleme.

                        Wenn keine Probleme existieren, gib eine leere Liste bei "problems" zurück.
                        """
                contents.append(Part.from_text(prompt))
                resp = requests.get(url)
                soup = BeautifulSoup(resp.text, "html.parser")
                css_code = extract_css_content(soup, url)
                if css_code:
                    contents.append(Part.from_text(f"CSS-Code der Seite:\n{css_code}"))


        elif file:
            image_data = await file.read()
            img = Image.open(io.BytesIO(image_data))
            width, height = img.size

            prompt = f"""
                    Analysiere das Farbkonzept des Bildes gemäß WCAG 2.2 AA und gib das Ergebnis ausschließlich im folgenden JSON-Format zurück. Keine weiteren Erklärungen oder Texte. Schreibe deine Antwort auf Deutsch.

                    Das Bild hat eine Auflösung von {width} Pixel in der Breite und {height} Pixel in der Höhe.

                    {{
                    "general_feedback": "Maximal 3 kurze Sätze allgemeines Feedback zum Farbkonzept.",
                    "problems": [
                        {{
                        "title": "Problem X",
                        "description": "Was ist das Problem?",
                        "location": "Wo auf dem Bild tritt das Problem auf?",
                        "current_color": "z.B. #FFFFFF",
                        "suggested_color": "z.B. #000000",
                        "bounding_box": [x1, y1, x2, y2]
                        }}
                    ]
                    }}

                    Wichtig: Die bounding_box muss die exakten Pixelkoordinaten [x1, y1, x2, y2] angeben, bezogen auf das gesamte Bild. 
                    - Der Ursprung (0,0) ist die obere linke Ecke des Bildes.
                    - (x1, y1) ist die obere linke Ecke der Box.
                    - (x2, y2) ist die untere rechte Ecke der Box.
                    - Gib die Box so eng wie möglich um das betroffene Element an (z. B. nur um den Text, nicht den ganzen Button oder Bereich).

                    Wenn keine Lokalisierung möglich ist, setze bounding_box auf null.
                    Fülle das X bei title mit der Problem-Nummerierung aus der Liste der Probleme.

                    Wenn keine Probleme existieren, gib eine leere Liste bei "problems" zurück.
                    """
            contents.append(Part.from_text(prompt))
            image_part = Part.from_data(data=image_data, mime_type=file.content_type)
            contents.append(image_part)

        response = model.generate_content(contents, generation_config={"temperature": 0.2})
        
        # print for usertests
        print("RESPONSE:", response.text)

        json_string = response.text.strip() # Remove leading/trailing whitespace

        match = re.search(r"\{.*\}", json_string, re.DOTALL)
        if match:
            json_string = match.group(0)
        else:
            # If no JSON object is found, handle the error or raise an exception
            print("Error: No JSON object found in response text.")
            raise ValueError("Model response did not contain a valid JSON object.")

        response_json = json.loads(json_string)

        text_output = generate_text_output(response_json)

        marked_image = mark_problems_on_image(image_data, response_json.get("problems", [])) if image_data else None
        image_base64 = b64encode(marked_image).decode("utf-8") if marked_image else None

        return templates.TemplateResponse("form.html", {
            "request": request,
            "response": text_output,
            "image_data": image_base64
        })

    except Exception as e:
        return templates.TemplateResponse("form.html", {"request": request, "response": f"Fehler bei der Verarbeitung: {str(e)}"})
