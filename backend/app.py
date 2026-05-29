from flask import Flask, request, jsonify  # Importa las clases para estructurar la API REST y manejar JSONs
from flask_cors import CORS                # Importa el control de acceso para permitir peticiones cross-origin desde el Frontend
from selenium import webdriver             # Importa el núcleo del motor de automatización para controlar el navegador Chrome
from selenium.webdriver.chrome.service import Service  # Permite gestionar el ciclo de vida del servicio de ChromeDriver
from selenium.webdriver.chrome.options import Options  # Permite inyectar argumentos de configuración al navegador (Headless, UA, etc.)
from selenium.webdriver.common.by import By            # Clase para definir las estrategias de búsqueda en el DOM (CLASS_NAME, CSS_SELECTOR)
from selenium.webdriver.support.ui import WebDriverWait # Permite implementar esperas explícitas basadas en condiciones de tiempo
from selenium.webdriver.support import expected_conditions as EC # Define los estados del DOM a esperar (presencia del elemento)
from webdriver_manager.chrome import ChromeDriverManager  # Automatiza la descarga y emparejamiento de la versión correcta de ChromeDriver
import threading                           # Librería nativa para instanciar subprocesos y ejecutar el raspado en hilos paralelos
import sqlite3                             # Motor de base de datos relacional integrado para gestionar la persistencia local
from groq import Groq                      # SDK oficial para conectar de forma asíncrona con los modelos LLM de Groq

app = Flask(__name__)  # Instancia la aplicación principal del micro-framework Flask
CORS(app)              # Aplica el middleware CORS para levantar las restricciones de seguridad del navegador sobre el puerto 8000

# CONFIGURACIÓN GROQ (Modelo de visión activo y rápido)
# Instancia el cliente de Groq asignando la API Key correspondiente para las llamadas de inferencia
client = Groq(api_key="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")

# --- BASE DE DATOS (Estructura 3FN) ---
def init_db():
    conn = sqlite3.connect('farmacia.db')  # Abre o crea el archivo binario de la base de datos local
    cursor = conn.cursor()                 # Instancia el objeto cursor para ejecutar sentencias SQL en la conexión
    
    # Crea la tabla maestra estática de cadenas farmacéuticas con restricciones de unicidad
    cursor.execute('CREATE TABLE IF NOT EXISTS farmacias (id INTEGER PRIMARY KEY, nombre TEXT UNIQUE, color TEXT)')
    
    # Crea la tabla maestra de términos buscados indexados de forma unívoca
    cursor.execute('CREATE TABLE IF NOT EXISTS medicamentos (id INTEGER PRIMARY KEY, nombre_buscado TEXT UNIQUE)')
    
    # Crea la tabla transaccional central con claves foráneas para estructurar la Tercera Forma Normal (3FN)
    cursor.execute('''CREATE TABLE IF NOT EXISTS historial 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, farmacia_id INTEGER, medicamento_id INTEGER, 
                       nombre_producto TEXT, precio INTEGER, fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP, link TEXT,
                       FOREIGN KEY(farmacia_id) REFERENCES farmacias(id),
                       FOREIGN KEY(medicamento_id) REFERENCES medicamentos(id))''')
                       
    # Declara el dataset inicial para poblar los registros constantes de los distribuidores
    farmacias_data = [(1, 'Ahumada', '#003399'), (2, 'Dr. Simi', '#ce000c'), (3, 'Salcobrand', '#ffd400')]
    
    # Inserta en lote ignorando duplicados para no corromper la tabla en reinicios del servidor
    cursor.executemany("INSERT OR IGNORE INTO farmacias VALUES (?,?,?)", farmacias_data)
    conn.commit()  # Consolida los cambios transaccionales en el disco físico
    conn.close()   # Libera la conexión para evitar fugas de memoria

init_db()  # Invoca la subrutina al arrancar la aplicación

