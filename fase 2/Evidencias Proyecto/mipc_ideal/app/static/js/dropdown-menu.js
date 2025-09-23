document.addEventListener('DOMContentLoaded', function() {
    // === ELEMENTOS DOM ===
    const themeIcon = document.getElementById('theme-icon');
    const themeDropdown = document.getElementById('theme-dropdown');
    const themeContainer = document.getElementById('theme-menu-container');
    const categoryContainer = document.getElementById('category-menu-container');
    const categoryDropdown = document.getElementById('category-dropdown');
    const pageOverlay = document.getElementById('page-overlay');
    
    // === MENÚ DE TEMAS/CONFIGURACIÓN ===
    
    // Función para mostrar el menú de temas
    function showThemeMenu() {
        themeDropdown.classList.add('show');
        showOverlay();
    }
    
    // Función para ocultar el menú de temas
    function hideThemeMenu() {
        themeDropdown.classList.remove('show');
        if (pageOverlay.classList.contains('show')) {
            hideOverlay();
        }
    }
    
    // Función para alternar el menú de temas
    function toggleThemeMenu() {
        if (themeDropdown.classList.contains('show')) {
            hideThemeMenu();
        } else {
            showThemeMenu();
        }
    }
    
    // Event listeners para menú de temas
    if (themeContainer) {
        themeContainer.addEventListener('click', function(e) {
            e.stopPropagation();
            toggleThemeMenu();
        });
    }
    
    // Manejar clicks en las opciones de tema
    const themeOptions = themeDropdown.querySelectorAll('a[data-theme]');
    themeOptions.forEach(option => {
        option.addEventListener('click', function(e) {
            e.preventDefault();
            const selectedTheme = this.getAttribute('data-theme');
            applyTheme(selectedTheme);
            hideThemeMenu();
        });
    });
    
    // === MENÚ DE CATEGORÍAS ===
    
    // Función para mostrar el menú de categorías
    function showCategoryMenu() {
        categoryDropdown.classList.add('show');
        showOverlay();
    }
    
    // Función para ocultar el menú de categorías
    function hideCategoryMenu() {
        categoryDropdown.classList.remove('show');
        if (pageOverlay.classList.contains('show')) {
            hideOverlay();
        }
    }
    
    // Función para alternar el menú de categorías
    function toggleCategoryMenu() {
        if (categoryDropdown.classList.contains('show')) {
            hideCategoryMenu();
        } else {
            showCategoryMenu();
        }
    }
    
    // Event listeners para menú de categorías
    if (categoryContainer) {
        categoryContainer.addEventListener('click', function(e) {
            e.stopPropagation();
            toggleCategoryMenu();
        });
    }
    
    // Manejar clicks en las opciones de categorías
    const categoryOptions = categoryDropdown?.querySelectorAll('a');
    categoryOptions?.forEach(option => {
        option.addEventListener('click', function(e) {
            e.preventDefault();
            const categoryText = this.textContent.trim();
            console.log('Categoría seleccionada:', categoryText);
            hideCategoryMenu();
        });
    });
    
    // === EVENT LISTENERS GLOBALES ===
    
    // Cerrar menús al hacer click fuera de ellos
    document.addEventListener('click', function(e) {
        if (themeContainer && !themeContainer.contains(e.target) && 
            !themeDropdown.contains(e.target)) {
            hideThemeMenu();
        }
        
        if (categoryContainer && !categoryContainer.contains(e.target) && 
            !categoryDropdown.contains(e.target)) {
            hideCategoryMenu();
        }
    });
    
    // Cerrar menús con tecla Escape
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            hideThemeMenu();
            hideCategoryMenu();
        }
    });
    
    // Cerrar menús al hacer click en el overlay
    if (pageOverlay) {
        pageOverlay.addEventListener('click', function() {
            hideThemeMenu();
            hideCategoryMenu();
        });
    }
});