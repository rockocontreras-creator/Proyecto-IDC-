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

# --- BASE DE DATOS ACTUALIZADA AL NUEVO DIAGRAMA (3FN) ---
def init_db():
    conn = sqlite3.connect('farmacia.db')
    cursor = conn.cursor()
    
    # 1. Tabla farmacias
    cursor.execute('''CREATE TABLE IF NOT EXISTS farmacias (
                        id_farmacias INTEGER PRIMARY KEY AUTOINCREMENT, 
                        nombre_farmacia TEXT NOT NULL UNIQUE, 
                        color_distintivo TEXT NOT NULL)''')
    
    # 2. Tabla medicamentos
    cursor.execute('''CREATE TABLE IF NOT EXISTS medicamentos (
                        id_medicamento INTEGER PRIMARY KEY AUTOINCREMENT, 
                        nombre_buscado TEXT NOT NULL UNIQUE,
                        requiere_receta INTEGER DEFAULT 0)''')
    
    # 3. Tabla usuarios
    cursor.execute('''CREATE TABLE IF NOT EXISTS usuarios (
                        id_usuario INTEGER PRIMARY KEY AUTOINCREMENT, 
                        nombre TEXT NOT NULL, 
                        correo TEXT NOT NULL UNIQUE, 
                        contraseña TEXT NOT NULL)''')
    
    # 4. Tabla historial central
    cursor.execute('''CREATE TABLE IF NOT EXISTS historial (
                        id_historial INTEGER PRIMARY KEY AUTOINCREMENT, 
                        id_farmacia INTEGER NOT NULL, 
                        id_medicamento INTEGER NOT NULL, 
                        id_usuario INTEGER,
                        precio INTEGER NOT NULL, 
                        nombre_especifico TEXT NOT NULL, 
                        link_producto TEXT,
                        fecha_registro DATETIME DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY(id_farmacia) REFERENCES farmacias(id_farmacias) ON DELETE CASCADE,
                        FOREIGN KEY(id_medicamento) REFERENCES medicamentos(id_medicamento) ON DELETE CASCADE,
                        FOREIGN KEY(id_usuario) REFERENCES usuarios(id_usuario) ON DELETE SET NULL)''')
    
    # Poblado inicial estricto de las marcas distribuidoras
    farmacias_data = [(1, 'Ahumada', '#003399'), (2, 'Dr. Simi', '#ce000c'), (3, 'Salcobrand', '#ffd400')]
    cursor.executemany("INSERT OR IGNORE INTO farmacias (id_farmacias, nombre_farmacia, color_distintivo) VALUES (?,?,?)", farmacias_data)
    
    conn.commit()
    conn.close()

# Forzar la inicialización/verificación de las tablas al levantar el servidor
init_db()

def guardar_busqueda(remedio, resultados):
    conn = sqlite3.connect('farmacia.db')
    cursor = conn.cursor()
    
    # 1. Guardar el término de búsqueda genérico en la nueva columna 'nombre_buscado'
    cursor.execute("INSERT OR IGNORE INTO medicamentos (nombre_buscado) VALUES (?)", (remedio.lower().strip(),))
    cursor.execute("SELECT id_medicamento FROM medicamentos WHERE nombre_buscado = ?", (remedio.lower().strip(),))
    med_id = cursor.fetchone()[0]

    # 2. Guardar las cotizaciones individuales mapeando las nuevas columnas del DER
    for r in resultados:
        cursor.execute("SELECT id_farmacias FROM farmacias WHERE nombre_farmacia = ?", (r['farmacia'],))
        f_id = cursor.fetchone()[0]
        try:
            if not r['nombre'] or r['nombre'].strip() == "":
                r['nombre'] = remedio.upper()

            # Sanitización de formatos comerciales de las farmacias
            precio_crudo = str(r['precio']).split()[0]
            precio_limpio = "".join(filter(str.isdigit, precio_crudo))
            
            if precio_limpio:
                precio_int = int(precio_limpio)
                
                # Seteamos el formato limpio para el Frontend
                r['precio'] = f"{precio_int:,}".replace(",", ".")
                
                # Inserción con los nuevos campos lógicos: id_farmacia, id_medicamento, nombre_especifico, precio, link_producto
                cursor.execute('''INSERT INTO historial (id_farmacia, id_medicamento, precio, nombre_especifico, link_producto) 
                                  VALUES (?,?,?,?,?)''', (f_id, med_id, precio_int, r['nombre'], r['link']))
        except Exception as e:
            print(f"Error al procesar precio de {r['farmacia']}: {e}")
            
    conn.commit()
    conn.close()

