from flask import Flask, request, jsonify  # Importa el framework web y herramientas para manejar peticiones y JSON
from flask_cors import CORS  # Importa CORS para permitir que el frontend se comunique con el backend desde distintos puertos
from selenium import webdriver  # Importa el motor para automatizar la navegación web
from selenium.webdriver.chrome.service import Service  # Maneja el servicio del ejecutable del navegador Chrome
from selenium.webdriver.chrome.options import Options  # Permite configurar opciones del navegador (como el modo headless)
from selenium.webdriver.common.by import By  # Permite localizar elementos en el DOM (ID, Clase, Xpath, etc.)
from selenium.webdriver.support.ui import WebDriverWait  # Herramienta para pausar el código hasta que un elemento aparezca
from selenium.webdriver.support import expected_conditions as EC  # Define las condiciones lógicas para las esperas (ej: que sea visible)
from webdriver_manager.chrome import ChromeDriverManager  # Descarga y gestiona automáticamente la versión correcta de ChromeDriver
import threading  # Permite la ejecución de múltiples hilos en paralelo (Multithreading)
import sqlite3  # Motor de base de datos relacional ligero para persistencia de datos

app = Flask(__name__)  # Inicializa la aplicación Flask
CORS(app)  # Habilita CORS para evitar bloqueos de seguridad del navegador al consultar la API

# --- CONFIGURACIÓN BASE DE DATOS (3FN) ---
def init_db():
    conn = sqlite3.connect('farmacia.db')  # Crea o conecta con el archivo de base de datos local
    cursor = conn.cursor()  # Crea un objeto cursor para ejecutar comandos SQL
    
    # Crea la tabla maestra de Farmacias (Primera Entidad en 3FN)
    cursor.execute('CREATE TABLE IF NOT EXISTS farmacias (id INTEGER PRIMARY KEY, nombre TEXT UNIQUE, color TEXT)')
    
    # Crea la tabla maestra de Medicamentos buscados (Segunda Entidad en 3FN)
    cursor.execute('CREATE TABLE IF NOT EXISTS medicamentos (id INTEGER PRIMARY KEY, nombre_buscado TEXT UNIQUE)')
    
    # Crea la tabla relacional Historial para guardar registros temporales (Tercera Entidad en 3FN)
    cursor.execute('''CREATE TABLE IF NOT EXISTS historial 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                       farmacia_id INTEGER, 
                       medicamento_id INTEGER, 
                       nombre_producto TEXT, 
                       precio INTEGER, 
                       fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP, 
                       link TEXT,
                       FOREIGN KEY(farmacia_id) REFERENCES farmacias(id),
                       FOREIGN KEY(medicamento_id) REFERENCES medicamentos(id))''')
    
    # Inserta los datos básicos de las cadenas farmacéuticas si no existen previamente
    farmacias_data = [(1, 'Ahumada', '#003399'), (2, 'Dr. Simi', '#ce000c'), (3, 'Salcobrand', '#ffd400')]
    cursor.executemany("INSERT OR IGNORE INTO farmacias VALUES (?,?,?)", farmacias_data)
    conn.commit()  # Guarda los cambios de forma permanente
    conn.close()  # Cierra la conexión para liberar recursos

init_db()  # Ejecuta la inicialización de la base de datos al arrancar el servidor

def guardar_busqueda(remedio_buscado, resultados):
    conn = sqlite3.connect('farmacia.db')  # Abre conexión con la BD
    cursor = conn.cursor()
    
    # Inserta el medicamento buscado en minúsculas para normalizar datos
    cursor.execute("INSERT OR IGNORE INTO medicamentos (nombre_buscado) VALUES (?)", (remedio_buscado.lower(),))
    # Obtiene el ID del medicamento recién insertado o ya existente
    cursor.execute("SELECT id FROM medicamentos WHERE nombre_buscado = ?", (remedio_buscado.lower(),))
    med_id = cursor.fetchone()[0]

    for r in resultados:
        # Busca el ID de la farmacia correspondiente según el nombre capturado en el scraping
        cursor.execute("SELECT id FROM farmacias WHERE nombre = ?", (r['farmacia'],))
        f_id = cursor.fetchone()[0]
        try:
            # Filtra solo los caracteres numéricos del precio (ej: "$1.990" -> 1990) para guardarlo como entero
            precio_int = int(''.join(filter(str.isdigit, str(r['precio']))))
            # Inserta el registro completo vinculando las IDs (Cumplimiento de 3FN)
            cursor.execute('''INSERT INTO historial (farmacia_id, medicamento_id, nombre_producto, precio, link) 
                              VALUES (?,?,?,?,?)''', (f_id, med_id, r['nombre'], precio_int, r['link']))
        except Exception as e: 
            print(f"Error al guardar registro: {e}")
    conn.commit()
    conn.close()

# --- LÓGICA DE SCRAPING ---
def get_driver():
    opts = Options()
    opts.add_argument("--headless")  # Ejecuta el navegador en segundo plano (sin ventana visible)
    opts.page_load_strategy = 'eager'  # Carga solo el DOM esencial para acelerar el scraping
    opts.add_argument("--blink-settings=imagesEnabled=false")  # Deshabilita imágenes para ahorrar ancho de banda y tiempo
    # Configura un User-Agent real para evitar que los sitios bloqueen al script por parecer un bot
    opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36")
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)

