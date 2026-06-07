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

    // Mostrar el botón de administración solo si el usuario es admin
    const navAdmin = document.getElementById('nav-admin-btn');
    if (navAdmin) navAdmin.style.display = usuario.es_admin ? 'flex' : 'none';

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

        // Detectar el precio más bajo para destacarlo
        let menorPrecio = Infinity;
        data.precios.forEach(p => {
            const val = parseInt(String(p.precio).replace(/\D/g, ''), 10);
            if (!isNaN(val) && val < menorPrecio) menorPrecio = val;
        });

        // Ordenar: más barato primero
        const ordenados = [...data.precios].sort((a, b) => {
            const va = parseInt(String(a.precio).replace(/\D/g, ''), 10) || Infinity;
            const vb = parseInt(String(b.precio).replace(/\D/g, ''), 10) || Infinity;
            return va - vb;
        });

        let html = `<div class="results-table-wrapper">
            <table class="results-table">
                <thead>
                    <tr>
                        <th>Farmacia</th>
                        <th>Producto encontrado</th>
                        <th>Precio</th>
                        <th>Estado</th>
                        <th style="text-align:right;">Acción</th>
                    </tr>
                </thead>
                <tbody>`;

        ordenados.forEach(p => {
            const val = parseInt(String(p.precio).replace(/\D/g, ''), 10);
            const esMasBarato = val === menorPrecio;
            const iniciales = p.farmacia.split(' ').map(w => w[0]).join('').substring(0, 2).toUpperCase();

            // Celda de precio con original tachado si hay oferta
            let celdaPrecio = `<span class="precio-actual">$${p.precio}</span><span class="precio-clp">CLP</span>`;
            if (p.oferta && p.precio_original) {
                celdaPrecio += `<br><span class="precio-original">$${p.precio_original}</span>`;
            }

            // Badges de estado
            let badges = '';
            if (esMasBarato) badges += `<span class="badge badge-barato">💰 Más barato</span>`;
            if (p.oferta)    badges += `<span class="badge badge-oferta">🏷️ En oferta</span>`;
            if (!badges) badges = `<span class="badge badge-normal">Precio normal</span>`;

            html += `<tr${esMasBarato ? ' class="row-barato"' : ''}>
                <td>
                    <div class="farmacia-cell">
                        <div class="farmacia-avatar" style="background:${p.color};">${iniciales}</div>
                        <span class="farmacia-nombre" style="color:${p.color};">${p.farmacia}</span>
                    </div>
                </td>
                <td><span class="producto-nombre">${p.nombre}</span></td>
                <td class="precio-cell">${celdaPrecio}</td>
                <td><div class="badges-cell">${badges}</div></td>
                <td style="text-align:right;">
                    <a href="${p.link}" target="_blank" class="btn-ir-web">Ir a la web <span>↗</span></a>
                </td>
            </tr>`;
        });

        html += `</tbody></table></div>`;
        res.innerHTML = html;
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
        let preciosAhumada = [], preciosSimi = [], preciosSalcobrand = [], preciosCruzVerde = [];

        etiquetasFechas.forEach(f => {
            const rA = data.find(row => row[1] === "Ahumada"    && row[4].includes(f));
            const rS = data.find(row => row[1] === "Dr. Simi"   && row[4].includes(f));
            const rB = data.find(row => row[1] === "Salcobrand" && row[4].includes(f));
            const rC = data.find(row => row[1] === "Cruz Verde" && row[4].includes(f));
            preciosAhumada.push(rA ? rA[3] : null);
            preciosSimi.push(rS ? rS[3] : null);
            preciosSalcobrand.push(rB ? rB[3] : null);
            preciosCruzVerde.push(rC ? rC[3] : null);
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
                    { label: 'Salcobrand', data: preciosSalcobrand, borderColor: '#ffd400', backgroundColor: '#ffd400', tension: 0.2, spanGaps: true, pointRadius: 5, borderWidth: 3 },
                    { label: 'Cruz Verde', data: preciosCruzVerde,  borderColor: '#009639', backgroundColor: '#009639', tension: 0.2, spanGaps: true, pointRadius: 5, borderWidth: 3 }
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

// =========================================================
// IDENTIFICADOR DE PASTILLAS
// =========================================================
let pillImages = []; // array de { base64, dataUrl }

// Drag & drop
document.addEventListener('DOMContentLoaded', () => {
    const zone = document.getElementById('pill-drop-zone');
    if (!zone) return;
    zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('drag-over'); });
    zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
    zone.addEventListener('drop', e => {
        e.preventDefault();
        zone.classList.remove('drag-over');
        const files = Array.from(e.dataTransfer.files).filter(f => f.type.startsWith('image/')).slice(0, 2);
        files.forEach(f => agregarImagenPastilla(f));
    });
});

