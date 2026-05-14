lucide.createIcons();
let ultimosResultados = "";

// MODO OSCURO GLOBAL
const themeBtn = document.getElementById('theme-toggle');
themeBtn.addEventListener('click', () => {
    const isDark = document.body.classList.toggle('dark-mode');
    document.getElementById('theme-icon').setAttribute('data-lucide', isDark ? 'sun' : 'moon');
    localStorage.setItem('theme', isDark ? 'dark' : 'light');
    lucide.createIcons();
});
if(localStorage.getItem('theme') === 'dark') document.body.classList.add('dark-mode');

// NAVEGACIÓN SPA
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
    res.innerHTML = "<p style='margin-top:20px;'>⏳ Analizando farmacias...</p>";
    try {
        const r = await fetch('http://127.0.0.1:8000/scraping_manual', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({remedio: q})
        });
        const data = await r.json();
        ultimosResultados = JSON.stringify(data.precios);
        let html = "<table><tr><th>Farmacia</th><th>Producto</th><th>Precio</th><th>Link</th></tr>";
        data.precios.forEach(p => {
            html += `<tr><td style="color:${p.color}; font-weight:bold;">${p.farmacia}</td><td>${p.nombre}</td><td>${p.precio}</td><td><a href="${p.link}" target="_blank" style="color:var(--primary)">Ir ↗</a></td></tr>`;
        });
        res.innerHTML = html + "</table>";
    } catch { res.innerHTML = "Error al conectar con el servidor."; }
}

// CHAT ASISTENTE
async function enviarMensaje() {
    const inp = document.getElementById('chat-input');
    const box = document.getElementById('chat-box');
    if(!inp.value) return;

    box.innerHTML += `<div class="msg-user"><b>Tú:</b> ${inp.value}</div>`;
    const prompt = inp.value; inp.value = "";
    box.scrollTop = box.scrollHeight;

    try {
        const r = await fetch('http://127.0.0.1:8000/consultar_asistente', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({pregunta: prompt, contexto_precios: ultimosResultados})
        });
        const data = await r.json();
        box.innerHTML += `<div class="msg-mathew"><b>Mathew:</b> ${data.respuesta}</div>`;
        box.scrollTop = box.scrollHeight;
    } catch { box.innerHTML += `<div class="msg-mathew">Error de conexión.</div>`; }
}

// MAPA (CORRECCIÓN ERROR 404)
function actualizarMapa(tipo) {
    if(navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(p => {
            const lat = p.coords.latitude;
            const lng = p.coords.longitude;
            // Se corrigió la URL añadiendo "/maps" después del dominio de Google
            const url = `https://www.google.com/maps/embed/v1/search?key=TU_API_KEY_OPCIONAL&q=${tipo}&center=${lat},${lng}&zoom=14`;
            
            // Si no tienes API Key, usamos esta versión pública que no falla:
            const urlPublica = `https://maps.google.com/maps?q=${tipo}&ll=${lat},${lng}&z=14&output=embed`;
            
            document.getElementById('map-iframe').src = urlPublica;
        }, (error) => {
            alert("Error al obtener ubicación. Por favor, activa el GPS del navegador.");
        });
    } else {
        alert("Tu navegador no soporta geolocalización.");
    }
}