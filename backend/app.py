from flask import Flask, request, jsonify
from flask_cors import CORS
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import threading
import sqlite3
from groq import Groq 

app = Flask(__name__)
CORS(app)

client = Groq(api_key="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")

def init_db():
    conn = sqlite3.connect('farmacia.db')
    cursor = conn.cursor()
    cursor.execute('CREATE TABLE IF NOT EXISTS farmacias (id INTEGER PRIMARY KEY, nombre TEXT UNIQUE, color TEXT)')
    cursor.execute('CREATE TABLE IF NOT EXISTS medicamentos (id INTEGER PRIMARY KEY, nombre_buscado TEXT UNIQUE)')
    cursor.execute('''CREATE TABLE IF NOT EXISTS historial 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, farmacia_id INTEGER, medicamento_id INTEGER, 
                       nombre_producto TEXT, precio INTEGER, fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP, link TEXT,
                       FOREIGN KEY(farmacia_id) REFERENCES farmacias(id),
                       FOREIGN KEY(medicamento_id) REFERENCES medicamentos(id))''')
    farmacias_data = [(1, 'Ahumada', '#003399'), (2, 'Dr. Simi', '#ce000c'), (3, 'Salcobrand', '#ffd400')]
    cursor.executemany("INSERT OR IGNORE INTO farmacias VALUES (?,?,?)", farmacias_data)
    conn.commit()
    conn.close()

init_db()

def get_driver():
    opts = Options()
    opts.add_argument("--headless")
    opts.add_argument("--blink-settings=imagesEnabled=false")
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)

def scrape_task(func, remedio, res_list):
    driver = get_driver()
    try: func(remedio, driver, res_list)
    except: pass
    finally: driver.quit()

def logic_ahumada(remedio, driver, res):
    driver.get(f"https://www.farmaciasahumada.cl/search?q={remedio}&srule=price-low-to-high&sz=1")
    WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.CLASS_NAME, "price")))
    nom = driver.find_element(By.CLASS_NAME, "pdp-link").text.strip()
    pre = driver.find_element(By.CLASS_NAME, "price").get_attribute("innerText").split('\n')[0]
    lnk = driver.find_element(By.CLASS_NAME, "pdp-link").find_element(By.TAG_NAME, "a").get_attribute("href")
    res.append({"farmacia": "Ahumada", "nombre": nom, "precio": pre, "link": lnk, "color": "#003399"})

def logic_drsimi(remedio, driver, res):
    driver.get(f"https://www.drsimi.cl/{remedio}?_q={remedio}&map=ft&order=OrderByPriceASC")
    WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, "[class*='currencyContainer']")))
    nom = driver.find_element(By.CSS_SELECTOR, "[class*='brandName']").text.strip()
    pre = driver.find_element(By.CSS_SELECTOR, "[class*='currencyContainer']").get_attribute("innerText")
    lnk = driver.find_element(By.CSS_SELECTOR, "a[class*='clearLink']").get_attribute("href")
    res.append({"farmacia": "Dr. Simi", "nombre": nom, "precio": pre, "link": lnk, "color": "#ce000c"})

def logic_salcobrand(remedio, driver, res):
    driver.get(f"https://salcobrand.cl/search_result?query={remedio}&sort=price_asc")
    WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, ".product-info")))
    d = driver.execute_script("let p=document.querySelector('.product-info'); let c=p.closest('.product'); return {n:p.innerText.split('\\n')[0], pr:c.querySelector('.price').innerText, l:c.querySelector('a').href};")
    if d: res.append({"farmacia": "Salcobrand", "nombre": d['n'], "precio": d['pr'], "link": d['l'], "color": "#ffd400"})

@app.route('/scraping_manual', methods=['POST'])
def scraping_manual():
    remedio = request.json.get('remedio', '')
    res = []
    threads = [threading.Thread(target=scrape_task, args=(f, remedio, res)) for f in [logic_ahumada, logic_drsimi, logic_salcobrand]]
    for t in threads: t.start()
    for t in threads: t.join()
    return jsonify({"precios": res})

@app.route('/consultar_asistente', methods=['POST'])
def consultar_asistente():
    data = request.json
    pregunta = data.get('pregunta')
    contexto = data.get('contexto_precios')
    reglas = ("Eres Mathew, asistente de FarmaConnect. Solo respondes sobre salud y medicamentos. "
              "No mediques dosis, sugiere ver a un profesional. Si preguntan otros temas, declina amablemente.")
    try:
        completion = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "system", "content": reglas}, {"role": "user", "content": f"Contexto: {contexto}. Pregunta: {pregunta}"}]
        )
        return jsonify({"respuesta": completion.choices[0].message.content})
    except: return jsonify({"respuesta": "Error de comunicación."}), 500

@app.route('/obtener_historial')
def obtener_historial():
    conn = sqlite3.connect('farmacia.db')
    c = conn.cursor()
    c.execute('''SELECT m.nombre_buscado, f.nombre, h.nombre_producto, h.precio, h.fecha 
                 FROM historial h JOIN farmacias f ON h.farmacia_id = f.id 
                 JOIN medicamentos m ON h.medicamento_id = m.id ORDER BY h.fecha DESC LIMIT 20''')
    data = c.fetchall(); conn.close()
    return jsonify(data)

if __name__ == '__main__':
    app.run(debug=True, port=8000)