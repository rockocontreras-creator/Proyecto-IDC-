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
import hmac
import secrets
import time
import json
import os
import re
import urllib.request
import urllib.parse
from groq import Groq

app = Flask(__name__)
# CORS abierto para desarrollo local — acepta cualquier origen
CORS(app, resources={r"/*": {"origins": "*"}})

client = Groq(api_key="")

APP_SECRET = 'farmaconnect_dev_secret_2024'

# =========================================================
# CONFIGURACIÓN DE SCRAPING
# Pon HEADLESS = False para ver las ventanas de Chrome (útil para depurar
# y para saltarse anti-bots agresivos como el de Salcobrand).
# =========================================================
HEADLESS = True

# =========================================================
# TOKENS EN MEMORIA (reemplaza flask.session — sin cookies)
# =========================================================
# TOKENS STATELESS (HMAC) — sobreviven reinicios del servidor
# El token codifica el user_id firmado con HMAC-SHA256.
# Al verificar, se valida la firma y se busca el usuario en la BD.
# =========================================================

def crear_token(user_id: int, nombre: str, correo: str, es_admin: int = 0) -> str:
    payload = str(user_id)
    sig = hmac.new(APP_SECRET.encode(), payload.encode(), 'sha256').hexdigest()[:40]
    return f"{payload}:{sig}"