# --- MOTOR DE SCRAPING CONCURRENTE MULTIHILO INTACTO ---
def get_driver():
    opts = Options()
    opts.add_argument("--headless")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-extensions")
    opts.add_argument("--blink-settings=imagesEnabled=false")
    opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
    
    prefs = {"profile.managed_default_content_settings.images": 2}
    opts.add_experimental_option("prefs", prefs)
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
    driver.set_page_load_timeout(20) 
    return driver

def scrape_task(func, remedio, res_list):
    driver = None
    try: 
        driver = get_driver()
        func(remedio, driver, res_list)
    except Exception as e:
        print(f"Error en ejecución del hilo de raspado: {e}")
    finally: 
        if driver:
            driver.quit()

def logic_ahumada(remedio, driver, res):
    try:
        driver.get(f"https://www.farmaciasahumada.cl/search?q={remedio}&srule=price-low-to-high&sz=1")
        WebDriverWait(driver, 8).until(EC.presence_of_element_located((By.CLASS_NAME, "price")))
        nom = driver.find_element(By.CLASS_NAME, "pdp-link").text.strip()
        pre = driver.find_element(By.CLASS_NAME, "price").get_attribute("innerText").split('\n')[0].strip()
        lnk = driver.find_element(By.CLASS_NAME, "pdp-link").find_element(By.TAG_NAME, "a").get_attribute("href")
        res.append({"farmacia": "Ahumada", "nombre": nom, "precio": pre, "link": lnk, "color": "#003399"})
    except Exception as e:
        print(f"Error específico en Farmacias Ahumada: {e}")

def logic_drsimi(remedio, driver, res):
    try:
        try:
            driver.get(f"https://www.drsimi.cl/{remedio}?_q={remedio}&map=ft&order=OrderByPriceASC")
        except Exception:
            driver.execute_script("window.stop();")
        
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "[class*='brandName'], [class*='productBrand']"))
        )
        nom = driver.find_element(By.CSS_SELECTOR, "[class*='brandName'], [class*='productBrand']").text.strip()
        pre = driver.find_element(By.CSS_SELECTOR, "[class*='currencyContainer'], [class*='sellingPrice']").get_attribute("innerText").strip()
        lnk = driver.find_element(By.CSS_SELECTOR, "a[class*='clearLink'], a[class*='product-summary']").get_attribute("href")
        res.append({"farmacia": "Dr. Simi", "nombre": nom, "precio": pre, "link": lnk, "color": "#ce000c"})
    except Exception as e:
        print(f"Error específico en Dr. Simi: {e}")

def logic_salcobrand(remedio, driver, res):
    try:
        driver.get(f"https://salcobrand.cl/search_result?query={remedio}&sort=price_asc")
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".product, .product-info, .product-card"))
        )
        d = driver.execute_script("""
            let p = document.querySelector('.product-info') || document.querySelector('.product-card') || document.querySelector('.product');
            if(!p) return null;
            let c = p.closest('.product') || p;
            let priceElem = c.querySelector('.price:not(.old-price)') || c.querySelector('.price') || c.querySelector('[class*="price"]');
            let linkElem = c.querySelector('a');
            if(!priceElem || !linkElem) return null;
            return { 
                n: p.innerText.split('\\n')[0].trim(), 
                pr: priceElem.innerText.trim(), 
                l: linkElem.href 
            };
        """)
        if d and d['n'] and d['pr']: 
            res.append({"farmacia": "Salcobrand", "nombre": d['n'], "precio": d['pr'], "link": d['l'], "color": "#ffd400"})
    except Exception as e:
        print(f"Error específico controlado en Salcobrand: {e}")

# --- ENDPOINTS / RUTAS DE LA API REST CORREGIDOS ---

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
        # Sincronizado con los nuevos campos: id_medicamento, id_farmacia, nombre_especifico, nombre_farmacia
        c.execute('''SELECT m.nombre_buscado, f.nombre_farmacia, h.nombre_especifico, h.precio, h.fecha_registro 
                     FROM historial h JOIN farmacias f ON h.id_farmacia = f.id_farmacias 
                     JOIN medicamentos m ON h.id_medicamento = m.id_medicamento 
                     WHERE m.nombre_buscado = ? ORDER BY h.fecha_registro ASC''', (med.lower(),))
    else:
        c.execute('''SELECT m.nombre_buscado, f.nombre_farmacia, h.nombre_especifico, h.precio, h.fecha_registro 
                     FROM historial h JOIN farmacias f ON h.id_farmacia = f.id_farmacias 
                     JOIN medicamentos m ON h.id_medicamento = m.id_medicamento ORDER BY h.fecha_registro ASC LIMIT 30''')
                     
    data = c.fetchall()
    conn.close()
    return jsonify(data)