function pillFileSelected(e) {
    const files = Array.from(e.target.files).slice(0, 2 - pillImages.length);
    files.forEach(f => agregarImagenPastilla(f));
    e.target.value = ''; // permite reseleccionar el mismo archivo
}

function agregarImagenPastilla(file) {
    if (pillImages.length >= 2) return;
    const reader = new FileReader();
    reader.onload = ev => {
        pillImages.push({
            base64: ev.target.result.split(',')[1],
            dataUrl: ev.target.result
        });
        renderPillPreviews();
    };
    reader.readAsDataURL(file);
}

function renderPillPreviews() {
    const container = document.getElementById('pill-previews');
    const placeholder = document.getElementById('pill-placeholder');

    if (pillImages.length === 0) {
        container.style.display = 'none';
        placeholder.style.display = 'flex';
        document.getElementById('pill-identify-btn').disabled = true;
        document.getElementById('pill-clear-btn').style.display = 'none';
        return;
    }

    placeholder.style.display = 'none';
    container.style.display = 'flex';
    document.getElementById('pill-identify-btn').disabled = false;
    document.getElementById('pill-clear-btn').style.display = 'inline-flex';

    let html = '';
    pillImages.forEach((img, i) => {
        html += `<div class="pill-preview-slot">
            <img src="${img.dataUrl}" alt="Foto ${i + 1}">
            <button class="pill-preview-remove" onclick="event.stopPropagation(); quitarImagenPastilla(${i})">✕</button>
            <span class="pill-preview-label">${i === 0 ? 'Anverso' : 'Reverso'}</span>
        </div>`;
    });
    if (pillImages.length < 2) {
        html += `<div class="pill-preview-slot pill-add-slot" onclick="event.stopPropagation(); document.getElementById('pill-file-input').click();">
            <i data-lucide="plus" style="width:28px;height:28px;color:var(--text-muted);"></i>
            <span style="font-size:0.8rem;color:var(--text-muted);">Agregar reverso</span>
        </div>`;
    }
    container.innerHTML = html;
    lucide.createIcons();
}

function quitarImagenPastilla(index) {
    pillImages.splice(index, 1);
    renderPillPreviews();
    document.getElementById('pill-result').style.display = 'none';
}

function limpiarIdentificador() {
    pillImages = [];
    document.getElementById('pill-file-input').value = '';
    renderPillPreviews();
    document.getElementById('pill-result').style.display = 'none';
}

