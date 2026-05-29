lucide.createIcons();
let ultimosResultados = "";
let base64File = null;
let miGrafico = null; // Patrón Singleton: Instancia global para evitar duplicidad de renderizado

// GESTIÓN DE MODO OSCURO
const themeBtn = document.getElementById('theme-toggle');
themeBtn.addEventListener('click', () => {
    const isDark = document.body.classList.toggle('dark-mode');
    document.getElementById('theme-icon').setAttribute('data-lucide', isDark ? 'sun' : 'moon');
    localStorage.setItem('theme', isDark ? 'dark' : 'light');
    lucide.createIcons();
    if(miGrafico) cargarHistorialFiltrado(); // Redibuja el gráfico adaptando colores de fuentes de inmediato
});
if(localStorage.getItem('theme') === 'dark') document.body.classList.add('dark-mode');

function showSection(id, btn) {
    document.querySelectorAll('.content-section').forEach(s => s.classList.remove('active-section'));
    document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
    document.getElementById(id + '-section').classList.add('active-section');
    btn.classList.add('active');
}

// CONTROL DE ARCHIVOS ADJUNTOS (RECETAS)
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

// INTERACCIÓN CON ASISTENTE VIRTUAL MATHEW IA
async function enviarMensaje() {
    const inp = document.getElementById('chat-input');
    const box = document.getElementById('chat-box');
    const prompt = inp.value.trim();
    
    if(!prompt && !base64File) return;

    let userMsg = prompt ? prompt : "🖼️ Imagen de Receta Médica enviada";
    box.innerHTML += `<div class="message message-user"><b>Tú:</b> ${userMsg}</div>`;
    inp.value = "";
    box.scrollTop = box.scrollHeight;

    // Bloqueo de controles para evitar saturación de peticiones concurrentes
    inp.disabled = true;
    const sendBtn = inp.nextElementSibling;
    if(sendBtn) sendBtn.disabled = true;

    const fileToSend = base64File;
    clearFile();

    // Crear burbuja de carga temporal para Mathew
    const loadingDiv = document.createElement('div');
    loadingDiv.className = 'message message-mathew loading-msg';
    loadingDiv.innerHTML = '⚡ <i>Mathew está analizando los registros...</i>';
    box.appendChild(loadingDiv);
    box.scrollTop = box.scrollHeight;

    try {
        const r = await fetch('http://127.0.0.1:8000/consultar_asistente', {
            method: 'POST', 
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ pregunta: prompt, contexto_precios: ultimosResultados, archivo_base64: fileToSend })
        });
        const data = await r.json();
        
        // Quitar mensaje de carga
        loadingDiv.remove();

        // Renderizado Profesional: Convertimos el Markdown de Groq en HTML real
        const respuestaDiv = document.createElement('div');
        respuestaDiv.className = 'message message-mathew';
        respuestaDiv.innerHTML = `<b>Mathew:</b> ${marked.parse(data.respuesta)}`;
        
        box.appendChild(respuestaDiv);
        box.scrollTop = box.scrollHeight;
    } catch (err) { 
        loadingDiv.remove();
        box.innerHTML += `<div class="message message-mathew" style="color:var(--text-muted);">No se pudo establecer la conexión con los protocolos de Mathew.</div>`; 
    } finally {
        // Desbloqueo de componentes interactivos
        inp.disabled = false;
        if(sendBtn) sendBtn.disabled = false;
        inp.focus();
    }
}