def guardar_busqueda(remedio, resultados):
    conn = sqlite3.connect('farmacia.db')  # Establece conexión para registrar la lista transaccional compartida
    cursor = conn.cursor()
    
    # 1. Guardar el término de búsqueda genérico sanitizado en minúsculas
    cursor.execute("INSERT OR IGNORE INTO medicamentos (nombre_buscado) VALUES (?)", (remedio.lower().strip(),))
    cursor.execute("SELECT id FROM medicamentos WHERE nombre_buscado = ?", (remedio.lower().strip(),))
    med_id = cursor.fetchone()[0]  # Recupera el ID correspondiente al medicamento maestro

    # 2. Guardar las cotizaciones individuales en el Historial y limpiar formato Frontend
    for r in resultados:
        cursor.execute("SELECT id FROM farmacias WHERE nombre = ?", (r['farmacia'],))
        f_id = cursor.fetchone()[0]  # Resuelve la llave foránea id_farmacia
        try:
            # SOLUCIÓN NOMBRE VACÍO: Controla retrasos en el renderizado de Dr. Simi asignando el término de búsqueda
            if not r['nombre'] or r['nombre'].strip() == "":
                r['nombre'] = remedio.upper()

            # SOLUCIÓN PRECIO SALCOBRAND: Remueve strings comerciales secundarios (ej: "Precio farmacia $791")
            precio_crudo = str(r['precio']).split()[0]
            
            # Filtra de manera estricta aislando únicamente los caracteres numéricos
            precio_limpio = "".join(filter(str.isdigit, precio_crudo))
            if precio_limpio:
                precio_int = int(precio_limpio)  # Realiza el casting a entero para la persistencia relacional
                
                # SOLUCIÓN SIGNOS DUPLICADOS: Formatea con puntos de miles eliminando el "$" para el Frontend
                r['precio'] = f"{precio_int:,}".replace(",", ".")
                
                # Inserta el registro atómico en la serie de tiempo financiera de la tabla historial
                cursor.execute('''INSERT INTO historial (farmacia_id, medicamento_id, nombre_producto, precio, link) 
                                  VALUES (?,?,?,?,?)''', (f_id, med_id, r['nombre'], precio_int, r['link']))
        except Exception as e:
            print(f"Error al procesar precio de {r['farmacia']}: {e}")  # Bloque de contingencia por registro corrompido
            
    conn.commit()  # Ejecuta una única transacción atómica segura tras finalizar las iteraciones
    conn.close()

# --- MOTOR DE SCRAPING MULTIHILO INTACTO ---
def get_driver():
    opts = Options()
    opts.add_argument("--headless")       # Deshabilita la interfaz gráfica del navegador para maximizar el rendimiento
    opts.add_argument("--disable-gpu")     # Desactiva la aceleración por hardware (requerido para entornos CLI/Linux)
    opts.add_argument("--no-sandbox")       # Omite el aislamiento de procesos (necesario para ejecuciones en contenedores)
    opts.add_argument("--disable-dev-shm-usage") # Evita caídas por memoria compartida limitada en entornos Docker
    opts.add_argument("--disable-extensions")     # Desactiva extensiones del navegador para optimizar el arranque
    opts.add_argument("--blink-settings=imagesEnabled=false") # Configuración a nivel de motor de renderizado para omitir imágenes
    opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36") # Setea un User-Agent orgánico anti-bot
    
    # Bloquea explícitamente la descarga de imágenes a nivel de red para acelerar la latencia
    prefs = {"profile.managed_default_content_settings.images": 2}
    opts.add_experimental_option("prefs", prefs)
    
    # Instancia el controlador de Chrome acoplando el ChromeDriver descargado y las opciones configuradas
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
    driver.set_page_load_timeout(20) # Define un margen de espera de seguridad de 20 segundos para la carga del sitio
    return driver