async function identificarPastilla() {
    if (pillImages.length === 0) return;
    const btn = document.getElementById('pill-identify-btn');
    const resultDiv = document.getElementById('pill-result');

    btn.disabled = true;
    btn.innerHTML = '<div class="auth-spinner"></div> Analizando imagen...';
    resultDiv.style.display = 'block';
    resultDiv.innerHTML = `
        <div class="pill-analyzing">
            <div class="pill-scan-animation"></div>
            <p>La IA está analizando ${pillImages.length > 1 ? 'las pastillas' : 'la pastilla'}...</p>
        </div>`;

    try {
        const r = await fetch(`${API}/identificar_pastilla`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ imagenes_base64: pillImages.map(i => i.base64) })
        });
        const data = await r.json();

        if (data.error) {
            resultDiv.innerHTML = `<div class="pill-error">${data.error}</div>`;
            return;
        }

        const p = data.resultado;
        const confianzaColor = p.confianza === 'alta' ? '#10b981' : p.confianza === 'media' ? '#f59e0b' : '#ef4444';
        const confianzaLabel = p.confianza === 'alta' ? 'Alta confianza' : p.confianza === 'media' ? 'Confianza media' : 'Baja confianza';

        resultDiv.innerHTML = `
            <div class="pill-result-card">
                <div class="pill-result-header">
                    <div>
                        <h3 class="pill-result-name">${p.nombre || 'No identificado'}</h3>
                        <p class="pill-result-activo">${p.principio_activo || ''}</p>
                    </div>
                    <span class="pill-confianza-badge" style="background:${confianzaColor}20;color:${confianzaColor};border:1px solid ${confianzaColor}40;">
                        ${confianzaLabel}
                    </span>
                </div>

                <div class="pill-result-grid">
                    ${p.descripcion ? `<div class="pill-info-block"><span class="pill-info-label">¿Para qué sirve?</span><p>${p.descripcion}</p></div>` : ''}
                    <div class="pill-info-row">
                        ${p.forma ? `<div class="pill-info-chip"><i data-lucide="pill" style="width:14px;height:14px;"></i> ${p.forma}</div>` : ''}
                        ${p.color ? `<div class="pill-info-chip"><i data-lucide="palette" style="width:14px;height:14px;"></i> ${p.color}</div>` : ''}
                        ${p.grabado && p.grabado !== 'N/A' ? `<div class="pill-info-chip"><i data-lucide="type" style="width:14px;height:14px;"></i> ${p.grabado}</div>` : ''}
                        ${p.laboratorio && p.laboratorio !== 'Desconocido' ? `<div class="pill-info-chip"><i data-lucide="building-2" style="width:14px;height:14px;"></i> ${p.laboratorio}</div>` : ''}
                    </div>
                    ${p.advertencia ? `<div class="pill-info-warning"><i data-lucide="alert-triangle" style="width:14px;height:14px;"></i> ${p.advertencia}</div>` : ''}
                </div>

                ${p.buscar ? `
                <button class="btn-premium pill-compare-btn" onclick="buscarDesdeIdentificador('${p.buscar.replace(/'/g, "\\'")}')">
                    <i data-lucide="bar-chart-2"></i> Comparar precios de "${p.buscar}" en farmacias
                </button>` : ''}
            </div>`;

        lucide.createIcons();

    } catch {
        resultDiv.innerHTML = `<div class="pill-error">No se pudo conectar con el servidor.</div>`;
    } finally {
        btn.disabled = false;
        btn.innerHTML = '<i data-lucide="search"></i> Identificar medicamento';
        lucide.createIcons();
    }
}

function buscarDesdeIdentificador(termino) {
    const searchInput = document.getElementById('manual-search');
    searchInput.value = termino;
    const navBtns = document.querySelectorAll('.nav-btn');
    navBtns.forEach(b => {
        if (b.textContent.trim().includes('Comparador')) {
            showSection('search', b);
        }
    });
    startScraping();
}

// =========================================================
// PANEL DE ADMINISTRADOR
// =========================================================
async function abrirAdmin(btn) {
    showSection('admin', btn);
    await cargarStats();
    await cargarUsuarios();
}

function adminTab(tab, btn) {
    document.querySelectorAll('.admin-tab').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    ['usuarios', 'historial', 'medicamentos'].forEach(t => {
        document.getElementById('admin-panel-' + t).style.display = (t === tab) ? 'block' : 'none';
    });
    if (tab === 'usuarios') cargarUsuarios();
    if (tab === 'historial') cargarHistorialAdmin();
    if (tab === 'medicamentos') cargarMedicamentosAdmin();
}

async function cargarStats() {
    try {
        const r = await fetch(`${API}/admin/stats`, { headers: authHeaders() });
        if (!r.ok) return;
        const s = await r.json();
        document.getElementById('stat-usuarios').textContent = s.usuarios;
        document.getElementById('stat-admins').textContent = s.admins;
        document.getElementById('stat-meds').textContent = s.medicamentos;
        document.getElementById('stat-busquedas').textContent = s.busquedas;
    } catch (e) { console.error(e); }
}

