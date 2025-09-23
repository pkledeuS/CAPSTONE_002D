// Funciones para manejar el overlay
let scrollPosition = 0;

// Hacer las funciones globalmente accesibles
window.showOverlay = function showOverlay() {
    const pageOverlay = document.getElementById('page-overlay');
    const body = document.body;
    
    // Solo proceder si el overlay no está ya visible
    if (pageOverlay.classList.contains('show')) {
        return;
    }
    
    // Guardar la posición actual del scroll
    scrollPosition = window.pageYOffset;
    
    pageOverlay.classList.add('show');
    body.classList.add('no-scroll');
    
    // Mantener la posición del scroll visualmente
    body.style.top = `-${scrollPosition}px`;
}

window.hideOverlay = function hideOverlay() {
    const pageOverlay = document.getElementById('page-overlay');
    const body = document.body;
    
    // Solo proceder si el overlay está realmente visible
    if (!pageOverlay.classList.contains('show')) {
        return;
    }
    
    pageOverlay.classList.remove('show');
    body.classList.remove('no-scroll');
    
    // Restaurar la posición del scroll solo si había una posición guardada
    body.style.top = '';
    if (scrollPosition !== undefined && scrollPosition !== null) {
        window.scrollTo(0, scrollPosition);
        scrollPosition = 0; // Resetear después de usar
    }
}