lucide.createIcons();
let ultimosResultados = "";
let base64File = null;

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

// ARCHIVOS (RECETA MÉDICA)
function previewFile() {
    const fileInput = document.getElementById('file-input');
    const previewContainer = document.getElementById('file-preview-container');
    const previewName = document.getElementById('file-preview-name');
    
    if (fileInput.files.length > 0) {
        const file = fileInput.files[0];
        previewName.textContent = file.name;
        previewContainer.style.display = 'flex';
        
        const reader = new FileReader();
        reader.onload = function(e) {
            base64File = e.target.result.split(',')[1];
        };
        reader.readAsDataURL(file);
    }
}

function clearFile() {
    document.getElementById('file-input').value = "";
    document.getElementById('file-preview-container').style.display = 'none';
    base64File = null;
}

// CHAT ASISTENTE
async function enviarMensaje() {
    const inp = document.getElementById('chat-input');
    const box = document.getElementById('chat-box');
    const prompt = inp.value;
    
    if(!prompt && !base64File) return;

    let userMsg = prompt ? prompt : "🖼️ Enviaste un documento/imagen";
    box.innerHTML += `<div class="msg-user"><b>Tú:</b> ${userMsg}</div>`;
    inp.value = "";
    box.scrollTop = box.scrollHeight;

    const fileToSend = base64File;
    clearFile();

    try {
        const r = await fetch('http://127.0.0.1:8000/consultar_asistente', {
            method: 'POST', 
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                pregunta: prompt, 
                contexto_precios: ultimosResultados,
                archivo_base64: fileToSend
            })
        });
        const data = await r.json();
        box.innerHTML += `<div class="msg-mathew"><b>Mathew:</b> ${data.respuesta}</div>`;
        box.scrollTop = box.scrollHeight;
    } catch { 
        box.innerHTML += `<div class="msg-mathew">Error de conexión con Mathew.</div>`; 
    }
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

// HISTORIAL (DURANTE LA NAVEGACIÓN SPA)
async function cargarHistorial() {
    const contenedor = document.getElementById('history-results');
    contenedor.innerHTML = "<p>⏳ Cargando registros del historial...</p>";
    
    // Mapeo estricto de colores por farmacia para mantener coherencia visual
    const coloresFarmacias = {
        "Ahumada": "#003399",
        "Dr. Simi": "#ce000c",
        "Salcobrand": "#ffd400"
    };

    try {
        const r = await fetch('http://127.0.0.1:8000/obtener_historial');
        const data = await r.json();
        
        if (data.length === 0) {
            contenedor.innerHTML = "<p style='color:var(--text-muted);'>No hay búsquedas registradas en el historial aún.</p>";
            return;
        }

        let html = "<table><tr><th>Búsqueda</th><th>Farmacia</th><th>Producto Encontrado</th><th>Precio</th><th>Fecha / Hora</th></tr>";
        data.forEach(row => {
            // row[0]=buscado, row[1]=farmacia, row[2]=nombre_producto, row[3]=precio, row[4]=fecha
            const farmaciaNombre = row[1];
            const colorColor = coloresFarmacias[farmaciaNombre] || "var(--text-main)";
            
            html += `<tr>
                <td style="font-weight:600; text-transform:capitalize;">${row[0]}</td>
                <td style="color:${colorColor}; font-weight:bold;">${farmaciaNombre}</td>
                <td style="color:var(--text-muted); font-size:0.95rem;">${row[2]}</td>
                <td style="font-weight:600;">$${row[3].toLocaleString('es-CL')}</td>
                <td style="font-size:0.9rem; color:var(--text-muted);">${row[4]}</td>
            </tr>`;
        });
        contenedor.innerHTML = html + "</table>";
    } catch {
        contenedor.innerHTML = "<p style='color:red;'>Error al conectar con la base de datos.</p>";
    }
}

// MAPA
function actualizarMapa(tipo) {
    if(navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(p => {
            const lat = p.coords.latitude, lng = p.coords.longitude;
            document.getElementById('map-iframe').src = `https://maps.google.com/maps?q=${tipo}&ll=${lat},${lng}&z=14&output=embed`;
        });
    }
}