def scrape_task(func, remedio, res_list):
    driver = get_driver()  # Crea una nueva instancia de navegador para este hilo específico
    try: 
        func(remedio, driver, res_list)  # Ejecuta la función de scraping específica (Ahumada, Simi o Salcobrand)
    except Exception as e: 
        print(f"Error en {func.__name__}: {e}")
    finally: 
        driver.quit()  # Asegura que el navegador se cierre siempre, liberando memoria RAM

def logic_ahumada(remedio, driver, res):
    # Navega a la URL de búsqueda de Ahumada ordenando por precio menor
    driver.get(f"https://www.farmaciasahumada.cl/search?q={remedio}&srule=price-low-to-high&sz=1")
    # Espera hasta 15 segundos a que aparezca el elemento de precio
    WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.CLASS_NAME, "price")))
    # Extrae el nombre, precio y enlace usando selectores de clase CSS
    nom = driver.find_element(By.CLASS_NAME, "pdp-link").text.strip()
    pre = driver.find_element(By.CLASS_NAME, "price").get_attribute("innerText").split('\n')[0].strip()
    lnk = driver.find_element(By.CLASS_NAME, "pdp-link").find_element(By.TAG_NAME, "a").get_attribute("href")
    # Agrega el resultado al diccionario compartido
    res.append({"farmacia": "Ahumada", "nombre": nom, "precio": pre, "link": lnk, "color": "#003399"})

def logic_drsimi(remedio, driver, res):
    # Navega a Dr. Simi usando parámetros de búsqueda y orden de precio
    driver.get(f"https://www.drsimi.cl/{remedio}?_q={remedio}&map=ft&order=OrderByPriceASC")
    # Espera extendida de 30 segundos por la lentitud de carga de este sitio
    WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.CSS_SELECTOR, ".vtex-product-price-1-x-currencyContainer")))
    nom = driver.find_element(By.CSS_SELECTOR, "[class*='brandName']").text.strip()
    pre = driver.find_element(By.CSS_SELECTOR, ".vtex-product-price-1-x-currencyContainer").get_attribute("innerText").strip()
    lnk = driver.find_element(By.CSS_SELECTOR, "a[class*='clearLink']").get_attribute("href")
    res.append({"farmacia": "Dr. Simi", "nombre": nom, "precio": pre, "link": lnk, "color": "#ce000c"})

def logic_salcobrand(remedio, driver, res):
    driver.get(f"https://salcobrand.cl/search_result?query={remedio}&sort=price_asc")
    WebDriverWait(driver, 25).until(EC.presence_of_element_located((By.CSS_SELECTOR, ".price")))
    # Ejecuta código JavaScript directamente en el navegador para extraer datos de forma más precisa en Salcobrand
    d = driver.execute_script("""
        let p = document.querySelector('.product-info');
        if(!p) return null;
        let c = p.closest('.product');
        let priceElem = c.querySelector('.price:not(.old-price)') || c.querySelector('.price');
        return { n: p.innerText.split('\\n')[0], pr: priceElem.innerText, l: c.querySelector('a').href };
    """)
    if d:
        res.append({"farmacia": "Salcobrand", "nombre": d['n'], "precio": d['pr'], "link": d['l'], "color": "#ffd400"})

@app.route('/scraping_manual', methods=['POST'])
def scraping_manual():
    remedio = request.json.get('remedio', '')  # Obtiene el nombre del remedio enviado desde el frontend
    res = []
    # Crea hilos de ejecución para consultar las 3 farmacias al mismo tiempo
    threads = [threading.Thread(target=scrape_task, args=(f, remedio, res)) for f in [logic_ahumada, logic_drsimi, logic_salcobrand]]
    for t in threads: t.start()  # Inicia todos los hilos
    for t in threads: t.join()   # Espera a que todos los hilos terminen antes de continuar
    if res: 
        guardar_busqueda(remedio, res)  # Guarda los resultados en la base de datos
    return jsonify({"precios": res})  # Envía los resultados al frontend en formato JSON

@app.route('/obtener_historial')
def obtener_historial():
    conn = sqlite3.connect('farmacia.db')
    c = conn.cursor()
    # Ejecuta una consulta compleja uniendo las 3 tablas (JOIN) para mostrar el historial legible
    c.execute('''SELECT m.nombre_buscado, f.nombre, h.nombre_producto, h.precio, h.fecha 
                 FROM historial h 
                 JOIN farmacias f ON h.farmacia_id = f.id 
                 JOIN medicamentos m ON h.medicamento_id = m.id 
                 ORDER BY h.fecha DESC LIMIT 30''')
    data = c.fetchall()
    conn.close()
    return jsonify(data)  # Envía los últimos 30 registros del historial al frontend

if __name__ == '__main__':
    # Inicia el servidor local en el puerto 5000
    app.run(debug=False, port=5000)