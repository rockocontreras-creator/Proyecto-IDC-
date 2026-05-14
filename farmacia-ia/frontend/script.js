lucide.createIcons();
let ultimosResultados = "";

// MODO OSCURO
const toggle = document.getElementById('theme-toggle');
toggle.addEventListener('click', () => {
    const isDark = document.body.classList.toggle('dark-mode');
    localStorage.setItem('theme', isDark ? 'dark' : 'light');
    document.getElementById('theme-icon').setAttribute('data-lucide', isDark ? 'sun' : 'moon');
    lucide.createIcons();
});
if(localStorage.getItem('theme') === 'dark') document.body.classList.add('dark-mode');

// NAVEGACIÓN
function showSection(id, btn) {
    document.querySelectorAll('.content-section').forEach(s => s.classList.remove('active-section'));
    document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
    document.getElementById(id + '-section').classList.add('active-section');
    btn.classList.add('active');
}

// SCRAPING
async function startScraping() {
    const q = document.getElementById('manual-search').value;
    const res = document.getElementById('scraping-results');
    if(!q) return;
    res.innerHTML = "<p style='padding:20px; text-align:center;'>⏳ Analizando farmacias...</p>";
    try {
        const r = await fetch('http://127.0.0.1:5000/scraping_manual', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({remedio: q})
        });
        const data = await r.json();
        ultimosResultados = JSON.stringify(data.precios);
        let html = "<table><tr><th>Farmacia</th><th>Producto</th><th>Precio</th><th>Link</th></tr>";
        data.precios.forEach(p => {
            html += `<tr><td style="color:${p.color}; font-weight:bold;">${p.farmacia}</td><td>${p.nombre}</td><td>${p.precio}</td><td><a href="${p.link}" target="_blank">Ir ↗</a></td></tr>`;
        });
        res.innerHTML = html + "</table>";
    } catch { res.innerHTML = "Error de conexión."; }
}

// CHAT IA
async function enviarMensaje() {
    const inp = document.getElementById('chat-input');
    const box = document.getElementById('chat-box');
    if(!inp.value) return;
    box.innerHTML += `<p style='text-align:right;'><b>Tú:</b> ${inp.value}</p>`;
    const prompt = inp.value; inp.value = "";
    try {
        const r = await fetch('http://127.0.0.1:5000/consultar_asistente', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({pregunta: prompt, contexto_precios: ultimosResultados})
        });
        const data = await r.json();
        box.innerHTML += `<p><b>Mathew:</b> ${data.respuesta}</p>`;
        box.scrollTop = box.scrollHeight;
    } catch { box.innerHTML += "<p>Error de IA.</p>"; }
}

// HISTORIAL Y MAPA (Igual a versiones previas, simplificados)
async function cargarHistorial() {
    const r = await fetch('http://127.0.0.1:5000/obtener_historial');
    const data = await r.json();
    let html = "<table><tr><th>Fecha</th><th>Farmacia</th><th>Precio</th></tr>";
    data.forEach(row => { html += `<tr><td>${row[4]}</td><td>${row[1]}</td><td>$${row[3]}</td></tr>`; });
    document.getElementById('history-content').innerHTML = html + "</table>";
}

function actualizarMapa(tipo) {
    if(navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(p => {
            const lat = p.coords.latitude, lng = p.coords.longitude;
            document.getElementById('map-iframe').src = `https://www.google.com/maps/embed/v1/search?key=TU_GOOGLE_KEY&center=${lat},${lng}&zoom=14&q=${tipo}`;
            // Alternativa sin key: 
            document.getElementById('map-iframe').src = `https://maps.google.com/maps?q=${tipo}&ll=${lat},${lng}&z=14&output=embed`;
        });
    }
}