// MOTOR DE COMPARACIÓN EN TIEMPO REAL (CON SKELETON LOADING)
async function startScraping() {
    const q = document.getElementById('manual-search').value.trim();
    const res = document.getElementById('scraping-results');
    const searchBtn = document.querySelector('.search-bar-box button');
    if(!q) return;
    
    // Bloquear controles visuales
    searchBtn.disabled = true;
    
    // Inyección de un esqueleto de carga técnico (Skeleton Screen) para simular la estructura
    res.innerHTML = `
        <div style="width: 100%; border: 1px solid var(--border); border-radius: 12px; overflow: hidden; animation: fadeIn 0.3s;">
            <div style="background: var(--border); height: 45px; width: 100%; padding: 12px; font-weight: 600; font-size: 0.85rem; color: var(--text-muted);">⏳ CONECTANDO CON LOS HILOS DE SELENIUM EN CONSOLA...</div>
            <div style="padding: 20px; display: flex; flex-direction: column; gap: 12px; background: var(--card-bg);">
                <div style="height: 20px; background: var(--border); border-radius: 4px; opacity: 0.6; animation: pulse 1.5s infinite;"></div>
                <div style="height: 20px; background: var(--border); border-radius: 4px; opacity: 0.4; animation: pulse 1.5s infinite 0.2s;"></div>
                <div style="height: 20px; background: var(--border); border-radius: 4px; opacity: 0.2; animation: pulse 1.5s infinite 0.4s;"></div>
            </div>
        </div>
    `;
    
    try {
        const r = await fetch('http://127.0.0.1:8000/scraping_manual', {
            method: 'POST', 
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({remedio: q})
        });
        const data = await r.json();
        ultimosResultados = JSON.stringify(data.precios);
        
        if(!data.precios || data.precios.length === 0) {
            res.innerHTML = "<p style='color:var(--text-muted); padding: 10px;'>No se encontraron ofertas comerciales para este término en las cadenas analizadas.</p>";
            return;
        }

        // Construcción de la tabla estructurada en 3FN
        let html = "<table><tr><th>Farmacia</th><th>Producto Encontrado</th><th>Precio Registrado</th><th>Acción Comercial</th></tr>";
        data.precios.forEach(p => {
            html += `<tr>
                <td style="color:${p.color}; font-weight:bold; letter-spacing: 0.02em;">${p.farmacia}</td>
                <td style="font-weight: 500;">${p.nombre}</td>
                <td style="font-weight:700; color: #10b981;">$${p.precio} CLP</td>
                <td><a href="${p.link}" target="_blank" class="btn-premium" style="padding: 6px 12px; font-size: 0.85rem; display: inline-flex; text-decoration:none;">Ir a la web ↗</a></td>
            </tr>`;
        });
        res.innerHTML = html + "</table>";
    } catch { 
        res.innerHTML = "<p style='color:var(--text-muted);'>El micro-framework de Flask en el puerto 8000 no responde.</p>"; 
    } finally {
        searchBtn.disabled = false;
    }
}

// --- SISTEMA INTERACTIVO DE HISTORIAL RELACIONAL ---
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
        console.error("Error cargando selector relacional:", e);
    }
}

async function cargarHistorialFiltrado() {
    const medSeleccionado = document.getElementById('med-selector').value;
    if(!medSeleccionado) return;

    try {
        const r = await fetch(`http://127.0.0.1:8000/obtener_historial?medicamento=${encodeURIComponent(medSeleccionado)}`);
        const data = await r.json();
        
        if (data.length === 0) return;

        // Extraemos marcas de tiempo unívocas (Muestreos de Hora y Minutos hh:mm)
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

        // Aplicación estricta del patrón Singleton: destruimos el objeto gráfico previo para liberar la pila de renderizado
        if (miGrafico) { miGrafico.destroy(); }

        const ctx = document.getElementById('historyChart').getContext('2d');
        const modoOscuroActivo = document.body.classList.contains('dark-mode');

        miGrafico = new Chart(ctx, {
            type: 'line',
            data: {
                labels: etiquetasFechas,
                datasets: [
                    { label: 'Ahumada', data: preciosAhumada, borderColor: '#003399', backgroundColor: '#003399', tension: 0.2, spanGaps: true, pointRadius: 5, borderWidth: 3 },
                    { label: 'Dr. Simi', data: preciosSimi, borderColor: '#ce000c', backgroundColor: '#ce000c', tension: 0.2, spanGaps: true, pointRadius: 5, borderWidth: 3 },
                    { label: 'Salcobrand', data: preciosSalcobrand, borderColor: '#ffd400', backgroundColor: '#ffd400', tension: 0.2, spanGaps: true, pointRadius: 5, borderWidth: 3 }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { labels: { color: modoOscuroActivo ? '#f1f5f9' : '#1e293b', font: { family: 'Inter', weight: '600', size: 12 } } }
                },
                scales: {
                    x: { ticks: { color: modoOscuroActivo ? '#94a3b8' : '#64748b' }, grid: { color: modoOscuroActivo ? '#334155' : '#e2e8f0' } },
                    y: { ticks: { color: modoOscuroActivo ? '#94a3b8' : '#64748b', callback: (v) => '$' + v + ' CLP' }, grid: { color: modoOscuroActivo ? '#334155' : '#e2e8f0' } }
                }
            }
        });
    } catch (e) {
        console.error("Error crítico en el render de Chart.js:", e);
    }
}

// COMPONENTE DE GEOLOCALIZACIÓN CLÍNICA
function actualizarMapa(tipo) {
    if(navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(p => {
            const lat = p.coords.latitude, lng = p.coords.longitude;
            document.getElementById('map-iframe').src = `https://maps.google.com/maps?q=${tipo}&ll=${lat},${lng}&z=14&output=embed`;
        }, () => {
            // Fallback UI si el usuario deniega los accesos de geolocalización (Usa coordenadas céntricas por defecto)
            document.getElementById('map-iframe').src = `https://maps.google.com/maps?q=${tipo}&z=13&output=embed`;
        });
    }
}