def resolver_token() -> dict | None:
    """Lee el header Authorization: Bearer <uid:firma> y verifica contra la BD."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth[7:]
    if ':' not in token:
        return None
    parts = token.split(":", 1)
    uid_str, sig = parts
    # Verificar firma HMAC
    expected = hmac.new(APP_SECRET.encode(), uid_str.encode(), 'sha256').hexdigest()[:40]
    if not hmac.compare_digest(sig, expected):
        return None
    # Buscar usuario en la BD
    try:
        conn = sqlite3.connect('farmacia.db')
        c = conn.cursor()
        c.execute("SELECT id_usuario, nombre, correo, es_admin FROM usuarios WHERE id_usuario = ?", (int(uid_str),))
        row = c.fetchone()
        conn.close()
        if not row:
            return None
        return {"id": row[0], "nombre": row[1], "correo": row[2], "es_admin": bool(row[3])}
    except Exception:
        return None

def resolver_admin() -> dict | None:
    u = resolver_token()
    if u and u.get("es_admin"):
        return u
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
                        contraseña TEXT NOT NULL,
                        es_admin INTEGER DEFAULT 0)''')
    # Migración: si la tabla 'usuarios' ya existía sin la columna es_admin, la añadimos
    try:
        cursor.execute("ALTER TABLE usuarios ADD COLUMN es_admin INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass  # la columna ya existe
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
    farmacias_data = [
        (1, 'Ahumada', '#003399'),
        (2, 'Dr. Simi', '#ce000c'),
        (3, 'Salcobrand', '#ffd400'),
        (4, 'Cruz Verde', '#009639'),
    ]
    cursor.executemany("INSERT OR IGNORE INTO farmacias (id_farmacias, nombre_farmacia, color_distintivo) VALUES (?,?,?)", farmacias_data)

    # 5. Tabla de historial de chat
    cursor.execute('''CREATE TABLE IF NOT EXISTS chat_historial (
                        id_chat INTEGER PRIMARY KEY AUTOINCREMENT,
                        id_usuario INTEGER NOT NULL,
                        rol TEXT NOT NULL,
                        mensaje TEXT NOT NULL,
                        fecha DATETIME DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY(id_usuario) REFERENCES usuarios(id_usuario) ON DELETE CASCADE)''')

    # 6. Tabla de alertas de precio
    cursor.execute('''CREATE TABLE IF NOT EXISTS alertas_precio (
                        id_alerta INTEGER PRIMARY KEY AUTOINCREMENT,
                        id_usuario INTEGER NOT NULL,
                        medicamento TEXT NOT NULL,
                        umbral_precio INTEGER NOT NULL,
                        activa INTEGER DEFAULT 1,
                        fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY(id_usuario) REFERENCES usuarios(id_usuario) ON DELETE CASCADE)''')

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
        token = crear_token(user_id, nombre, correo, 0)
        return jsonify({
            "mensaje": "Cuenta creada con éxito.",
            "token": token,
            "usuario": {"id": user_id, "nombre": nombre, "correo": correo, "es_admin": False}
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
    cursor.execute("SELECT id_usuario, nombre, correo, es_admin FROM usuarios WHERE correo = ? AND contraseña = ?",
                   (correo, hash_password(password)))
    usuario = cursor.fetchone()
    conn.close()

    if not usuario:
        return jsonify({"error": "Correo o contraseña incorrectos."}), 401

    token = crear_token(usuario[0], usuario[1], usuario[2], usuario[3])
    return jsonify({
        "mensaje": "Sesión iniciada.",
        "token": token,
        "usuario": {"id": usuario[0], "nombre": usuario[1], "correo": usuario[2], "es_admin": bool(usuario[3])}
    })


@app.route('/logout', methods=['POST'])
def logout():
    # Token es stateless — solo el frontend necesita borrarlo de localStorage
    return jsonify({"mensaje": "Sesión cerrada."})


@app.route('/me', methods=['GET'])
def me():
    usuario = resolver_token()
    if usuario:
        return jsonify({"autenticado": True, "usuario": usuario})
    return jsonify({"autenticado": False}), 401


# =========================================================
# PANEL DE ADMINISTRADOR (todos los endpoints requieren admin)
# =========================================================

@app.route('/admin/stats', methods=['GET'])
def admin_stats():
    if not resolver_admin():
        return jsonify({"error": "Acceso denegado. Se requieren permisos de administrador."}), 403
    conn = sqlite3.connect('farmacia.db')
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM usuarios");      total_usuarios = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM usuarios WHERE es_admin = 1"); total_admins = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM medicamentos");  total_meds = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM historial");     total_hist = c.fetchone()[0]
    conn.close()
    return jsonify({
        "usuarios": total_usuarios,
        "admins": total_admins,
        "medicamentos": total_meds,
        "busquedas": total_hist
    })


@app.route('/admin/usuarios', methods=['GET'])
def admin_listar_usuarios():
    if not resolver_admin():
        return jsonify({"error": "Acceso denegado."}), 403
    conn = sqlite3.connect('farmacia.db')
    c = conn.cursor()
    c.execute("SELECT id_usuario, nombre, correo, es_admin FROM usuarios ORDER BY id_usuario ASC")
    usuarios = [{"id": r[0], "nombre": r[1], "correo": r[2], "es_admin": bool(r[3])} for r in c.fetchall()]
    conn.close()
    return jsonify(usuarios)


@app.route('/admin/usuarios/<int:uid>', methods=['PUT'])
def admin_editar_usuario(uid):
    admin = resolver_admin()
    if not admin:
        return jsonify({"error": "Acceso denegado."}), 403
    data = request.json
    nombre   = data.get('nombre', '').strip()
    correo   = data.get('correo', '').strip().lower()
    es_admin = 1 if data.get('es_admin') else 0
    password = data.get('password', '')  # opcional

    if not nombre or not correo:
        return jsonify({"error": "Nombre y correo son obligatorios."}), 400

    # Evita que un admin se quite a sí mismo el último acceso de administrador
    if admin['id'] == uid and es_admin == 0:
        conn = sqlite3.connect('farmacia.db'); c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM usuarios WHERE es_admin = 1"); n = c.fetchone()[0]; conn.close()
        if n <= 1:
            return jsonify({"error": "No puedes quitarte el rol de admin siendo el único administrador."}), 400

    conn = sqlite3.connect('farmacia.db')
    c = conn.cursor()
    try:
        if password:
            if len(password) < 6:
                return jsonify({"error": "La contraseña debe tener al menos 6 caracteres."}), 400
            c.execute("UPDATE usuarios SET nombre=?, correo=?, es_admin=?, contraseña=? WHERE id_usuario=?",
                      (nombre, correo, es_admin, hash_password(password), uid))
        else:
            c.execute("UPDATE usuarios SET nombre=?, correo=?, es_admin=? WHERE id_usuario=?",
                      (nombre, correo, es_admin, uid))
        conn.commit()
        # Tokens son stateless — la próxima verificación leerá los datos actualizados de la BD
        return jsonify({"mensaje": "Usuario actualizado."})
    except sqlite3.IntegrityError:
        return jsonify({"error": "Ese correo ya está en uso por otro usuario."}), 409
    finally:
        conn.close()


@app.route('/admin/usuarios/<int:uid>', methods=['DELETE'])
def admin_eliminar_usuario(uid):
    admin = resolver_admin()
    if not admin:
        return jsonify({"error": "Acceso denegado."}), 403
    if admin['id'] == uid:
        return jsonify({"error": "No puedes eliminar tu propia cuenta."}), 400
    conn = sqlite3.connect('farmacia.db')
    c = conn.cursor()
    c.execute("DELETE FROM usuarios WHERE id_usuario=?", (uid,))
    conn.commit()
    conn.close()
    return jsonify({"mensaje": "Usuario eliminado."})


@app.route('/admin/historial', methods=['GET'])
def admin_listar_historial():
    if not resolver_admin():
        return jsonify({"error": "Acceso denegado."}), 403
    conn = sqlite3.connect('farmacia.db')
    c = conn.cursor()
    c.execute('''SELECT h.id_historial, m.nombre_buscado, f.nombre_farmacia, h.nombre_especifico,
                        h.precio, h.fecha_registro, COALESCE(u.nombre, 'Anónimo')
                 FROM historial h
                 JOIN farmacias f ON h.id_farmacia = f.id_farmacias
                 JOIN medicamentos m ON h.id_medicamento = m.id_medicamento
                 LEFT JOIN usuarios u ON h.id_usuario = u.id_usuario
                 ORDER BY h.fecha_registro DESC LIMIT 200''')
    rows = [{"id": r[0], "buscado": r[1], "farmacia": r[2], "producto": r[3],
             "precio": r[4], "fecha": r[5], "usuario": r[6]} for r in c.fetchall()]
    conn.close()
    return jsonify(rows)


@app.route('/admin/historial/<int:hid>', methods=['DELETE'])
def admin_eliminar_historial(hid):
    if not resolver_admin():
        return jsonify({"error": "Acceso denegado."}), 403
    conn = sqlite3.connect('farmacia.db')
    c = conn.cursor()
    c.execute("DELETE FROM historial WHERE id_historial=?", (hid,))
    conn.commit()
    conn.close()
    return jsonify({"mensaje": "Registro eliminado."})


@app.route('/admin/medicamentos', methods=['GET'])
def admin_listar_medicamentos():
    if not resolver_admin():
        return jsonify({"error": "Acceso denegado."}), 403
    conn = sqlite3.connect('farmacia.db')
    c = conn.cursor()
    c.execute('''SELECT m.id_medicamento, m.nombre_buscado, COUNT(h.id_historial)
                 FROM medicamentos m
                 LEFT JOIN historial h ON h.id_medicamento = m.id_medicamento
                 GROUP BY m.id_medicamento ORDER BY m.nombre_buscado ASC''')
    rows = [{"id": r[0], "nombre": r[1], "busquedas": r[2]} for r in c.fetchall()]
    conn.close()
    return jsonify(rows)


@app.route('/admin/medicamentos/<int:mid>', methods=['DELETE'])
def admin_eliminar_medicamento(mid):
    if not resolver_admin():
        return jsonify({"error": "Acceso denegado."}), 403
    conn = sqlite3.connect('farmacia.db')
    c = conn.cursor()
    c.execute("DELETE FROM historial WHERE id_medicamento=?", (mid,))   # borra su historial asociado
    c.execute("DELETE FROM medicamentos WHERE id_medicamento=?", (mid,))
    conn.commit()
    conn.close()
    return jsonify({"mensaje": "Medicamento y su historial eliminados."})


# =========================================================
# IDENTIFICADOR DE PASTILLAS (Groq Vision)
# =========================================================

@app.route('/identificar_pastilla', methods=['POST'])
def identificar_pastilla():
    data = request.json
    # Acepta una sola imagen o una lista de hasta 2 imágenes
    imagenes = data.get('imagenes_base64', [])
    if not imagenes:
        img_unica = data.get('imagen_base64')
        if img_unica:
            imagenes = [img_unica]
    if not imagenes:
        return jsonify({"error": "Debes enviar al menos una imagen de la pastilla."}), 400
    if len(imagenes) > 2:
        imagenes = imagenes[:2]

    multi = len(imagenes) > 1
    prompt = (
        "Eres un experto farmacéutico chileno con amplio conocimiento en identificación visual de medicamentos. "
        f"Analiza {'estas imágenes' if multi else 'esta imagen'} de una pastilla, comprimido, cápsula o medicamento. "
        f"{'Las fotos pueden mostrar la misma pastilla desde distintos ángulos (anverso/reverso). Usa ambas para mejorar la identificación. ' if multi else ''}"
        "Identifica el medicamento basándote en su forma, color, tamaño, grabados, letras, números o marcas visibles.\n\n"
        "Responde ÚNICAMENTE con un objeto JSON válido (sin bloques de código, sin texto adicional) con estos campos:\n"
        '{\n'
        '  "nombre": "Nombre comercial más probable del medicamento",\n'
        '  "principio_activo": "Principio activo / molécula",\n'
        '  "descripcion": "Breve descripción de para qué se usa (2-3 líneas)",\n'
        '  "forma": "Comprimido / Cápsula / Tableta / Gragea / etc",\n'
        '  "color": "Color observado",\n'
        '  "grabado": "Texto o marcas visibles en la pastilla (o N/A)",\n'
        '  "laboratorio": "Laboratorio fabricante probable (o Desconocido)",\n'
        '  "confianza": "alta / media / baja",\n'
        '  "buscar": "Término óptimo para buscar este medicamento en farmacias chilenas (ej: paracetamol 500mg)",\n'
        '  "advertencia": "Alguna precaución importante (interacciones, contraindicaciones comunes)"\n'
        '}\n\n'
        "Si NO puedes identificar el medicamento con certeza, responde igualmente con el JSON "
        "poniendo confianza 'baja' y en nombre pon tu mejor estimación o 'No identificado'. "
        "NUNCA respondas fuera del formato JSON."
    )

    respuesta_cruda = ""
    try:
        contenido = [{"type": "text", "text": prompt}]
        for img_b64 in imagenes:
            contenido.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}})

        completion = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[{"role": "user", "content": contenido}],
            temperature=0.2
        )
        respuesta_cruda = completion.choices[0].message.content.strip()

        # Limpiar posibles fences de markdown (```json ... ```)
        if respuesta_cruda.startswith("```"):
            respuesta_cruda = respuesta_cruda.split("```")[1]
            if respuesta_cruda.startswith("json"):
                respuesta_cruda = respuesta_cruda[4:]
            respuesta_cruda = respuesta_cruda.strip()

        resultado = json.loads(respuesta_cruda)
        return jsonify({"resultado": resultado})

    except json.JSONDecodeError:
        return jsonify({"resultado": {
            "nombre": "No se pudo procesar",
            "descripcion": respuesta_cruda[:500] if respuesta_cruda else "Error al analizar la imagen.",
            "confianza": "baja",
            "buscar": ""
        }})
    except Exception as e:
        print(f"Error en identificación de pastilla: {e}")
        return jsonify({"error": f"Error al procesar la imagen: {str(e)[:200]}"}), 500


@app.route('/extraer_receta', methods=['POST'])
def extraer_receta():
    """Extrae los nombres de medicamentos de una foto de receta médica."""
    data = request.json
    imagen = data.get('imagen_base64')
    if not imagen:
        return jsonify({"error": "Debes enviar una imagen de la receta."}), 400

    prompt = (
        "Eres un farmacéutico experto chileno. Analiza esta imagen de una receta médica. "
        "Extrae TODOS los medicamentos mencionados en la receta. "
        "Responde ÚNICAMENTE con un JSON válido (sin markdown, sin texto extra) con este formato:\n"
        '{"medicamentos": [\n'
        '  {"nombre": "nombre del medicamento tal como aparece", "buscar": "término óptimo para buscar en farmacias chilenas (nombre genérico + dosis si está visible)"},\n'
        '  ...\n'
        ']}\n\n'
        "Si no puedes leer la receta o no encuentras medicamentos, devuelve {\"medicamentos\": []}. "
        "NUNCA respondas fuera del formato JSON."
    )

    try:
        contenido = [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{imagen}"}}
        ]
        completion = client.chat.completions.create(
            model="meta-llama/llama-4-scout-17b-16e-instruct",
            messages=[{"role": "user", "content": contenido}],
            temperature=0.1
        )
        respuesta = completion.choices[0].message.content.strip()
        if respuesta.startswith("```"):
            respuesta = respuesta.split("```")[1]
            if respuesta.startswith("json"):
                respuesta = respuesta[4:]
            respuesta = respuesta.strip()
        resultado = json.loads(respuesta)
        return jsonify(resultado)
    except json.JSONDecodeError:
        return jsonify({"medicamentos": [], "error": "No se pudo interpretar la receta."})
    except Exception as e:
        print(f"Error extrayendo receta: {e}")
        return jsonify({"error": str(e)[:200]}), 500


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

                # Formatear también el precio original (tachado) si viene en oferta
                if r.get('precio_original'):
                    orig_limpio = "".join(filter(str.isdigit, str(r['precio_original'])))
                    if orig_limpio:
                        r['precio_original'] = f"{int(orig_limpio):,}".replace(",", ".")
                    else:
                        r['precio_original'] = None
                        r['oferta'] = False

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
    if HEADLESS:
        opts.add_argument("--headless")           # headless clásico (el que funcionaba con 3 farmacias)
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-extensions")
    opts.add_argument("--blink-settings=imagesEnabled=false")
    opts.add_argument("--window-size=1280,800")
    # Anti-detección (no interfiere con la carga; solo ayuda con anti-bots)
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
    prefs = {"profile.managed_default_content_settings.images": 2}
    opts.add_experimental_option("prefs", prefs)
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    service = Service(ChromeDriverManager().install(), log_output=os.devnull)
    driver = webdriver.Chrome(service=service, options=opts)
    driver.set_page_load_timeout(20)   # restaurado al valor original (20s)
    try:
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        })
    except Exception:
        pass
    return driver


def scrape_task(func, remedio, res_list):
    """Ejecuta el scraper de una farmacia. Si no devuelve nada, reintenta UNA vez
       (las SPAs anti-bot a veces fallan la primera carga y funcionan en la segunda)."""
    nombre_farmacia = func.__name__.replace("logic_", "").capitalize()
    antes = len(res_list)
    for intento in (1, 2):
        driver = None
        try:
            driver = get_driver()
            func(remedio, driver, res_list)
        except Exception as e:
            print(f"Error en hilo de raspado ({nombre_farmacia}, intento {intento}): {e}")
        finally:
            if driver:
                try: driver.quit()
                except Exception: pass
        if len(res_list) > antes:   # ya obtuvo resultado → no reintentar
            break


def _cargar(driver, url):
    """Navega a la URL; si supera el page_load_timeout corta la carga y sigue
       con lo que ya esté en el DOM (las farmacias son SPAs muy pesadas)."""
    try:
        driver.get(url)
    except Exception:
        driver.execute_script("window.stop();")


# Extractor genérico LIVIANO: busca solo entre elementos con clase tipo 'price'/'precio'
# (conjunto acotado) para no congelar el renderer en páginas pesadas.
_JS_EXTRACTOR_GENERICO = r"""
    const priceRe = /\$\s?\d{1,3}(?:[.,]\d{3})+/;
    const parse = t => parseInt(String(t).replace(/\D/g, ''), 10) || 0;

    // Conjunto ACOTADO de posibles nodos de precio (no recorremos todo el DOM)
    let priceEls = Array.from(
        document.querySelectorAll("[class*='price'],[class*='Price'],[class*='precio'],[class*='Precio'],[class*='amount']")
    ).filter(el => {
        const t = (el.innerText || '').trim();
        return priceRe.test(t) && parse(t.match(priceRe)[0]) >= 100;
    });
    if (priceEls.length === 0) return null;

    // Subir hasta un contenedor que tenga un enlace
    function contenedor(node) {
        let cur = node;
        for (let i = 0; i < 6 && cur; i++) {
            if (cur.querySelector && cur.querySelector('a[href]')) return cur;
            cur = cur.parentElement;
        }
        return node.parentElement || node;
    }

    // Ordenar por precio ascendente y tomar el primero válido
    let items = priceEls.map(el => ({ el, val: parse((el.innerText.match(priceRe) || ['0'])[0]) }))
                        .filter(x => x.val > 0)
                        .sort((a, b) => a.val - b.val);

    for (const it of items) {
        const cont = contenedor(it.el);
        const link = cont.querySelector('a[href]');
        if (!link) continue;

        // Nombre: título del enlace, su texto, o el texto más largo no-precio del contenedor (acotado a hijos directos-ish)
        let nombre = (link.getAttribute('title') || '').trim();
        if (!nombre) nombre = (link.innerText || '').trim().split('\n')[0];
        if (!nombre) {
            const cand = Array.from(cont.querySelectorAll('h2,h3,h4,[class*="name"],[class*="Name"],[class*="title"],[class*="brand"]'))
                .map(n => (n.innerText || '').trim())
                .filter(t => t && !priceRe.test(t) && t.length < 120)
                .sort((a, b) => b.length - a.length);
            if (cand.length) nombre = cand[0];
        }
        if (!nombre || nombre.length > 140) continue;

        // Precio original (oferta): un precio MAYOR dentro del mismo contenedor
        let original = null;
        cont.querySelectorAll("[class*='price'],[class*='Price'],s,del,strike").forEach(n => {
            const m = (n.innerText || '').trim().match(priceRe);
            if (m && parse(m[0]) > it.val) {
                if (!original || parse(m[0]) > parse(original)) original = m[0];
            }
        });

        return { n: nombre, pr: '$' + it.val.toLocaleString('es-CL'), l: link.href, orig: original };
    }
    return null;