def scrape_task(func, remedio, res_list):
    driver = None
    try: 
        driver = get_driver()          # Aprovisiona una instancia aislada de WebDriver por cada subproceso instanciado
        func(remedio, driver, res_list) # Ejecuta de forma dinámica la rutina lógica de raspado correspondiente
    except Exception as e:
        print(f"Error en ejecución del hilo de raspado: {e}")
    finally: 
        if driver:
            driver.quit() # Garantiza el cierre absoluto de las instancias de Chrome en memoria RAM (bloque finally)

# --- INTACTA SIN TOCAR ---
def logic_ahumada(remedio, driver, res):
    try:
        # Direcciona el navegador al buscador parametrizado con ordenamiento por menor precio
        driver.get(f"https://www.farmaciasahumada.cl/search?q={remedio}&srule=price-low-to-high&sz=1")
        # Inyecta una espera explícita condicional de hasta 8 segundos para comprobar la existencia del nodo de precio
        WebDriverWait(driver, 8).until(EC.presence_of_element_located((By.CLASS_NAME, "price")))
        # Extrae las propiedades de texto e hipervínculos utilizando la coincidencia de nombres de clases de la estructura
        nom = driver.find_element(By.CLASS_NAME, "pdp-link").text.strip()
        pre = driver.find_element(By.CLASS_NAME, "price").get_attribute("innerText").split('\n')[0].strip()
        lnk = driver.find_element(By.CLASS_NAME, "pdp-link").find_element(By.TAG_NAME, "a").get_attribute("href")
        # Añade de manera segura el diccionario resultante al listado compartido en memoria
        res.append({"farmacia": "Ahumada", "nombre": nom, "precio": pre, "link": lnk, "color": "#003399"})
    except Exception as e:
        print(f"Error específico en Farmacias Ahumada: {e}")

# --- CORREGIDA EN EXCLUSIVA PARA EL TIMEOUT ---
def logic_drsimi(remedio, driver, res):
    try:
        try:
            # Intentamos cargar la página de forma nativa
            driver.get(f"https://www.drsimi.cl/{remedio}?_q={remedio}&map=ft&order=OrderByPriceASC")
        except Exception as timeout_error:
            # Si salta un timeout del renderer por culpa de trackers lentos, forzamos la detención con JS
            # Esto permite que el HTML que ya se descargó pase a ser procesado de inmediato
            driver.execute_script("window.stop();")
        
        # Esperamos a que los selectores del producto base estén en pantalla
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "[class*='brandName'], [class*='productBrand']"))
        )
        
        nom = driver.find_element(By.CSS_SELECTOR, "[class*='brandName'], [class*='productBrand']").text.strip()
        pre = driver.find_element(By.CSS_SELECTOR, "[class*='currencyContainer'], [class*='sellingPrice']").get_attribute("innerText").strip()
        lnk = driver.find_element(By.CSS_SELECTOR, "a[class*='clearLink'], a[class*='product-summary']").get_attribute("href")
        
        res.append({"farmacia": "Dr. Simi", "nombre": nom, "precio": pre, "link": lnk, "color": "#ce000c"})
    except Exception as e:
        print(f"Error específico en Dr. Simi: {e}")

# --- INTACTA SIN TOCAR ---
def logic_salcobrand(remedio, driver, res):
    try:
        driver.get(f"https://salcobrand.cl/search_result?query={remedio}&sort=price_asc")
        
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".product, .product-info, .product-card"))
        )
        
        # Inyección de script JS en el navegador para extraer de manera directa los nodos clonados
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

# --- ENDPOINTS / RUTAS DE LA API ---

