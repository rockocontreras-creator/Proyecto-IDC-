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

# CONFIGURACIÓN GROQ (IA Gratuita y Multimodal)
# Asegúrate de poner aquí tu clave activa generada en la consola de Groq
client = Groq(api_key="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")

# --- BASE DE DATOS (Estructura 3FN Completa) ---
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

def guardar_busqueda(remedio, resultados):
    conn = sqlite3.connect('farmacia.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO medicamentos (nombre_buscado) VALUES (?)", (remedio.lower(),))
    cursor.execute("SELECT id FROM medicamentos WHERE nombre_buscado = ?", (remedio.lower(),))
    med_id = cursor.fetchone()[0]

    for r in resultados:
        cursor.execute("SELECT id FROM farmacias WHERE nombre = ?", (r['farmacia'],))
        f_id = cursor.fetchone()[0]
        try:
            precio_int = int(''.join(filter(str.isdigit, str(r['precio']))))
            cursor.execute('''INSERT INTO historial (farmacia_id, medicamento_id, nombre_producto, precio, link) 
                              VALUES (?,?,?,?,?)''', (f_id, med_id, r['nombre'], precio_int, r['link']))
        except: pass
    conn.commit()
    conn.close()

# --- MOTOR DE SCRAPING MULTIHILO (Selenium) ---
def get_driver():
    opts = Options()
    opts.add_argument("--headless")
    opts.add_argument("--blink-settings=imagesEnabled=false")
    opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)

def scrape_task(func, remedio, res_list):
    driver = get_driver()
    try: 
        func(remedio, driver, res_list)
    except Exception as e: 
        print(f"Error en hilo de farmacia: {e}")
    finally: 
        driver.quit()

def logic_ahumada(remedio, driver, res):
    driver.get(f"https://www.farmaciasahumada.cl/search?q={remedio}&srule=price-low-to-high&sz=1")
    WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.CLASS_NAME, "price")))
    nom = driver.find_element(By.CLASS_NAME, "pdp-link").text.strip()
    pre = driver.find_element(By.CLASS_NAME, "price").get_attribute("innerText").split('\n')[0].strip()
    lnk = driver.find_element(By.CLASS_NAME, "pdp-link").find_element(By.TAG_NAME, "a").get_attribute("href")
    res.append({"farmacia": "Ahumada", "nombre": nom, "precio": pre, "link": lnk, "color": "#003399"})

def logic_drsimi(remedio, driver, res):
    driver.get(f"https://www.drsimi.cl/{remedio}?_q={remedio}&map=ft&order=OrderByPriceASC")
    WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, "[class*='currencyContainer']")))
    nom = driver.find_element(By.CSS_SELECTOR, "[class*='brandName']").text.strip()
    pre = driver.find_element(By.CSS_SELECTOR, "[class*='currencyContainer']").get_attribute("innerText").strip()
    lnk = driver.find_element(By.CSS_SELECTOR, "a[class*='clearLink']").get_attribute("href")
    res.append({"farmacia": "Dr. Simi", "nombre": nom, "precio": pre, "link": lnk, "color": "#ce000c"})

def logic_salcobrand(remedio, driver, res):
    driver.get(f"https://salcobrand.cl/search_result?query={remedio}&sort=price_asc")
    WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, ".product-info")))
    d = driver.execute_script("""
        let p = document.querySelector('.product-info');
        if(!p) return null;
        let c = p.closest('.product');
        let priceElem = c.querySelector('.price:not(.old-price)') || c.querySelector('.price');
        return { n: p.innerText.split('\\n')[0], pr: priceElem.innerText, l: c.querySelector('a').href };
    """)
    if d:
        res.append({"farmacia": "Salcobrand", "nombre": d['n'], "precio": d['pr'], "link": d['l'], "color": "#ffd400"})

# --- RUTAS DE LA API ---

@app.route('/scraping_manual', methods=['POST'])
def scraping_manual():
    remedio = request.json.get('remedio', '')
    if not remedio: return jsonify({"error": "No se envió término"}), 400
    res = []
    threads = [
        threading.Thread(target=scrape_task, args=(logic_ahumada, remedio, res)),
        threading.Thread(target=scrape_task, args=(logic_drsimi, remedio, res)),
        threading.Thread(target=scrape_task, args=(logic_salcobrand, remedio, res))
    ]
    for t in threads: t.start()
    for t in threads: t.join()
    
    if res: guardar_busqueda(remedio, res)
    return jsonify({"precios": res})

@app.route('/obtener_historial')
def obtener_historial():
    conn = sqlite3.connect('farmacia.db')
    c = conn.cursor()
    c.execute('''SELECT m.nombre_buscado, f.nombre, h.nombre_producto, h.precio, h.fecha 
                 FROM historial h JOIN farmacias f ON h.farmacia_id = f.id 
                 JOIN medicamentos m ON h.medicamento_id = m.id ORDER BY h.fecha DESC LIMIT 20''')
    data = c.fetchall()
    conn.close()
    return jsonify(data)

@app.route('/consultar_asistente', methods=['POST'])
def consultar_asistente():
    data = request.json
    pregunta = data.get('pregunta', '')
    contexto = data.get('contexto_precios', '')
    archivo_base64 = data.get('archivo_base64') 

    reglas = (
        "Eres Mathew, asistente experto de FarmaConnect. Solo respondes sobre salud, medicamentos y análisis de recetas médicas. "
        "REGLA CRÍTICA IMPERATIVA: No puedes recetar ni formular dosis absolutas de medicamentos. No reemplazas bajo ninguna circunstancia a un médico. "
        "Si te preguntan cosas de otros dominios (política, entretenimiento, matemáticas, etc.), declina responder educadamente diciendo que estás limitado al ámbito de salud. "
        "Sé breve, claro, formal y añade siempre al final de respuestas asistenciales la sugerencia de visitar a un profesional médico."
    )

    try:
        # Modo con Imagen Adjunta usando el nuevo modelo de visión activo de Groq
        if archivo_base64:
            contenido_mensaje = [
                {"type": "text", "text": f"{reglas}\nContexto de precios actuales del scraping: {contexto}\nPregunta o instrucción adicional: {pregunta}"},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{archivo_base64}"
                    }
                }
            ]
            completion = client.chat.completions.create(
                model="llama-3.2-90b-vision-preview", # Modelo de visión actualizado y soportado por Groq
                messages=[{"role": "user", "content": contenido_mensaje}]
            )
        
        # Modo estándar (Sólo texto)
        else:
            completion = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {"role": "system", "content": reglas}, 
                    {"role": "user", "content": f"Contexto de precios: {contexto}. Pregunta: {pregunta}"}
                ]
            )
            
        return jsonify({"respuesta": completion.choices[0].message.content})
    except Exception as e:
        print(f"ERROR EN ASISTENTE: {e}")
        return jsonify({"respuesta": "Mathew no pudo procesar tu solicitud en este momento."}), 500

if __name__ == '__main__':
    app.run(debug=True, port=8000)