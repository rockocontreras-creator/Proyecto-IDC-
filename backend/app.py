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

# CONFIGURACIÓN GROQ (Modelo de visión activo y rápido)
client = Groq(api_key="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")

# --- BASE DE DATOS (Estructura 3FN) ---
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
    
    # 1. Guardar el término de búsqueda genérico
    cursor.execute("INSERT OR IGNORE INTO medicamentos (nombre_buscado) VALUES (?)", (remedio.lower().strip(),))
    cursor.execute("SELECT id FROM medicamentos WHERE nombre_buscado = ?", (remedio.lower().strip(),))
    med_id = cursor.fetchone()[0]

    # 2. Guardar las cotizaciones individuales en el Historial
    for r in resultados:
        cursor.execute("SELECT id FROM farmacias WHERE nombre = ?", (r['farmacia'],))
        f_id = cursor.fetchone()[0]
        try:
            # Limpieza estricta para dejar solo dígitos (ej: "$4.990" -> 4990)
            precio_limpio = "".join(filter(str.isdigit, str(r['precio'])))
            precio_int = int(precio_limpio)
            
            cursor.execute('''INSERT INTO historial (farmacia_id, medicamento_id, nombre_producto, precio, link) 
                              VALUES (?,?,?,?,?)''', (f_id, med_id, r['nombre'], precio_int, r['link']))
        except Exception as e:
            print(f"Error al procesar precio de {r['farmacia']}: {e}")
            
    conn.commit()
    conn.close()

# --- MOTOR DE SCRAPING MULTIHILO (Selenium Headless) ---
def get_driver():
    opts = Options()
    opts.add_argument("--headless")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--blink-settings=imagesEnabled=false")
    opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)

def scrape_task(func, remedio, res_list):
    driver = get_driver()
    try: 
        func(remedio, driver, res_list)
    except Exception as e:
        print(f"Error en hilo de raspado: {e}")
    finally: 
        driver.quit()

def logic_ahumada(remedio, driver, res):
    driver.get(f"https://www.farmaciasahumada.cl/search?q={remedio}&srule=price-low-to-high&sz=1")
    WebDriverWait(driver, 12).until(EC.presence_of_element_located((By.CLASS_NAME, "price")))
    nom = driver.find_element(By.CLASS_NAME, "pdp-link").text.strip()
    pre = driver.find_element(By.CLASS_NAME, "price").get_attribute("innerText").split('\n')[0].strip()
    lnk = driver.find_element(By.CLASS_NAME, "pdp-link").find_element(By.TAG_NAME, "a").get_attribute("href")
    res.append({"farmacia": "Ahumada", "nombre": nom, "precio": pre, "link": lnk, "color": "#003399"})

def logic_drsimi(remedio, driver, res):
    driver.get(f"https://www.drsimi.cl/{remedio}?_q={remedio}&map=ft&order=OrderByPriceASC")
    WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, "[class*='currencyContainer']")))
    nom = driver.find_element(By.CSS_SELECTOR, "[class*='brandName']").text.strip()
    pre = driver.find_element(By.CSS_SELECTOR, "[class*='currencyContainer']").get_attribute("innerText").strip()
    lnk = driver.find_element(By.CSS_SELECTOR, "a[class*='clearLink']").get_attribute("href")
    res.append({"farmacia": "Dr. Simi", "nombre": nom, "precio": pre, "link": lnk, "color": "#ce000c"})

def logic_salcobrand(remedio, driver, res):
    driver.get(f"https://salcobrand.cl/search_result?query={remedio}&sort=price_asc")
    WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.CSS_SELECTOR, ".product-info")))
    d = driver.execute_script("""
        let p = document.querySelector('.product-info');
        if(!p) return null;
        let c = p.closest('.product');
        let priceElem = c.querySelector('.price:not(.old-price)') || c.querySelector('.price');
        return { n: p.innerText.split('\\n')[0], pr: priceElem.innerText, l: c.querySelector('a').href };
    """)
    if d: 
        res.append({"farmacia": "Salcobrand", "nombre": d['n'], "precio": d['pr'], "link": d['l'], "color": "#ffd400"})

# --- ENDPOINTS / RUTAS DE LA API ---

@app.route('/scraping_manual', methods=['POST'])
def scraping_manual():
    remedio = request.json.get('remedio', '')
    if not remedio: return jsonify({"error": "Falta el parámetro"}), 400
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

@app.route('/obtener_medicamentos')
def obtener_medicamentos():
    conn = sqlite3.connect('farmacia.db')
    c = conn.cursor()
    c.execute("SELECT nombre_buscado FROM medicamentos ORDER BY nombre_buscado ASC")
    data = [row[0] for row in c.fetchall()]
    conn.close()
    return jsonify(data)

@app.route('/obtener_historial')
def obtener_historial():
    med = request.args.get('medicamento', '')
    conn = sqlite3.connect('farmacia.db')
    c = conn.cursor()
    
    if med:
        # Trae de forma ascendente por fecha (de antiguo a nuevo) para que Chart.js dibuje la línea hacia adelante
        c.execute('''SELECT m.nombre_buscado, f.nombre, h.nombre_producto, h.precio, h.fecha 
                     FROM historial h JOIN farmacias f ON h.farmacia_id = f.id 
                     JOIN medicamentos m ON h.medicamento_id = m.id 
                     WHERE m.nombre_buscado = ? ORDER BY h.fecha ASC''', (med.lower(),))
    else:
        c.execute('''SELECT m.nombre_buscado, f.nombre, h.nombre_producto, h.precio, h.fecha 
                     FROM historial h JOIN farmacias f ON h.farmacia_id = f.id 
                     JOIN medicamentos m ON h.medicamento_id = m.id ORDER BY h.fecha ASC LIMIT 30''')
                     
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
        "Eres Mathew, asistente clínico de FarmaConnect. Respondes exclusivamente sobre salud y recetas médicos. "
        "REGLA OBLIGATORIA: No des dosis absolutas y aclara que no reemplazas a un médico. Sé breve y formal."
    )

    try:
        if archivo_base64:
            contenido = [
                {"type": "text", "text": f"{reglas}\nPrecios actuales: {contexto}\nPregunta: {pregunta}"},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{archivo_base64}"}}
            ]
            completion = client.chat.completions.create(model="llama-3.2-90b-vision-preview", messages=[{"role": "user", "content": contenido}])
        else:
            completion = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "system", "content": rules}, {"role": "user", "content": f"Contexto: {contexto}. Consulta: {pregunta}"}]
            )
        return jsonify({"respuesta": completion.choices[0].message.content})
    except:
        return jsonify({"respuesta": "Mathew está experimentando problemas técnicos."}), 500

if __name__ == '__main__':
    app.run(debug=True, port=8000)