@app.route('/scraping_manual', methods=['POST'])
def scraping_manual():
    remedio = request.json.get('remedio', '')  # Recupera el parámetro clave enviado dentro del cuerpo JSON de la petición
    if not remedio: return jsonify({"error": "Falta el parámetro"}), 400
    res = []
    
    # Declaración e instanciación de los tres hilos concurrentes apuntando a sus respectivas subtareas
    threads = [
        threading.Thread(target=scrape_task, args=(logic_ahumada, remedio, res)),
        threading.Thread(target=scrape_task, args=(logic_drsimi, remedio, res)),
        threading.Thread(target=scrape_task, args=(logic_salcobrand, remedio, res))
    ]
    for t in threads: t.start()  # Inicializa la ejecución de los tres subprocesos en paralelo
    for t in threads: t.join()   # Sincroniza e interrumpe el flujo principal hasta que todos los hilos finalicen sus tareas
    
    if res: guardar_busqueda(remedio, res)  # Envía el set completo acumulado a la subrutina relacional
    return jsonify({"precios": res})       # Retorna al cliente de la SPA la colección estructurada final

@app.route('/obtener_medicamentos')
def obtener_medicamentos():
    conn = sqlite3.connect('farmacia.db')
    c = conn.cursor()
    c.execute("SELECT nombre_buscado FROM medicamentos ORDER BY nombre_buscado ASC") # Query para poblar el <select> del historial
    data = [row[0] for row in c.fetchall()]
    conn.close()
    return jsonify(data)

@app.route('/obtener_historial')
def obtener_historial():
    med = request.args.get('medicamento', '') # Captura el parámetro de consulta vía cadena de URL (Query String)
    conn = sqlite3.connect('farmacia.db')
    c = conn.cursor()
    
    if med:
        # Realiza el JOIN relacional completo bajo los parámetros del medicamento seleccionado para alimentar a Chart.js
        c.execute('''SELECT m.nombre_buscado, f.nombre, h.nombre_producto, h.precio, h.fecha 
                     FROM historial h JOIN farmacias f ON h.farmacia_id = f.id 
                     JOIN medicamentos m ON h.medicamento_id = m.id 
                     WHERE m.nombre_buscado = ? ORDER BY h.fecha ASC''', (med.lower(),))
    else:
        # Retorna una consulta genérica con límite de registros para no sobrecargar el ancho de banda
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
    archivo_base64 = data.get('archivo_base64') # Captura la imagen binaria codificada como string desde el Frontend

    # Inyección jerárquica del prompt clínico para condicionar el comportamiento y resguardar la seguridad del chat
    reglas = (
        "Eres Mathew, asistente clínico de FarmaConnect. Respondes exclusivamente sobre salud y recetas médicos. "
        "REGLA OBLIGATORIA: No des dosis absolutas y aclara que no reemplazas a un médico. Sé breve y formal."
    )

    try:
        if archivo_base64:
            # Estructura el payload multimodal inyectando el prefijo MIME y la cadena binaria legibles para la IA
            contenido = [
                {"type": "text", "text": f"{reglas}\nPrecios actuales: {contexto}\nPregunta: {pregunta}"},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{archivo_base64}"}}
            ]
            # Invoca el modelo de visión artificial masivo activo de Groq para el procesamiento OCR
            completion = client.chat.completions.create(model="llama-3.2-90b-vision-preview", messages=[{"role": "user", "content": contenido}])
        else:
            # Invoca el modelo optimizado para texto plano si no se adjuntaron archivos binarios
            completion = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "system", "content": reglas}, {"role": "user", "content": f"Contexto: {contexto}. Consulta: {pregunta}"}]
            )
        return jsonify({"respuesta": completion.choices[0].message.content}) # Retorna la respuesta generada por el LLM
    except Exception as e:
        print(f"Error en la API de inferencia de Groq: {e}")
        # Retorno adaptativo amigable para interceptar el error sin interrumpir ni congelar la sesión del cliente
        return jsonify({"respuesta": "Mathew está personalizando sus respuestas y experimentando problemas técnicos temporales."}), 500

if __name__ == '__main__':
    # Inicializa el servidor en modo de depuración activo escuchando solicitudes a través del puerto 8000
    app.run(debug=True, port=8000)