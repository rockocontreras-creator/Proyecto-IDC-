lucide.createIcons();
let ultimosResultados = "";
let base64File = null;
let miGrafico = null; // Instancia global para evitar duplicidad de render

// GESTIÓN DE MODO OSCURO
const themeBtn = document.getElementById('theme-toggle');
themeBtn.addEventListener('click', () => {
    const isDark = document.body.classList.toggle('dark-mode');
    document.getElementById('theme-icon').setAttribute('data-lucide', isDark ? 'sun' : 'moon');
    localStorage.setItem('theme', isDark ? 'dark' : 'light');
    lucide.createIcons();
    if(miGrafico) cargarHistorialFiltrado(); // Redibuja el gráfico adaptando colores de fuentes
});
if(localStorage.getItem('theme') === 'dark') document.body.classList.add('dark-mode');

function showSection(id, btn) {
    document.querySelectorAll('.content-section').forEach(s => s.classList.remove('active-section'));
    document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
    document.getElementById(id + '-section').classList.add('active-section');
    btn.classList.add('active');
}

// CONTROL DE ARCHIVOS ADJUNTOS
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

// CHAT CON LA IA
async function enviarMensaje() {
    const inp = document.getElementById('chat-input');
    const box = document.getElementById('chat-box');
    const prompt = inp.value;
    
    if(!prompt && !base64File) return;

    let userMsg = prompt ? prompt : "🖼️ Imagen/Receta enviada";
    box.innerHTML += `<div class="msg-user"><b>Tú:</b> ${userMsg}</div>`;
    inp.value = "";
    box.scrollTop = box.scrollHeight;

    const fileToSend = base64File;
    clearFile();

    try {
        const r = await fetch('http://127.0.0.1:8000/consultar_asistente', {
            method: 'POST', 
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ pregunta: prompt, contexto_precios: ultimosResultados, archivo_base64: fileToSend })
        });
        const data = await r.json();
        box.innerHTML += `<div class="msg-mathew"><b>Mathew:</b> ${data.respuesta}</div>`;
        box.scrollTop = box.scrollHeight;
    } catch { 
        box.innerHTML += `<div class="msg-mathew">No se pudo contactar al asistente.</div>`; 
    }
}

// MOTOR DE COMPARACIÓN (SCRAPING)
async function startScraping() {
    const q = document.getElementById('manual-search').value;
    const res = document.getElementById('scraping-results');
    if(!q) return;
    res.innerHTML = "<p style='margin-top:20px; color:var(--text-muted);'>⏳ Analizando catálogos de farmacias chilenas...</p>";
    try {
        const r = await fetch('http://127.0.0.1:8000/scraping_manual', {
            method: 'POST', headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({remedio: q})
        });
        const data = await r.json();
        ultimosResultados = JSON.stringify(data.precios);
        let html = "<table><tr><th>Farmacia</th><th>Producto Encontrado</th><th>Precio</th><th>Acción</th></tr>";
        data.precios.forEach(p => {
            html += `<tr><td style="color:${p.color}; font-weight:bold;">${p.farmacia}</td><td>${p.nombre}</td><td style="font-weight:600;">$${p.precio}</td><td><a href="${p.link}" target="_blank" style="color:var(--primary); font-weight:600; text-decoration:none;">Ver Producto ↗</a></td></tr>`;
        });
        res.innerHTML = html + "</table>";
    } catch { res.innerHTML = "<p style='color:red;'>El servidor de scraping no responde.</p>"; }
}

// --- SISTEMA INTERACTIVO DE PRECIO HISTÓRICO ---

async function abrirHistorial(btn) {
    showSection('history', btn);
    await inicializarSelector();
}

async function inicializarSelector() {
    const selector = document.getElementById('med-selector');
    try {
        const r = await fetch('http://127.0.0.1:8000/obtener_medicamentos');
        const medicamentos = await r.json();
        
        selector.innerHTML = '<option value="">-- Elige un medicamento --</option>';
        
        if(medicamentos.length === 0) {
            selector.innerHTML = '<option value="">Sin registros todavía</option>';
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
    if(!medSeleccionado) return;

    try {
        const r = await fetch(`http://127.0.0.1:8000/obtener_historial?medicamento=${encodeURIComponent(medSeleccionado)}`);
        const data = await r.json();
        
        if (data.length === 0) return;

        // Eje X: Marcas de tiempo formateadas (Extraemos solo Hora y Minutos hh:mm)
        const etiquetasFechas = [...new Set(data.map(row => row[4].substring(11, 16)))];

        let preciosAhumada = [];
        let preciosSimi = [];
        let preciosSalcobrand = [];

        etiquetasFechas.forEach(f => {
            const regAhumada = data.find(row => row[1] === "Ahumada" && row[4].includes(f));
            const regSimi = data.find(row => row[1] === "Dr. Simi" && row[4].includes(f));
            const regSalcobrand = data.find(row => row[1] === "Salcobrand" && row[4].includes(f));

            preciosAhumada.push(regAhumada ? regAhumada[3] : null);
            preciosSimi.push(regSimi ? regSimi[3] : null);
            preciosSalcobrand.push(regSalcobrand ? regSalcobrand[3] : null);
        });

        if (miGrafico) { miGrafico.destroy(); }

        const ctx = document.getElementById('historyChart').getContext('2d');
        const modoOscuroActivo = document.body.classList.contains('dark-mode');

        miGrafico = new Chart(ctx, {
            type: 'line',
            data: {
                labels: etiquetasFechas,
                datasets: [
                    { label: 'Ahumada', data: preciosAhumada, borderColor: '#003399', backgroundColor: '#003399', tension: 0.2, spanGaps: true, pointRadius: 4 },
                    { label: 'Dr. Simi', data: preciosSimi, borderColor: '#ce000c', backgroundColor: '#ce000c', tension: 0.2, spanGaps: true, pointRadius: 4 },
                    { label: 'Salcobrand', data: preciosSalcobrand, borderColor: '#ffd400', backgroundColor: '#ffd400', tension: 0.2, spanGaps: true, pointRadius: 4 }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { labels: { color: modoOscuroActivo ? '#f1f5f9' : '#1e293b', font: { weight: '600' } } }
                },
                scales: {
                    x: { ticks: { color: modoOscuroActivo ? '#94a3b8' : '#64748b' }, grid: { color: modoOscuroActivo ? '#334155' : '#e2e8f0' } },
                    y: { ticks: { color: modoOscuroActivo ? '#94a3b8' : '#64748b', callback: (v) => '$' + v }, grid: { color: modoOscuroActivo ? '#334155' : '#e2e8f0' } }
                }
            }
        });
    } catch (e) {
        console.error("Error crítico al renderizar el gráfico:", e);
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