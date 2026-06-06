lucide.createIcons();

// =========================================================
// ESTADO GLOBAL
// =========================================================
let ultimosResultados = "";
let base64File = null;
let miGrafico = null;
const API = 'http://127.0.0.1:8000';

// Token en localStorage — persiste entre recargas
function getToken() { return localStorage.getItem('fc_token'); }
function setToken(t) { localStorage.setItem('fc_token', t); }
function clearToken() { localStorage.removeItem('fc_token'); localStorage.removeItem('fc_usuario'); }
function getUsuario() {
    try { return JSON.parse(localStorage.getItem('fc_usuario')); } catch { return null; }
}
function setUsuario(u) { localStorage.setItem('fc_usuario', JSON.stringify(u)); }

// Headers con token cuando está disponible
function authHeaders() {
    const h = { 'Content-Type': 'application/json' };
    const t = getToken();
    if (t) h['Authorization'] = `Bearer ${t}`;
    return h;
}

// =========================================================
// MODO OSCURO
// =========================================================
const themeBtn = document.getElementById('theme-toggle');
themeBtn.addEventListener('click', () => {
    const isDark = document.body.classList.toggle('dark-mode');
    document.getElementById('theme-icon').setAttribute('data-lucide', isDark ? 'sun' : 'moon');
    localStorage.setItem('theme', isDark ? 'dark' : 'light');
    lucide.createIcons();
    if (miGrafico) cargarHistorialFiltrado();
});
if (localStorage.getItem('theme') === 'dark') document.body.classList.add('dark-mode');

// =========================================================
// INIT — restaurar sesión desde localStorage sin llamar al servidor
// =========================================================
window.addEventListener('DOMContentLoaded', () => {
    const token = getToken();
    const usuario = getUsuario();
    if (token && usuario) {
        // Ya tenemos token guardado → entrar directo sin mostrar overlay
        mostrarApp(usuario);
    } else {
        // Sin sesión → mostrar overlay
        document.getElementById('auth-overlay').style.display = 'flex';
        document.getElementById('app-main').style.display = 'none';
    }
    lucide.createIcons();
});

// =========================================================
// AUTENTICACIÓN
// =========================================================
function switchAuthTab(tab) {
    document.getElementById('tab-login').classList.toggle('active', tab === 'login');
    document.getElementById('tab-registro').classList.toggle('active', tab === 'registro');
    document.getElementById('form-login').classList.toggle('active-form', tab === 'login');
    document.getElementById('form-registro').classList.toggle('active-form', tab === 'registro');
    ocultarAuthAlert();
}

function mostrarAuthAlert(mensaje, tipo = 'error') {
    const el = document.getElementById('auth-alert');
    el.textContent = mensaje;
    el.className = `auth-alert ${tipo}`;
    el.style.display = 'block';
}

function ocultarAuthAlert() {
    document.getElementById('auth-alert').style.display = 'none';
}

function setBtnLoading(btnId, loading) {
    const btn = document.getElementById(btnId);
    if (loading) {
        btn.disabled = true;
        btn.innerHTML = `<div class="auth-spinner"></div> Procesando...`;
    } else {
        btn.disabled = false;
        if (btnId === 'btn-login') {
            btn.innerHTML = `<span>Entrar</span><i data-lucide="arrow-right"></i>`;
        } else {
            btn.innerHTML = `<span>Crear cuenta</span><i data-lucide="user-plus"></i>`;
        }
        lucide.createIcons();
    }
}