"""


def _extraer_generico(driver):
    try:
        return driver.execute_script("return (function(){" + _JS_EXTRACTOR_GENERICO + "})();")
    except Exception:
        return None




def _agregar_resultados(items, farmacia, color, res):
    """Procesa items extraídos (dict o lista) y los agrega a res."""
    if not items:
        return
    if isinstance(items, dict):
        items = [items]
    for d in items:
        if d and d.get('n') and d.get('pr'):
            res.append({
                "farmacia": farmacia, "nombre": d['n'], "precio": d['pr'], "link": d.get('l', ''),
                "color": color,
                "oferta": bool(d.get('orig')),
                "precio_original": d.get('orig')
            })


def logic_ahumada(remedio, driver, res):
    try:
        driver.get(f"https://www.farmaciasahumada.cl/search?q={remedio}&srule=price-low-to-high&sz=4")
        WebDriverWait(driver, 8).until(EC.presence_of_element_located((By.CLASS_NAME, "price")))
        items = driver.execute_script("""
            let tiles = document.querySelectorAll('.product-tile, .grid-tile, .product');
            let results = [];
            tiles.forEach((tile, i) => {
                if (i >= 3) return;
                let nom = tile.querySelector('.pdp-link');
                let priceWrap = tile.querySelector('.price');
                if (!nom || !priceWrap) return;
                let link = nom.querySelector('a');
                let salesEl = priceWrap.querySelector('.sales .value, .sales');
                let strikeEl = priceWrap.querySelector('.strike-through .value, .strike-through, del');
                let actual = salesEl ? salesEl.innerText.trim() : priceWrap.innerText.split('\\n')[0].trim();
                let orig = strikeEl ? strikeEl.innerText.trim() : null;
                if (actual) results.push({ n: nom.innerText.trim(), pr: actual, l: link ? link.href : window.location.href, orig: orig });
            });
            return results.length > 0 ? results : null;
        """)
        if items:
            _agregar_resultados(items, "Ahumada", "#003399", res)
        else:
            _agregar_resultados(_extraer_generico(driver), "Ahumada", "#003399", res)
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
        items = driver.execute_script("""
            let cards = document.querySelectorAll('[class*="productSummary"], [class*="product-summary"], article');
            let results = [];
            cards.forEach((card, i) => {
                if (i >= 3) return;
                let nom = card.querySelector('[class*="brandName"], [class*="productBrand"]');
                let sell = card.querySelector('[class*="sellingPrice"], [class*="currencyContainer"]');
                let list = card.querySelector('[class*="listPrice"]');
                let link = card.querySelector('a[class*="clearLink"], a');
                if (!nom || !sell) return;
                let actual = sell.innerText.trim();
                let orig = list ? list.innerText.trim() : null;
                let esOferta = orig && orig.replace(/\\D/g,'') !== actual.replace(/\\D/g,'') && orig.replace(/\\D/g,'') !== '';
                results.push({ n: nom.innerText.trim(), pr: actual, l: link ? link.href : window.location.href, orig: esOferta ? orig : null });
            });
            return results.length > 0 ? results : null;
        """)
        if items:
            _agregar_resultados(items, "Dr. Simi", "#ce000c", res)
        else:
            _agregar_resultados(_extraer_generico(driver), "Dr. Simi", "#ce000c", res)
    except Exception as e:
        print(f"Error Dr. Simi: {e}")


def logic_salcobrand(remedio, driver, res):
    try:
        driver.get(f"https://salcobrand.cl/search_result?query={remedio}&sort=price_asc")
        try:
            WebDriverWait(driver, 12).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".product, .product-info, .product-card"))
            )
        except Exception:
            pass
        time.sleep(1.5)
        items = driver.execute_script("""
            let products = document.querySelectorAll('.product');
            let results = [];
            products.forEach((prod, i) => {
                if (i >= 3) return;
                let info = prod.querySelector('.product-info') || prod.querySelector('.product-card') || prod;
                let priceEl = prod.querySelector('.price:not(.old-price)') || prod.querySelector('.price') || prod.querySelector('[class*="price"]');
                let oldEl = prod.querySelector('.old-price');
                let linkEl = prod.querySelector('a');
                if (!priceEl || !linkEl) return;
                let orig = oldEl ? oldEl.innerText.trim() : null;
                results.push({ n: info.innerText.split('\\n')[0].trim(), pr: priceEl.innerText.trim(), l: linkEl.href, orig: (orig && orig.replace(/\\D/g,'') !== '') ? orig : null });
            });
            return results.length > 0 ? results : null;
        """)
        if items:
            _agregar_resultados(items, "Salcobrand", "#ffd400", res)
        else:
            _agregar_resultados(_extraer_generico(driver), "Salcobrand", "#ffd400", res)
    except Exception as e:
        print(f"Error Salcobrand: {e}")


def logic_cruzverde(remedio, res):
    """Cruz Verde via SSR (Googlebot). El sitio sirve HTML pre-renderizado para crawlers."""
    query = urllib.parse.quote(remedio)

    try:
        req = urllib.request.Request(
            f"https://www.cruzverde.cl/search?query={query}",
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
                "Accept": "text/html",
                "Accept-Language": "es-CL,es;q=0.9",
            }
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode('utf-8', errors='ignore')

        if len(html) < 5000:
            print(f"Cruz Verde SSR: solo {len(html)} chars, sin contenido.")
            return

        productos = []

        # =============================================
        # Estrategia 1: Buscar JSON-LD (schema.org Product)
        # =============================================
        ld_blocks = re.findall(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, re.DOTALL)
        for ld in ld_blocks:
            try:
                ld_data = json.loads(ld)
                items = []
                if isinstance(ld_data, list):
                    items = ld_data
                elif isinstance(ld_data, dict):
                    if ld_data.get('@type') == 'Product':
                        items = [ld_data]
                    elif 'itemListElement' in ld_data:
                        items = [i.get('item', i) for i in ld_data['itemListElement']]
                for item in items[:3]:
                    nombre = item.get('name', '')
                    offers = item.get('offers', {})
                    if isinstance(offers, list):
                        offers = offers[0] if offers else {}
                    precio = offers.get('price', 0)
                    link = item.get('url', '')
                    if nombre and precio:
                        productos.append({
                            "farmacia": "Cruz Verde", "nombre": nombre,
                            "precio": f"{int(float(precio)):,}".replace(",", "."),
                            "link": link or f"https://www.cruzverde.cl/search?query={query}",
                            "color": "#009639", "oferta": False, "precio_original": None
                        })
            except (json.JSONDecodeError, ValueError):
                continue

        if productos:
            res.extend(productos[:3])
            print(f"Cruz Verde JSON-LD: {len(productos[:3])} producto(s)")
            return

        # =============================================
        # Estrategia 2: Buscar estado Angular/JS embebido
        # =============================================
        state_match = re.search(r'window\.__(?:STATE|INITIAL_STATE|APP_STATE|PRELOADED)__\s*=\s*(\{.*?\});?\s*</script>', html, re.DOTALL)
        if state_match:
            try:
                state = json.loads(state_match.group(1))
                print(f"Cruz Verde: Estado Angular encontrado, claves: {list(state.keys())[:8]}")
            except json.JSONDecodeError:
                pass

        # =============================================
        # Estrategia 3: Regex en HTML pre-renderizado
        # Filtrar SVG y buscar solo productos reales
        # =============================================
        # Eliminar todos los bloques SVG del HTML para no matchear sus atributos
        html_sin_svg = re.sub(r'<svg[^>]*>.*?</svg>', '', html, flags=re.DOTALL)
        html_sin_svg = re.sub(r'<style[^>]*>.*?</style>', '', html_sin_svg, flags=re.DOTALL)

        # Buscar precios CLP: $ X.XXX o $X.XXX (con o sin punto de miles)
        precios = re.findall(r'\$\s?([\d]+(?:\.[\d]{3})*)', html_sin_svg)
        precios = [p for p in precios if int(p.replace('.', '')) >= 100]  # filtrar precios < $100

        # Buscar enlaces a productos (.html con slug)
        links = re.findall(r'href=["\'](/[a-z0-9][a-z0-9\-]+/\d+\.html)["\']', html_sin_svg)
        links = list(dict.fromkeys(links))  # dedup manteniendo orden

        # Buscar nombres de producto: textos sustanciales cerca de precios
        # Los nombres suelen estar en elementos con clases product-name, title, o como texto de enlaces
        nombres = re.findall(
            r'(?:class=["\'][^"\']*(?:product-name|productName|product-title|name)[^"\']*["\'][^>]*>|'
            r'<h[23][^>]*>|<a[^>]*title=["\'])([^<"\']{10,100})',
            html_sin_svg
        )
        # Filtrar nombres que no son productos
        nombres_filtrados = []
        blacklist = ['cruz verde', 'buscar', 'cerrar', 'iniciar', 'menú', 'filtrar',
                     'ordenar', 'home', 'logo', 'group', 'rectangle', 'path', 'svg',
                     'cookie', 'suscri', 'despacho', 'retiro', 'bolsa', 'registro']
        for n in nombres:
            n_clean = n.strip()
            if len(n_clean) < 8:
                continue
            if any(bl in n_clean.lower() for bl in blacklist):
                continue
            if n_clean not in nombres_filtrados:
                nombres_filtrados.append(n_clean)

        # Emparejar: nombre + precio + link
        for i in range(min(3, max(len(precios), len(links), len(nombres_filtrados)))):
            nombre = nombres_filtrados[i] if i < len(nombres_filtrados) else f"Producto Cruz Verde"
            precio = precios[i] if i < len(precios) else None
            link = f"https://www.cruzverde.cl{links[i]}" if i < len(links) else f"https://www.cruzverde.cl/search?query={query}"

            if not precio:
                continue

            # Detectar oferta: si hay un precio mayor justo después
            precio_original = None
            if i * 2 + 1 < len(precios):
                val_actual = int(precios[i].replace('.', ''))
                val_orig = int(precios[i * 2 + 1].replace('.', '')) if i * 2 + 1 < len(precios) else 0
                if val_orig > val_actual:
                    precio_original = precios[i * 2 + 1]

            productos.append({
                "farmacia": "Cruz Verde", "nombre": nombre, "precio": precio,
                "link": link, "color": "#009639",
                "oferta": bool(precio_original),
                "precio_original": precio_original
            })

        if productos:
            res.extend(productos)
            print(f"Cruz Verde SSR regex: {len(productos)} producto(s)")
        else:
            # Debug: qué encontró cada regex
            print(f"Cruz Verde SSR: {len(html)} chars, {len(precios)} precios, {len(links)} links, {len(nombres_filtrados)} nombres")
            print(f"  Precios: {precios[:5]}")
            print(f"  Links: {links[:3]}")
            print(f"  Nombres: {nombres_filtrados[:5]}")

    except Exception as e:
        print(f"Error Cruz Verde: {e}")


def _parsear_cruzverde_json(data, remedio):
    """Parsea respuesta JSON de OCAPI/SCAPI de Cruz Verde."""
    productos = []
    
    # OCAPI format: { "hits": [{ "product_id", "product_name", "price", ... }] }
    hits = data.get('hits') or data.get('results') or data.get('products') or data.get('data', {}).get('products', [])
    if not hits and isinstance(data, list):
        hits = data

    if not hits:
        # Buscar en sugerencias
        sugs = data.get('suggestions') or data.get('products', {}).get('suggestions', [])
        if sugs:
            hits = sugs

    for item in (hits or [])[:3]:
        nombre = item.get('product_name') or item.get('name') or item.get('productName') or item.get('title') or ''
        precio = item.get('price') or item.get('prices', {}).get('sale') or item.get('salePrice') or 0
        precio_orig = item.get('list_price') or item.get('prices', {}).get('list') or item.get('listPrice') or 0
        prod_id = item.get('product_id') or item.get('id') or item.get('productId') or ''
        link = item.get('link') or item.get('url') or item.get('productUrl') or ''
        
        if not link and prod_id:
            slug = nombre.lower().replace(' ', '-').replace('.', '') if nombre else remedio
            link = f"https://www.cruzverde.cl/{slug}/{prod_id}.html"
        if link and not link.startswith('http'):
            link = 'https://www.cruzverde.cl' + link

        if nombre and precio:
            if isinstance(precio, (int, float)):
                precio_str = f"${int(precio):,}".replace(",", ".")
            else:
                precio_str = str(precio)

            oferta = False
            precio_original_str = None
            if precio_orig and float(precio_orig) > float(precio):
                oferta = True
                if isinstance(precio_orig, (int, float)):
                    precio_original_str = f"${int(precio_orig):,}".replace(",", ".")

            productos.append({
                "farmacia": "Cruz Verde", "nombre": nombre, "precio": precio_str,
                "link": link, "color": "#009639",
                "oferta": oferta, "precio_original": precio_original_str
            })
    return productos


def _parsear_cruzverde_html(body, remedio):
    """Parsea HTML de Search-Show/UpdateGrid de Cruz Verde."""
    productos = []
    price_re = re.compile(r'\$\s?([\d.,]+)')

    # Buscar product tiles
    links = re.findall(r'href=["\']([^"\']*?\.html)["\']', body)
    product_links = [('https://www.cruzverde.cl' + l if l.startswith('/') else l)
                     for l in links if '.html' in l and '/search' not in l]
    product_links = list(dict.fromkeys(product_links))[:3]

    names = re.findall(r'(?:title|data-name|aria-label|alt)=["\']([^"\']{8,100})["\']', body)
    names = [n for n in names if len(n) > 5 and not any(x in n for x in ['Cruz Verde', 'Buscar', 'Cerrar', 'Iniciar', 'Google'])]
    names = list(dict.fromkeys(names))

    prices = price_re.findall(body)

    for i in range(min(3, max(len(product_links), len(names)))):
        nombre = names[i] if i < len(names) else f"Producto Cruz Verde"
        link = product_links[i] if i < len(product_links) else f"https://www.cruzverde.cl/search?q={urllib.parse.quote(remedio)}"
        precio = prices[i] if i < len(prices) else None
        if not precio:
            continue
        productos.append({
            "farmacia": "Cruz Verde", "nombre": nombre, "precio": f"${precio}",
            "link": link, "color": "#009639", "oferta": False, "precio_original": None
        })
    return productos


@app.route('/bioequivalente', methods=['POST'])
def bioequivalente():
    """Usa el LLM para identificar el principio activo de un medicamento y sugerir búsquedas genéricas."""
    data = request.json
    nombre = data.get('nombre', '').strip()
    if not nombre:
        return jsonify({"error": "Falta el nombre del medicamento."}), 400

    try:
        completion = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {"role": "system", "content": (
                    "Eres un farmacéutico experto chileno. El usuario te da el nombre de un medicamento. "
                    "Responde SOLO con un JSON válido (sin markdown, sin texto extra) con estos campos:\n"
                    '{"principio_activo": "nombre del principio activo/molécula", '
                    '"dosis_comun": "dosis más común (ej: 500mg)", '
                    '"buscar": "término genérico para buscar en farmacias chilenas (ej: paracetamol 500mg)", '
                    '"es_generico": true/false, '
                    '"alternativas": ["nombre genérico 1", "nombre genérico 2"]}'
                )},
                {"role": "user", "content": f"Medicamento: {nombre}"}
            ],
            temperature=0.1
        )
        respuesta = completion.choices[0].message.content.strip()
        if respuesta.startswith("```"):
            respuesta = respuesta.split("```")[1]
            if respuesta.startswith("json"):
                respuesta = respuesta[4:]
            respuesta = respuesta.strip()
        resultado = json.loads(respuesta)
        return jsonify(resultado)
    except Exception as e:
        print(f"Error bioequivalente: {e}")
        return jsonify({"error": "No se pudo analizar el medicamento."}), 500


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
        threading.Thread(target=scrape_task, args=(logic_salcobrand, remedio, res)),
        # Cruz Verde usa HTTP directo (no Selenium) — no necesita scrape_task con Chrome
        threading.Thread(target=logic_cruzverde, args=(remedio, res))
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


# =========================================================
# MEDICAMENTOS POPULARES (para la página de inicio)
# =========================================================

@app.route('/medicamentos_populares', methods=['GET'])
def medicamentos_populares():
    """Devuelve los medicamentos más buscados con el precio más bajo registrado por farmacia."""
    conn = sqlite3.connect('farmacia.db')
    c = conn.cursor()
    # Top 10 medicamentos más buscados (por cantidad de registros en historial)
    c.execute('''
        SELECT m.nombre_buscado,
               MIN(h.precio) as precio_min,
               f_min.nombre_farmacia as farmacia_barata,
               f_min.color_distintivo as color,
               COUNT(h.id_historial) as total_busquedas
        FROM historial h
        JOIN medicamentos m ON h.id_medicamento = m.id_medicamento
        JOIN farmacias f_min ON f_min.id_farmacias = (
            SELECT h2.id_farmacia FROM historial h2
            WHERE h2.id_medicamento = m.id_medicamento
            ORDER BY h2.precio ASC LIMIT 1
        )
        GROUP BY m.id_medicamento
        ORDER BY total_busquedas DESC
        LIMIT 10
    ''')
    resultados = []
    for row in c.fetchall():
        resultados.append({
            "nombre": row[0],
            "precio_min": row[1],
            "farmacia": row[2],
            "color": row[3],
            "busquedas": row[4]
        })
    conn.close()
    return jsonify(resultados)


# =========================================================
# ALERTAS DE PRECIO
# =========================================================

@app.route('/alertas', methods=['POST'])
def crear_alerta():
    usuario = resolver_token()
    if not usuario:
        return jsonify({"error": "Sesión requerida."}), 401
    data = request.json
    medicamento = data.get('medicamento', '').strip().lower()
    umbral = data.get('umbral_precio', 0)
    if not medicamento or not umbral:
        return jsonify({"error": "Medicamento y precio umbral son obligatorios."}), 400
    try:
        umbral = int(umbral)
    except (ValueError, TypeError):
        return jsonify({"error": "El precio umbral debe ser un número entero."}), 400

    conn = sqlite3.connect('farmacia.db')
    c = conn.cursor()
    # Verificar que no tenga ya una alerta para ese medicamento
    c.execute("SELECT id_alerta FROM alertas_precio WHERE id_usuario = ? AND medicamento = ? AND activa = 1",
              (usuario['id'], medicamento))
    if c.fetchone():
        # Actualizar el umbral existente
        c.execute("UPDATE alertas_precio SET umbral_precio = ? WHERE id_usuario = ? AND medicamento = ? AND activa = 1",
                  (umbral, usuario['id'], medicamento))
    else:
        c.execute("INSERT INTO alertas_precio (id_usuario, medicamento, umbral_precio) VALUES (?, ?, ?)",
                  (usuario['id'], medicamento, umbral))
    conn.commit()
    conn.close()
    return jsonify({"mensaje": f"Alerta creada: te avisaremos cuando {medicamento} baje de ${umbral:,} CLP.".replace(",", ".")})


@app.route('/alertas', methods=['GET'])
def listar_alertas():
    usuario = resolver_token()
    if not usuario:
        return jsonify({"error": "Sesión requerida."}), 401
    conn = sqlite3.connect('farmacia.db')
    c = conn.cursor()
    c.execute("SELECT id_alerta, medicamento, umbral_precio, fecha_creacion FROM alertas_precio WHERE id_usuario = ? AND activa = 1 ORDER BY fecha_creacion DESC",
              (usuario['id'],))
    alertas = []
    for row in c.fetchall():
        alertas.append({"id": row[0], "medicamento": row[1], "umbral": row[2], "fecha": row[3]})
    conn.close()
    return jsonify(alertas)


@app.route('/alertas/<int:aid>', methods=['DELETE'])
def eliminar_alerta(aid):
    usuario = resolver_token()
    if not usuario:
        return jsonify({"error": "Sesión requerida."}), 401
    conn = sqlite3.connect('farmacia.db')
    c = conn.cursor()
    c.execute("DELETE FROM alertas_precio WHERE id_alerta = ? AND id_usuario = ?", (aid, usuario['id']))
    conn.commit()
    conn.close()
    return jsonify({"mensaje": "Alerta eliminada."})


@app.route('/alertas/verificar', methods=['GET'])
def verificar_alertas():
    """Verifica si alguna alerta del usuario se cumplió (precio actual <= umbral)."""
    usuario = resolver_token()
    if not usuario:
        return jsonify({"error": "Sesión requerida."}), 401
    conn = sqlite3.connect('farmacia.db')
    c = conn.cursor()
    c.execute("SELECT id_alerta, medicamento, umbral_precio FROM alertas_precio WHERE id_usuario = ? AND activa = 1",
              (usuario['id'],))
    alertas = c.fetchall()
    disparadas = []
    for alerta_id, med, umbral in alertas:
        # Buscar el precio más bajo registrado para ese medicamento
        c.execute('''SELECT MIN(h.precio), f.nombre_farmacia
                     FROM historial h
                     JOIN medicamentos m ON h.id_medicamento = m.id_medicamento
                     JOIN farmacias f ON h.id_farmacia = f.id_farmacias
                     WHERE m.nombre_buscado = ?
                     GROUP BY h.id_farmacia
                     ORDER BY MIN(h.precio) ASC LIMIT 1''', (med,))
        row = c.fetchone()
        if row and row[0] <= umbral:
            disparadas.append({
                "id": alerta_id,
                "medicamento": med,
                "umbral": umbral,
                "precio_actual": row[0],
                "farmacia": row[1]
            })
    conn.close()
    return jsonify(disparadas)


# =========================================================
# HISTORIAL DE CHAT (persistencia de conversaciones con Mathew)
# =========================================================

@app.route('/chat/historial', methods=['GET'])
def chat_historial():
    usuario = resolver_token()
    if not usuario:
        return jsonify([])
    conn = sqlite3.connect('farmacia.db')
    c = conn.cursor()
    c.execute('''SELECT rol, mensaje, fecha FROM chat_historial
                 WHERE id_usuario = ? ORDER BY id_chat ASC LIMIT 100''',
              (usuario['id'],))
    mensajes = [{"rol": r[0], "mensaje": r[1], "fecha": r[2]} for r in c.fetchall()]
    conn.close()
    return jsonify(mensajes)


@app.route('/chat/historial', methods=['DELETE'])
def chat_limpiar():
    usuario = resolver_token()
    if not usuario:
        return jsonify({"error": "No autenticado."}), 401
    conn = sqlite3.connect('farmacia.db')
    c = conn.cursor()
    c.execute("DELETE FROM chat_historial WHERE id_usuario = ?", (usuario['id'],))
    conn.commit()
    conn.close()
    return jsonify({"mensaje": "Historial de chat eliminado."})


def _guardar_chat(user_id, rol, mensaje):
    """Guarda un mensaje de chat en la BD. Se llama internamente."""
    if not user_id or not mensaje:
        return
    try:
        conn = sqlite3.connect('farmacia.db')
        c = conn.cursor()
        c.execute("INSERT INTO chat_historial (id_usuario, rol, mensaje) VALUES (?, ?, ?)",
                  (user_id, rol, mensaje[:5000]))  # limita a 5000 chars
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Error guardando chat: {e}")


@app.route('/consultar_asistente', methods=['POST'])
def consultar_asistente():
    # IA es pública — no requiere token, pero si hay token guardamos el chat
    usuario = resolver_token()
    user_id = usuario['id'] if usuario else None

    data = request.json
    pregunta = data.get('pregunta', '')
    idioma_usuario = data.get('idioma', 'es')
    archivo_base64 = data.get('archivo_base64')
    latitud = data.get('latitud')
    longitud = data.get('longitud')

    # Guardar mensaje del usuario
    if user_id and pregunta:
        _guardar_chat(user_id, 'user', pregunta)
    elif user_id and archivo_base64:
        _guardar_chat(user_id, 'user', '🖼️ Imagen de receta médica enviada')

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

    # Contexto de ubicación del usuario
    contexto_ubicacion = ""
    if latitud and longitud:
        contexto_ubicacion = (
            f"\n\nUBICACIÓN DEL USUARIO: Latitud {latitud}, Longitud {longitud} (Chile). "
            "Si pregunta por farmacias, clínicas, hospitales o centros médicos cercanos, "
            "usa estas coordenadas para orientarlo geográficamente. Menciona comunas, calles o sectores chilenos conocidos "
            "que estén cerca de esas coordenadas. También recuérdale que puede usar la sección 'Mapa Salud' de FarmaConnect "
            "para ver las sucursales exactas en un mapa interactivo."
        )

    reglas = (
        "REGLAS DE SISTEMA DE FARMACONNECT:\n"
        "1. Eres Mathew, asistente clínico virtual de FarmaConnect. NO eres médico. Responde de forma cálida y profesional.\n"
        "2. Responde dudas de salud humana, malestares, síntomas comunes, y consultas sobre medicamentos.\n"
        "3. No sugieras medicamentos por iniciativa propia para tratar dolores. Usa medidas físicas leves (reposo, compresas).\n"
        "4. PROTOCOLO DE TABLA: SÓLO si recibes 'DATOS REALES EXTRAÍDOS', construye una tabla Markdown con los precios.\n"
        "5. Cuando el usuario pregunte por farmacias, clínicas u hospitales cercanos, oriéntalo geográficamente usando "
        "la ubicación proporcionada (si la hay) y recomiéndale usar la sección 'Mapa Salud' de FarmaConnect para ver un mapa interactivo.\n"
        "6. Explica brevemente para qué sirve cada fármaco mencionado. Incluye SIEMPRE advertencia de consultar médico.\n"
        + ("7. Responde SIEMPRE en INGLÉS (English). Sé conciso pero informativo."
           if idioma_usuario == 'en' else
           "7. Responde siempre en español. Sé conciso pero informativo.")
        + f"{contexto_ubicacion}"
    )

    try:
        if archivo_base64:
            contenido = [
                {"type": "text", "text": f"{reglas}\n\nContexto: {contexto_precios}\n\nConsulta: {pregunta}"},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{archivo_base64}"}}
            ]
            completion = client.chat.completions.create(
                model="meta-llama/llama-4-scout-17b-16e-instruct",
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
        respuesta = completion.choices[0].message.content

        # Guardar respuesta de Mathew
        if user_id:
            _guardar_chat(user_id, 'assistant', respuesta)

        return jsonify({"respuesta": respuesta})
    except Exception as e:
        print(f"Error Groq: {e}")
        return jsonify({"respuesta": "Mathew está experimentando problemas técnicos temporales."}), 500


if __name__ == '__main__':
    app.run(debug=True, port=8000)