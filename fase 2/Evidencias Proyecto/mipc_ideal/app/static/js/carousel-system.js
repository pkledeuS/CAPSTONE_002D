document.addEventListener('DOMContentLoaded', function() {
    // Inicializar todos los carruseles en la página
    const carousels = document.querySelectorAll('.carousel');
    
    if (!carousels || carousels.length === 0) {
        console.warn('No se encontraron carruseles en la página');
        return;
    }
    
    carousels.forEach((carousel, carouselIndex) => {
        try {
            const inner = carousel.querySelector('.carousel-inner');
            if (!inner) {
                console.warn(`Carrusel #${carouselIndex + 1}: No se encontró el elemento .carousel-inner`);
                return;
            }
            
            const items = carousel.querySelectorAll('.carousel-item');
            if (!items || items.length === 0) {
                console.warn(`Carrusel #${carouselIndex + 1}: No se encontraron elementos .carousel-item`);
                return;
            }
            
            const prevBtn = carousel.querySelector('.prev');
            const nextBtn = carousel.querySelector('.next');
            
            if (!prevBtn || !nextBtn) {
                console.warn(`Carrusel #${carouselIndex + 1}: Faltan botones de navegación`);
            }
            
            let currentIndex = 0;
            let isAnimating = false;
            
            // Clonar el primer elemento y añadirlo al final para transición suave
            const firstItemClone = items[0].cloneNode(true);
            inner.appendChild(firstItemClone);
            
            // Función para mostrar un slide específico con animación
            function showSlide(index, direction = 'next') {
                if (isAnimating) return;
                isAnimating = true;
                
                // Asegurar transición suave
                inner.style.transition = 'transform 0.5s ease';
                
                if (direction === 'next') {
                    // Lógica de avanzar
                    if (currentIndex === items.length - 1 && index === 0) {
                        inner.style.transform = `translateX(-${items.length * 100}%)`;
                        setTimeout(() => {
                            inner.style.transition = 'none';
                            inner.style.transform = 'translateX(0)';
                            currentIndex = 0;
                            setTimeout(() => {
                                inner.style.transition = 'transform 0.5s ease';
                                isAnimating = false;
                            }, 50);
                        }, 500);
                    } else {
                        currentIndex = index;
                        inner.style.transform = `translateX(-${currentIndex * 100}%)`;
                        setTimeout(() => {
                            isAnimating = false;
                        }, 500);
                    }
                } else {
                    // Lógica de retroceder
                    if (currentIndex === 0 && index === items.length - 1) {
                        inner.style.transition = 'none';
                        inner.style.transform = `translateX(-${items.length * 100}%)`;
                        inner.offsetHeight;
                        setTimeout(() => {
                            inner.style.transition = 'transform 0.5s ease';
                            inner.style.transform = `translateX(-${(items.length - 1) * 100}%)`;
                            currentIndex = items.length - 1;
                            setTimeout(() => {
                                isAnimating = false;
                            }, 500);
                        }, 20);
                    } else {
                        currentIndex = index;
                        inner.style.transform = `translateX(-${currentIndex * 100}%)`;
                        setTimeout(() => {
                            isAnimating = false;
                        }, 500);
                    }
                }
            }
            
            // Variable para controlar el intervalo
            let interval;
            
            // Función para avanzar al siguiente slide
            function nextSlide(e) {
                if (e) {
                    e.preventDefault();
                    e.stopPropagation();
                    // Pausar auto-rotación cuando el usuario hace click manualmente
                    if (interval) {
                        clearInterval(interval);
                        setTimeout(() => {
                            if (items.length > 1) {
                                interval = setInterval(nextSlide, 5000);
                            }
                        }, 3000);
                    }
                }
                try {
                    const newIndex = currentIndex === items.length - 1 ? 0 : currentIndex + 1;
                    showSlide(newIndex, 'next');
                } catch (err) {
                    console.error(`Error en nextSlide del carrusel #${carouselIndex + 1}:`, err);
                }
            }
            
            // Función para retroceder al slide anterior
            function prevSlide(e) {
                if (e) {
                    e.preventDefault();
                    e.stopPropagation();
                    if (interval) {
                        clearInterval(interval);
                        setTimeout(() => {
                            if (items.length > 1) {
                                interval = setInterval(nextSlide, 5000);
                            }
                        }, 3000);
                    }
                }
                try {
                    const newIndex = currentIndex === 0 ? items.length - 1 : currentIndex - 1;
                    showSlide(newIndex, 'prev');
                } catch (err) {
                    console.error(`Error en prevSlide del carrusel #${carouselIndex + 1}:`, err);
                }
            }
            
            // Configurar los event listeners para los botones
            if (nextBtn && prevBtn) {
                nextBtn.addEventListener('click', nextSlide);
                prevBtn.addEventListener('click', prevSlide);
            }
            
            // Mostrar el primer slide
            inner.style.transform = 'translateX(0)';
            
            // Solo activar la auto-rotación si hay más de un elemento
            if (items.length > 1) {
                interval = setInterval(nextSlide, 5000);
                
                // Detener auto rotación cuando el usuario interactúa
                carousel.addEventListener('mouseenter', () => {
                    clearInterval(interval);
                });
                
                // Reiniciar auto rotación cuando el usuario deja de interactuar
                carousel.addEventListener('mouseleave', () => {
                    interval = setInterval(nextSlide, 5000);
                });
            }
        } catch (error) {
            console.error(`Error al inicializar el carrusel #${carouselIndex + 1}:`, error);
        }
    });
});