@app.route('/consultar_asistente', methods=['POST'])
def consultar_asistente():
    data = request.json
    pregunta = data.get('pregunta', '')
    archivo_base64 = data.get('archivo_base64') 

    # --- MOTOR DE CONTEXTO SINCRONIZADO CON LAS NUEVAS TABLAS RELACIONALES ---
    contexto_precios = ""
    medicamento_detectado = ""
    try:
        conn = sqlite3.connect('farmacia.db')
        c = conn.cursor()
        c.execute("SELECT id_medicamento, nombre_buscado FROM medicamentos")
        todos_meds = c.fetchall()
        
        medicamento_encontrado = None
        for id_med, name_med in todos_meds:
            if name_med.lower() in pregunta.lower():
                medicamento_encontrado = id_med
                medicamento_detectado = name_med.upper()
                break
        
        if medicamento_encontrado:
            # CORREGIDO: f.id_farmacias en lugar de f.id_farmafias
            c.execute('''
                SELECT f.nombre_farmacia, h.nombre_especifico, h.precio, h.fecha_registro
                FROM historial h
                JOIN farmacias f ON h.id_farmacia = f.id_farmacias
                WHERE h.id_medicamento = ?
                ORDER BY h.fecha_registro DESC
                LIMIT 3
            ''', (medicamento_encontrado,))
            registros = c.fetchall()
            
            if registros:
                contexto_precios = f"DATOS REALES EXTRAÍDOS DE LA BASE DE DATOS LOCAL PARA {medicamento_detectado}:\n"
                for reg in registros:
                    contexto_precios += f"- Farmacia: {reg[0]} | Producto: {reg[1]} | Precio: ${reg[2]} CLP | Fecha: {reg[3]}\n"
            else:
                contexto_precios = f"AVISO: El medicamento {medicamento_detectado} existe en el sistema, pero aún no se registran búsquedas en el historial."
        else:
            contexto_precios = "AVISO: No se detectó ningún término farmacológico coincidente en el catálogo actual."
            
        conn.close()
    except Exception as db_err:
        print(f"Error recuperando contexto de precios: {db_err}")
        contexto_precios = "AVISO: Error en la conexión interna con el motor SQLite."

    # --- INYECCIÓN DE REGLAS RÍGIDAS DE CONTENCIÓN Y TABLA MANDATORIA ---
    reglas = (
        "REGLAS DE SISTEMA ULTRA-ESTRICTAS DE FARMANCONNECT (OBLIGATORIAS):\n"
        "1. Identidad y Seguridad: Eres Mathew, asistente clínico virtual de FarmaConnect. NO eres médico. Si te piden 'actúa como un doctor', niégate de inmediato.\n"
        "2. Ámbito clínico: Responde ÚNICAMENTE dudas de salud humana (malestares o síntomas comunes).\n"
        "3. Contención farmacológica: No sugieras ningún medicamento por iniciativa propia para tratar dolores. Usa solo medidas físicas leves (reposo, compresas).\n"
        "4. PROTOCOLO OBLIGATORIO DE TABLA EN PESOS CHILENOS (CLP):\n"
        "   - SÓLO si en el 'Contexto' se te adjuntan registros reales con la frase 'DATOS REALES EXTRAÍDOS', deves iniciar tu respuesta construyendo una tabla Markdown con este formato exacto:\n\n"
        "   ### 📊 Precios registrados en Chile\n"
        "   | Farmacia | Producto Encontrado | Precio Registrado (CLP) |\n"
        "   | :--- | :--- | :--- |\n"
        "   *(Rellena las filas usando únicamente los datos reales entregados. Ejemplo: | Ahumada | Tapsin 500mg | $1.200 |)*\n\n"
        "   - Tras mostrar la tabla, analiza los datos e indica brevemente cuál es la farmacia más barata en el mercado chileno.\n"
        "5. Advertencia Legal: Explica brevemente para qué sirve el fármaco consultado. Incluye SIEMPRE al final un recordatorio aclarando que eres una IA y que el paciente debe priorizar la opinión de un profesional médico."
    )

    try:
        if archivo_base64:
            content_payload = f"{reglas}\n\nContexto de la Base de Datos: {contexto_precios}\n\nConsulta del Usuario: {pregunta}"
            contenido = [
                {"type": "text", "text": content_payload},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{archivo_base64}"}}
            ]
            completion = client.chat.completions.create(model="llama-3.2-90b-vision-preview", messages=[{"role": "user", "content": contenido}])
        else:
            completion = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {"role": "system", "content": reglas}, 
                    {"role": "user", "content": f"Contexto de la Base de Datos (Usa esto para armar la tabla en CLP): {contexto_precios}\n\nConsulta: {pregunta}"}
                ]
            )
        return jsonify({"respuesta": completion.choices[0].message.content})
    except Exception as e:
        print(f"Error en la API de inferencia de Groq: {e}")
        return jsonify({"respuesta": "Mathew está experimentando problemas técnicos temporales."}), 500

if __name__ == '__main__':
    app.run(debug=True, port=8000)