// ---- USUARIOS ----
async function cargarUsuarios() {
    const cont = document.getElementById('admin-panel-usuarios');
    cont.innerHTML = '<p class="admin-loading">Cargando usuarios...</p>';
    try {
        const r = await fetch(`${API}/admin/usuarios`, { headers: authHeaders() });
        if (!r.ok) { cont.innerHTML = '<p class="admin-loading">Acceso denegado.</p>'; return; }
        const usuarios = await r.json();

        let html = `<table class="admin-table">
            <thead><tr><th>ID</th><th>Nombre</th><th>Correo</th><th>Rol</th><th style="text-align:right;">Acciones</th></tr></thead><tbody>`;
        usuarios.forEach(u => {
            html += `<tr>
                <td>${u.id}</td>
                <td>${u.nombre}</td>
                <td>${u.correo}</td>
                <td>${u.es_admin ? '<span class="badge badge-admin">Admin</span>' : '<span class="badge badge-normal">Usuario</span>'}</td>
                <td style="text-align:right;white-space:nowrap;">
                    <button class="admin-btn-icon" title="Editar"
                        onclick='abrirModalUsuario(${JSON.stringify(u)})'><i data-lucide="edit"></i></button>
                    <button class="admin-btn-icon danger" title="Eliminar"
                        onclick="eliminarUsuario(${u.id}, '${u.nombre.replace(/'/g, "")}')"><i data-lucide="trash-2"></i></button>
                </td>
            </tr>`;
        });
        html += '</tbody></table>';
        cont.innerHTML = html;
        lucide.createIcons();
    } catch (e) {
        cont.innerHTML = '<p class="admin-loading">Error de conexión.</p>';
    }
}

function abrirModalUsuario(u) {
    document.getElementById('edit-user-id').value = u.id;
    document.getElementById('edit-user-nombre').value = u.nombre;
    document.getElementById('edit-user-correo').value = u.correo;
    document.getElementById('edit-user-password').value = '';
    document.getElementById('edit-user-admin').checked = !!u.es_admin;
    document.getElementById('edit-user-alert').style.display = 'none';
    document.getElementById('edit-user-modal').style.display = 'flex';
    lucide.createIcons();
}

function cerrarModalUsuario() {
    document.getElementById('edit-user-modal').style.display = 'none';
}

async function guardarUsuario() {
    const id       = document.getElementById('edit-user-id').value;
    const nombre   = document.getElementById('edit-user-nombre').value.trim();
    const correo   = document.getElementById('edit-user-correo').value.trim();
    const password = document.getElementById('edit-user-password').value;
    const es_admin = document.getElementById('edit-user-admin').checked;
    const alertEl  = document.getElementById('edit-user-alert');

    try {
        const r = await fetch(`${API}/admin/usuarios/${id}`, {
            method: 'PUT',
            headers: authHeaders(),
            body: JSON.stringify({ nombre, correo, password, es_admin })
        });
        const data = await r.json();
        if (!r.ok) {
            alertEl.textContent = data.error || 'Error al guardar.';
            alertEl.style.display = 'block';
            return;
        }
        cerrarModalUsuario();
        await cargarStats();
        await cargarUsuarios();
    } catch {
        alertEl.textContent = 'Error de conexión con el servidor.';
        alertEl.style.display = 'block';
    }
}

async function eliminarUsuario(id, nombre) {
    if (!confirm(`¿Eliminar al usuario "${nombre}"? Esta acción no se puede deshacer.`)) return;
    try {
        const r = await fetch(`${API}/admin/usuarios/${id}`, { method: 'DELETE', headers: authHeaders() });
        const data = await r.json();
        if (!r.ok) { alert(data.error || 'No se pudo eliminar.'); return; }
        await cargarStats();
        await cargarUsuarios();
    } catch { alert('Error de conexión.'); }
}

