// Obtener tema guardado o usar 'light' por defecto
let currentTheme = localStorage.getItem('theme') || 'light';

// Aplicar tema al cargar la página - función global
window.applyTheme = function applyTheme(theme) {
    const body = document.body;
    
    // Remover todas las clases de tema
    body.classList.remove('light-theme', 'dark-theme');
    
    // Aplicar el tema seleccionado
    if (theme === 'dark') {
        body.classList.add('dark-theme');
    } else if (theme === 'auto') {
        // Detectar preferencia del sistema
        const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        if (prefersDark) {
            body.classList.add('dark-theme');
        }
    }
    
    // Actualizar checkmarks
    updateCheckmarks(theme);
    
    // Guardar tema en localStorage
    localStorage.setItem('theme', theme);
    currentTheme = theme;
}

// Actualizar los checkmarks del menú
function updateCheckmarks(activeTheme) {
    const checkmarks = document.querySelectorAll('.checkmark');
    checkmarks.forEach(check => check.classList.remove('active'));
    
    const activeCheck = document.getElementById(activeTheme + '-check');
    if (activeCheck) {
        activeCheck.classList.add('active');
    }
}

// Escuchar cambios en la preferencia del sistema (solo para modo automático)
window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', function(e) {
    if (currentTheme === 'auto') {
        applyTheme('auto');
    }
});

// Aplicar tema inicial cuando se carga la página
document.addEventListener('DOMContentLoaded', function() {
    applyTheme(currentTheme);
});