async function doLogin() {
    const correo   = document.getElementById('login-correo').value.trim();
    const password = document.getElementById('login-password').value;
    if (!correo || !password) { mostrarAuthAlert('Por favor completa todos los campos.'); return; }

    setBtnLoading('btn-login', true);
    ocultarAuthAlert();
    try {
        const r = await fetch(`${API}/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ correo, password })
        });
        const data = await r.json();
        if (!r.ok) { mostrarAuthAlert(data.error || 'Error al iniciar sesión.'); return; }

        setToken(data.token);
        setUsuario(data.usuario);
        mostrarApp(data.usuario);
    } catch {
        mostrarAuthAlert('No se pudo conectar con el servidor Flask en el puerto 8000.');
    } finally {
        setBtnLoading('btn-login', false);
    }
}

async function doRegistro() {
    const nombre   = document.getElementById('reg-nombre').value.trim();
    const correo   = document.getElementById('reg-correo').value.trim();
    const password = document.getElementById('reg-password').value;
    if (!nombre || !correo || !password) { mostrarAuthAlert('Por favor completa todos los campos.'); return; }

    setBtnLoading('btn-registro', true);
    ocultarAuthAlert();
    try {
        const r = await fetch(`${API}/registro`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ nombre, correo, password })
        });
        const data = await r.json();
        if (!r.ok) { mostrarAuthAlert(data.error || 'Error al registrarse.'); return; }

        setToken(data.token);
        setUsuario(data.usuario);
        mostrarApp(data.usuario);
    } catch {
        mostrarAuthAlert('No se pudo conectar con el servidor Flask en el puerto 8000.');
    } finally {
        setBtnLoading('btn-registro', false);
    }
}

async function doLogout() {
    try {
        await fetch(`${API}/logout`, { method: 'POST', headers: authHeaders() });
    } catch (_) {}
    clearToken();

    // Ocultar app, mostrar overlay
    document.getElementById('app-main').style.display = 'none';
    const overlay = document.getElementById('auth-overlay');
    overlay.classList.remove('fade-out');
    overlay.style.display = 'flex';

    // Limpiar campos
    ['login-correo','login-password','reg-nombre','reg-correo','reg-password']
        .forEach(id => { document.getElementById(id).value = ''; });
    ocultarAuthAlert();
    switchAuthTab('login');
    lucide.createIcons();
}

function mostrarApp(usuario) {
    const overlay = document.getElementById('auth-overlay');
    overlay.classList.add('fade-out');
    setTimeout(() => { overlay.style.display = 'none'; }, 400);
    document.getElementById('app-main').style.display = 'flex';

    const iniciales = usuario.nombre.split(' ').map(p => p[0]).join('').substring(0, 2).toUpperCase();
    document.getElementById('user-avatar-initials').textContent = iniciales;
    document.getElementById('sidebar-user-name').textContent = usuario.nombre;
    document.getElementById('sidebar-user-email').textContent = usuario.correo;
    lucide.createIcons();
}

function togglePw(inputId, btn) {
    const input = document.getElementById(inputId);
    const isPassword = input.type === 'password';
    input.type = isPassword ? 'text' : 'password';
    btn.querySelector('i').setAttribute('data-lucide', isPassword ? 'eye-off' : 'eye');
    lucide.createIcons();
}

// =========================================================
// NAVEGACIÓN
// =========================================================
function showSection(id, btn) {
    document.querySelectorAll('.content-section').forEach(s => s.classList.remove('active-section'));
    document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
    document.getElementById(id + '-section').classList.add('active-section');
    btn.classList.add('active');
}

// =========================================================
// ARCHIVOS ADJUNTOS
// =========================================================
function previewFile() {
    const fileInput = document.getElementById('file-input');
    const previewContainer = document.getElementById('file-preview-container');
    const previewName = document.getElementById('file-preview-name');
    if (fileInput.files.length > 0) {
        const file = fileInput.files[0];
        previewName.textContent = file.name;
        previewContainer.style.display = 'flex';
        const reader = new FileReader();
        reader.onload = e => { base64File = e.target.result.split(',')[1]; };
        reader.readAsDataURL(file);
    }
}

function clearFile() {
    document.getElementById('file-input').value = "";
    document.getElementById('file-preview-container').style.display = 'none';
    base64File = null;
}

// =========================================================
// MATHEW IA — sin autenticación requerida
// =========================================================
async function enviarMensaje() {
    const inp = document.getElementById('chat-input');
    const box = document.getElementById('chat-box');
    const prompt = inp.value.trim();
    if (!prompt && !base64File) return;

    const userMsg = prompt || "🖼️ Imagen de Receta Médica enviada";
    box.innerHTML += `<div class="message message-user"><b>Tú:</b> ${userMsg}</div>`;
    inp.value = "";
    box.scrollTop = box.scrollHeight;

    inp.disabled = true;
    const sendBtn = inp.nextElementSibling;
    if (sendBtn) sendBtn.disabled = true;

    const fileToSend = base64File;
    clearFile();

    const loadingDiv = document.createElement('div');
    loadingDiv.className = 'message message-mathew loading-msg';
    loadingDiv.innerHTML = '⚡ <i>Mathew está analizando los registros...</i>';
    box.appendChild(loadingDiv);
    box.scrollTop = box.scrollHeight;

    try {
        // No requiere token — headers sin Authorization
        const r = await fetch(`${API}/consultar_asistente`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ pregunta: prompt, contexto_precios: ultimosResultados, archivo_base64: fileToSend })
        });
        const data = await r.json();
        loadingDiv.remove();
        const respuestaDiv = document.createElement('div');
        respuestaDiv.className = 'message message-mathew';
        respuestaDiv.innerHTML = `<b>Mathew:</b> ${marked.parse(data.respuesta)}`;
        box.appendChild(respuestaDiv);
        box.scrollTop = box.scrollHeight;
    } catch {
        loadingDiv.remove();
        box.innerHTML += `<div class="message message-mathew" style="color:var(--text-muted);">No se pudo conectar con Mathew.</div>`;
    } finally {
        inp.disabled = false;
        if (sendBtn) sendBtn.disabled = false;
        inp.focus();
    }
}

// =========================================================
// COMPARADOR — requiere login
// =========================================================
async function startScraping() {
    const q = document.getElementById('manual-search').value.trim();
    const res = document.getElementById('scraping-results');
    const searchBtn = document.querySelector('.search-bar-box button');
    if (!q) return;

    // Verificar si hay token antes de llamar
    if (!getToken()) {
        res.innerHTML = `
            <div class="auth-required-notice">
                <i data-lucide="lock" style="width:20px;height:20px;"></i>
                <span>Para usar el comparador necesitas <button onclick="pedirLogin()" class="link-btn">iniciar sesión</button>.</span>
            </div>`;
        lucide.createIcons();
        return;
    }

    searchBtn.disabled = true;
    res.innerHTML = `
        <div style="width:100%;border:1px solid var(--border);border-radius:12px;overflow:hidden;">
            <div style="background:var(--border);height:45px;padding:12px;font-weight:600;font-size:0.85rem;color:var(--text-muted);">⏳ CONECTANDO CON LOS HILOS DE SELENIUM...</div>
            <div style="padding:20px;display:flex;flex-direction:column;gap:12px;background:var(--card-bg);">
                <div style="height:20px;background:var(--border);border-radius:4px;opacity:0.6;animation:pulse 1.5s infinite;"></div>
                <div style="height:20px;background:var(--border);border-radius:4px;opacity:0.4;animation:pulse 1.5s infinite 0.2s;"></div>
                <div style="height:20px;background:var(--border);border-radius:4px;opacity:0.2;animation:pulse 1.5s infinite 0.4s;"></div>
            </div>
        </div>`;

    try {
        const r = await fetch(`${API}/scraping_manual`, {
            method: 'POST',
            headers: authHeaders(),
            body: JSON.stringify({ remedio: q })
        });

        if (r.status === 401) {
            clearToken();
            res.innerHTML = `
                <div class="auth-required-notice">
                    <i data-lucide="lock" style="width:20px;height:20px;"></i>
                    <span>Sesión expirada. <button onclick="pedirLogin()" class="link-btn">Inicia sesión nuevamente</button>.</span>
                </div>`;
            lucide.createIcons();
            return;
        }

        const data = await r.json();
        ultimosResultados = JSON.stringify(data.precios);

        if (!data.precios || data.precios.length === 0) {
            res.innerHTML = "<p style='color:var(--text-muted);padding:10px;'>No se encontraron ofertas para este término.</p>";
            return;
        }

        let html = "<table><tr><th>Farmacia</th><th>Producto Encontrado</th><th>Precio Registrado</th><th>Acción Comercial</th></tr>";
        data.precios.forEach(p => {
            html += `<tr>
                <td style="color:${p.color};font-weight:bold;">${p.farmacia}</td>
                <td style="font-weight:500;">${p.nombre}</td>
                <td style="font-weight:700;color:#10b981;">$${p.precio} CLP</td>
                <td><a href="${p.link}" target="_blank" class="btn-premium" style="padding:6px 12px;font-size:0.85rem;display:inline-flex;text-decoration:none;">Ir a la web ↗</a></td>
            </tr>`;
        });
        res.innerHTML = html + "</table>";
    } catch {
        res.innerHTML = "<p style='color:var(--text-muted);'>El servidor Flask en el puerto 8000 no responde.</p>";
    } finally {
        searchBtn.disabled = false;
    }
}

// Abre el overlay de login desde dentro de la app
function pedirLogin() {
    const overlay = document.getElementById('auth-overlay');
    overlay.classList.remove('fade-out');
    overlay.style.display = 'flex';
    switchAuthTab('login');
}

// =========================================================
// HISTORIAL
// =========================================================
async function abrirHistorial(btn) {
    showSection('history', btn);
    await inicializarSelector();
}

async function inicializarSelector() {
    const selector = document.getElementById('med-selector');
    try {
        const r = await fetch(`${API}/obtener_medicamentos`);
        const medicamentos = await r.json();
        selector.innerHTML = '<option value="">-- Elige un medicamento --</option>';
        if (medicamentos.length === 0) {
            selector.innerHTML = '<option value="">Sin registros en SQLite</option>';
            return;
        }
        medicamentos.forEach(med => {
            const opt = document.createElement('option');
            opt.value = med;
            opt.textContent = med.toUpperCase();
            selector.appendChild(opt);
        });
    } catch (e) {
        console.error("Error cargando selector:", e);
    }
}

async function cargarHistorialFiltrado() {
    const medSeleccionado = document.getElementById('med-selector').value;
    if (!medSeleccionado) return;
    try {
        const r = await fetch(`${API}/obtener_historial?medicamento=${encodeURIComponent(medSeleccionado)}`);
        const data = await r.json();
        if (data.length === 0) return;

        const etiquetasFechas = [...new Set(data.map(row => row[4].substring(11, 16)))];
        let preciosAhumada = [], preciosSimi = [], preciosSalcobrand = [];

        etiquetasFechas.forEach(f => {
            const rA = data.find(row => row[1] === "Ahumada"    && row[4].includes(f));
            const rS = data.find(row => row[1] === "Dr. Simi"   && row[4].includes(f));
            const rB = data.find(row => row[1] === "Salcobrand" && row[4].includes(f));
            preciosAhumada.push(rA ? rA[3] : null);
            preciosSimi.push(rS ? rS[3] : null);
            preciosSalcobrand.push(rB ? rB[3] : null);
        });

        if (miGrafico) miGrafico.destroy();

        const ctx = document.getElementById('historyChart').getContext('2d');
        const dark = document.body.classList.contains('dark-mode');

        miGrafico = new Chart(ctx, {
            type: 'line',
            data: {
                labels: etiquetasFechas,
                datasets: [
                    { label: 'Ahumada',    data: preciosAhumada,    borderColor: '#003399', backgroundColor: '#003399', tension: 0.2, spanGaps: true, pointRadius: 5, borderWidth: 3 },
                    { label: 'Dr. Simi',   data: preciosSimi,       borderColor: '#ce000c', backgroundColor: '#ce000c', tension: 0.2, spanGaps: true, pointRadius: 5, borderWidth: 3 },
                    { label: 'Salcobrand', data: preciosSalcobrand, borderColor: '#ffd400', backgroundColor: '#ffd400', tension: 0.2, spanGaps: true, pointRadius: 5, borderWidth: 3 }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { labels: { color: dark ? '#f1f5f9' : '#1e293b', font: { family: 'Inter', weight: '600', size: 12 } } } },
                scales: {
                    x: { ticks: { color: dark ? '#94a3b8' : '#64748b' }, grid: { color: dark ? '#334155' : '#e2e8f0' } },
                    y: { ticks: { color: dark ? '#94a3b8' : '#64748b', callback: v => '$' + v + ' CLP' }, grid: { color: dark ? '#334155' : '#e2e8f0' } }
                }
            }
        });
    } catch (e) {
        console.error("Error Chart.js:", e);
    }
}

// =========================================================
// MAPA
// =========================================================
function actualizarMapa(tipo) {
    if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(
            p => { document.getElementById('map-iframe').src = `https://maps.google.com/maps?q=${tipo}&ll=${p.coords.latitude},${p.coords.longitude}&z=14&output=embed`; },
            ()  => { document.getElementById('map-iframe').src = `https://maps.google.com/maps?q=${tipo}&z=13&output=embed`; }
        );
    }
}