// ---- HISTORIAL ----
async function cargarHistorialAdmin() {
    const cont = document.getElementById('admin-panel-historial');
    cont.innerHTML = '<p class="admin-loading">Cargando historial...</p>';
    try {
        const r = await fetch(`${API}/admin/historial`, { headers: authHeaders() });
        if (!r.ok) { cont.innerHTML = '<p class="admin-loading">Acceso denegado.</p>'; return; }
        const rows = await r.json();
        if (rows.length === 0) { cont.innerHTML = '<p class="admin-loading">Sin registros todavía.</p>'; return; }

        let html = `<table class="admin-table">
            <thead><tr><th>Buscado</th><th>Farmacia</th><th>Producto</th><th>Precio</th><th>Usuario</th><th>Fecha</th><th></th></tr></thead><tbody>`;
        rows.forEach(h => {
            html += `<tr>
                <td>${h.buscado}</td>
                <td>${h.farmacia}</td>
                <td style="max-width:200px;">${h.producto}</td>
                <td style="color:#10b981;font-weight:600;">$${Number(h.precio).toLocaleString('es-CL')}</td>
                <td>${h.usuario}</td>
                <td style="font-size:0.8rem;color:var(--text-muted);">${h.fecha ? h.fecha.substring(0,16) : ''}</td>
                <td style="text-align:right;">
                    <button class="admin-btn-icon danger" title="Eliminar"
                        onclick="eliminarHistorial(${h.id})"><i data-lucide="trash-2"></i></button>
                </td>
            </tr>`;
        });
        html += '</tbody></table>';
        cont.innerHTML = html;
        lucide.createIcons();
    } catch {
        cont.innerHTML = '<p class="admin-loading">Error de conexión.</p>';
    }
}

async function eliminarHistorial(id) {
    if (!confirm('¿Eliminar este registro del historial?')) return;
    try {
        const r = await fetch(`${API}/admin/historial/${id}`, { method: 'DELETE', headers: authHeaders() });
        if (!r.ok) { alert('No se pudo eliminar.'); return; }
        await cargarStats();
        await cargarHistorialAdmin();
    } catch { alert('Error de conexión.'); }
}

// ---- MEDICAMENTOS ----
async function cargarMedicamentosAdmin() {
    const cont = document.getElementById('admin-panel-medicamentos');
    cont.innerHTML = '<p class="admin-loading">Cargando medicamentos...</p>';
    try {
        const r = await fetch(`${API}/admin/medicamentos`, { headers: authHeaders() });
        if (!r.ok) { cont.innerHTML = '<p class="admin-loading">Acceso denegado.</p>'; return; }
        const meds = await r.json();
        if (meds.length === 0) { cont.innerHTML = '<p class="admin-loading">Catálogo vacío.</p>'; return; }

        let html = `<table class="admin-table">
            <thead><tr><th>ID</th><th>Medicamento</th><th>Búsquedas registradas</th><th style="text-align:right;">Acciones</th></tr></thead><tbody>`;
        meds.forEach(m => {
            html += `<tr>
                <td>${m.id}</td>
                <td style="text-transform:uppercase;font-weight:500;">${m.nombre}</td>
                <td>${m.busquedas}</td>
                <td style="text-align:right;">
                    <button class="admin-btn-icon danger" title="Eliminar"
                        onclick="eliminarMedicamento(${m.id}, '${m.nombre.replace(/'/g, "")}')"><i data-lucide="trash-2"></i></button>
                </td>
            </tr>`;
        });
        html += '</tbody></table>';
        cont.innerHTML = html;
        lucide.createIcons();
    } catch {
        cont.innerHTML = '<p class="admin-loading">Error de conexión.</p>';
    }
}

async function eliminarMedicamento(id, nombre) {
    if (!confirm(`¿Eliminar "${nombre}" y todo su historial asociado?`)) return;
    try {
        const r = await fetch(`${API}/admin/medicamentos/${id}`, { method: 'DELETE', headers: authHeaders() });
        if (!r.ok) { alert('No se pudo eliminar.'); return; }
        await cargarStats();
        await cargarMedicamentosAdmin();
    } catch { alert('Error de conexión.'); }
}