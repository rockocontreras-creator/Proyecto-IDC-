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
import hashlib
import secrets
import os
from groq import Groq

app = Flask(__name__)
# CORS abierto para desarrollo local — acepta cualquier origen
CORS(app, resources={r"/*": {"origins": "*"}})

client = Groq(api_key="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")

APP_SECRET = 'farmaconnect_dev_secret_2024'

# =========================================================
# TOKENS EN MEMORIA (reemplaza flask.session — sin cookies)
# dict { token_str -> { id, nombre, correo } }
# =========================================================
_tokens: dict = {}

def crear_token(user_id: int, nombre: str, correo: str) -> str:
    token = secrets.token_hex(32)
    _tokens[token] = {"id": user_id, "nombre": nombre, "correo": correo}
    return token

def resolver_token() -> dict | None:
    """Lee el header Authorization: Bearer <token> y devuelve el usuario o None."""
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]
        return _tokens.get(token)
    return None

def hash_password(password: str) -> str:
    return hashlib.sha256(f"{APP_SECRET}{password}".encode()).hexdigest()

# =========================================================
# BASE DE DATOS
# =========================================================
def init_db():
    conn = sqlite3.connect('farmacia.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS farmacias (
                        id_farmacias INTEGER PRIMARY KEY AUTOINCREMENT,
                        nombre_farmacia TEXT NOT NULL UNIQUE,
                        color_distintivo TEXT NOT NULL)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS medicamentos (
                        id_medicamento INTEGER PRIMARY KEY AUTOINCREMENT,
                        nombre_buscado TEXT NOT NULL UNIQUE,
                        requiere_receta INTEGER DEFAULT 0)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS usuarios (
                        id_usuario INTEGER PRIMARY KEY AUTOINCREMENT,
                        nombre TEXT NOT NULL,
                        correo TEXT NOT NULL UNIQUE,
                        contraseña TEXT NOT NULL)''')
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
    farmacias_data = [(1, 'Ahumada', '#003399'), (2, 'Dr. Simi', '#ce000c'), (3, 'Salcobrand', '#ffd400')]
    cursor.executemany("INSERT OR IGNORE INTO farmacias (id_farmacias, nombre_farmacia, color_distintivo) VALUES (?,?,?)", farmacias_data)
    conn.commit()
    conn.close()

init_db()

# =========================================================
# AUTH ENDPOINTS
# =========================================================

@app.route('/registro', methods=['POST'])
def registro():
    data = request.json
    nombre   = data.get('nombre', '').strip()
    correo   = data.get('correo', '').strip().lower()
    password = data.get('password', '')

    if not nombre or not correo or not password:
        return jsonify({"error": "Todos los campos son obligatorios."}), 400
    if len(password) < 6:
        return jsonify({"error": "La contraseña debe tener al menos 6 caracteres."}), 400
    if '@' not in correo or '.' not in correo:
        return jsonify({"error": "Correo electrónico inválido."}), 400

    conn = sqlite3.connect('farmacia.db')
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO usuarios (nombre, correo, contraseña) VALUES (?, ?, ?)",
                       (nombre, correo, hash_password(password)))
        conn.commit()
        user_id = cursor.lastrowid
        token = crear_token(user_id, nombre, correo)
        return jsonify({
            "mensaje": "Cuenta creada con éxito.",
            "token": token,
            "usuario": {"id": user_id, "nombre": nombre, "correo": correo}
        }), 201
    except sqlite3.IntegrityError:
        return jsonify({"error": "Este correo ya está registrado."}), 409
    finally:
        conn.close()


@app.route('/login', methods=['POST'])
def login():
    data     = request.json
    correo   = data.get('correo', '').strip().lower()
    password = data.get('password', '')

    if not correo or not password:
        return jsonify({"error": "Correo y contraseña son obligatorios."}), 400

    conn = sqlite3.connect('farmacia.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id_usuario, nombre, correo FROM usuarios WHERE correo = ? AND contraseña = ?",
                   (correo, hash_password(password)))
    usuario = cursor.fetchone()
    conn.close()

    if not usuario:
        return jsonify({"error": "Correo o contraseña incorrectos."}), 401

    token = crear_token(usuario[0], usuario[1], usuario[2])
    return jsonify({
        "mensaje": "Sesión iniciada.",
        "token": token,
        "usuario": {"id": usuario[0], "nombre": usuario[1], "correo": usuario[2]}
    })


@app.route('/logout', methods=['POST'])
def logout():
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        _tokens.pop(auth[7:], None)
    return jsonify({"mensaje": "Sesión cerrada."})


@app.route('/me', methods=['GET'])
def me():
    usuario = resolver_token()
    if usuario:
        return jsonify({"autenticado": True, "usuario": usuario})
    return jsonify({"autenticado": False}), 401


# =========================================================
# SCRAPING
# =========================================================

def guardar_busqueda(remedio, resultados, user_id=None):
    conn = sqlite3.connect('farmacia.db')
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO medicamentos (nombre_buscado) VALUES (?)", (remedio.lower().strip(),))
    cursor.execute("SELECT id_medicamento FROM medicamentos WHERE nombre_buscado = ?", (remedio.lower().strip(),))
    med_id = cursor.fetchone()[0]

    for r in resultados:
        cursor.execute("SELECT id_farmacias FROM farmacias WHERE nombre_farmacia = ?", (r['farmacia'],))
        f_id = cursor.fetchone()[0]
        try:
            if not r['nombre'] or r['nombre'].strip() == "":
                r['nombre'] = remedio.upper()
            precio_crudo = str(r['precio']).split()[0]
            precio_limpio = "".join(filter(str.isdigit, precio_crudo))
            if precio_limpio:
                precio_int = int(precio_limpio)
                r['precio'] = f"{precio_int:,}".replace(",", ".")
                cursor.execute(
                    '''INSERT INTO historial (id_farmacia, id_medicamento, id_usuario, precio, nombre_especifico, link_producto)
                       VALUES (?,?,?,?,?,?)''',
                    (f_id, med_id, user_id, precio_int, r['nombre'], r['link'])
                )
        except Exception as e:
            print(f"Error al procesar precio de {r['farmacia']}: {e}")
    conn.commit()
    conn.close()


def get_driver():
    opts = Options()
    opts.add_argument("--headless=new")           # nuevo modo headless más estable
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-extensions")
    opts.add_argument("--disable-software-rasterizer")
    opts.add_argument("--disable-background-networking")
    opts.add_argument("--disable-default-apps")
    opts.add_argument("--disable-sync")
    opts.add_argument("--no-first-run")
    opts.add_argument("--blink-settings=imagesEnabled=false")
    opts.add_argument("--window-size=1280,800")
    opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36")
    prefs = {
        "profile.managed_default_content_settings.images": 2,
        "profile.managed_default_content_settings.stylesheets": 2,  # bloquea CSS → más rápido
    }
    opts.add_experimental_option("prefs", prefs)
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    service = Service(ChromeDriverManager().install(), log_output=os.devnull)  # silencia logs de chromedriver
    driver = webdriver.Chrome(service=service, options=opts)
    driver.set_page_load_timeout(12)   # reducido de 20 → 12s
    return driver


def scrape_task(func, remedio, res_list):
    driver = None
    try:
        driver = get_driver()
        func(remedio, driver, res_list)
    except Exception as e:
        print(f"Error en hilo de raspado: {e}")
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
        print(f"Error Ahumada: {e}")


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
        print(f"Error Dr. Simi: {e}")


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
            return { n: p.innerText.split('\\n')[0].trim(), pr: priceElem.innerText.trim(), l: linkElem.href };
        """)
        if d and d['n'] and d['pr']:
            res.append({"farmacia": "Salcobrand", "nombre": d['n'], "precio": d['pr'], "link": d['l'], "color": "#ffd400"})
    except Exception as e:
        print(f"Error Salcobrand: {e}")


@app.route('/scraping_manual', methods=['POST'])
def scraping_manual():
    # Requiere sesión — lee token del header
    usuario = resolver_token()
    if not usuario:
        return jsonify({"error": "Debes iniciar sesión para usar el comparador."}), 401

    remedio = request.json.get('remedio', '')
    if not remedio:
        return jsonify({"error": "Falta el parámetro"}), 400

    res = []
    threads = [
        threading.Thread(target=scrape_task, args=(logic_ahumada, remedio, res)),
        threading.Thread(target=scrape_task, args=(logic_drsimi, remedio, res)),
        threading.Thread(target=scrape_task, args=(logic_salcobrand, remedio, res))
    ]
    for t in threads: t.start()
    for t in threads: t.join()

    if res:
        guardar_busqueda(remedio, res, user_id=usuario.get("id"))
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
        c.execute('''SELECT m.nombre_buscado, f.nombre_farmacia, h.nombre_especifico, h.precio, h.fecha_registro
                     FROM historial h JOIN farmacias f ON h.id_farmacia = f.id_farmacias
                     JOIN medicamentos m ON h.id_medicamento = m.id_medicamento
                     WHERE m.nombre_buscado = ? ORDER BY h.fecha_registro ASC''', (med.lower(),))
    else:
        c.execute('''SELECT m.nombre_buscado, f.nombre_farmacia, h.nombre_especifico, h.precio, h.fecha_registro
                     FROM historial h JOIN farmacias f ON h.id_farmacia = f.id_farmacias
                     JOIN medicamentos m ON h.id_medicamento = m.id_medicamento
                     ORDER BY h.fecha_registro ASC LIMIT 30''')
    data = c.fetchall()
    conn.close()
    return jsonify(data)


@app.route('/consultar_asistente', methods=['POST'])
def consultar_asistente():
    # IA es pública — no requiere token
    data = request.json
    pregunta = data.get('pregunta', '')
    archivo_base64 = data.get('archivo_base64')

    contexto_precios = ""
    try:
        conn = sqlite3.connect('farmacia.db')
        c = conn.cursor()
        c.execute("SELECT id_medicamento, nombre_buscado FROM medicamentos")
        todos_meds = c.fetchall()
        medicamento_encontrado = None
        medicamento_detectado = ""
        for id_med, name_med in todos_meds:
            if name_med.lower() in pregunta.lower():
                medicamento_encontrado = id_med
                medicamento_detectado = name_med.upper()
                break

        if medicamento_encontrado:
            c.execute('''SELECT f.nombre_farmacia, h.nombre_especifico, h.precio, h.fecha_registro
                         FROM historial h JOIN farmacias f ON h.id_farmacia = f.id_farmacias
                         WHERE h.id_medicamento = ? ORDER BY h.fecha_registro DESC LIMIT 3''',
                      (medicamento_encontrado,))
            registros = c.fetchall()
            if registros:
                contexto_precios = f"DATOS REALES EXTRAÍDOS DE LA BASE DE DATOS LOCAL PARA {medicamento_detectado}:\n"
                for reg in registros:
                    contexto_precios += f"- Farmacia: {reg[0]} | Producto: {reg[1]} | Precio: ${reg[2]} CLP | Fecha: {reg[3]}\n"
            else:
                contexto_precios = f"AVISO: {medicamento_detectado} existe pero sin historial aún."
        else:
            contexto_precios = "AVISO: No se detectó término farmacológico en el catálogo."
        conn.close()
    except Exception as db_err:
        print(f"Error DB: {db_err}")
        contexto_precios = "AVISO: Error interno SQLite."

    reglas = (
        "REGLAS DE SISTEMA ULTRA-ESTRICTAS DE FARMANCONNECT (OBLIGATORIAS):\n"
        "1. Eres Mathew, asistente clínico virtual de FarmaConnect. NO eres médico.\n"
        "2. Responde ÚNICAMENTE dudas de salud humana (malestares o síntomas comunes).\n"
        "3. No sugieras medicamentos por iniciativa propia. Usa solo medidas físicas leves.\n"
        "4. PROTOCOLO DE TABLA: SÓLO si recibes 'DATOS REALES EXTRAÍDOS', construye una tabla Markdown:\n"
        "   ### 📊 Precios registrados en Chile\n"
        "   | Farmacia | Producto Encontrado | Precio Registrado (CLP) |\n"
        "   | :--- | :--- | :--- |\n"
        "   Luego indica cuál farmacia es más barata.\n"
        "5. Explica brevemente para qué sirve el fármaco. Incluye SIEMPRE advertencia de consultar médico."
    )

    try:
        if archivo_base64:
            contenido = [
                {"type": "text", "text": f"{reglas}\n\nContexto: {contexto_precios}\n\nConsulta: {pregunta}"},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{archivo_base64}"}}
            ]
            completion = client.chat.completions.create(
                model="llama-3.2-90b-vision-preview",
                messages=[{"role": "user", "content": contenido}]
            )
        else:
            completion = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[
                    {"role": "system", "content": reglas},
                    {"role": "user", "content": f"Contexto DB: {contexto_precios}\n\nConsulta: {pregunta}"}
                ]
            )
        return jsonify({"respuesta": completion.choices[0].message.content})
    except Exception as e:
        print(f"Error Groq: {e}")
        return jsonify({"respuesta": "Mathew está experimentando problemas técnicos temporales."}), 500


if __name__ == '__main__':
    app.run(debug=True, port=8000)