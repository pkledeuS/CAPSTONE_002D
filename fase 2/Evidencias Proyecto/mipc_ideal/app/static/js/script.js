// menú desplegable
const menuToggle = document.getElementById("menuToggle");
const menuOptions = document.getElementById("menuOptions");
const pw = document.getElementById('pwBootstrap');
const btn = document.getElementById('togglePassword');
const icon = document.getElementById('iconToggle');
const chk = document.getElementById('showChk');


document.addEventListener("DOMContentLoaded", () => {
    const usuarioRadio = document.getElementById("usuario");
    const tiendaRadio = document.getElementById("tienda");
    const serviciosSection = document.getElementById("serviciosSection");

    // Función que alterna la visibilidad de la sección de servicios
    function toggleServicios() {
        if (tiendaRadio.checked) {
            serviciosSection.style.display = "block";
        } else {
            serviciosSection.style.display = "none";
        }
    }

    // Escuchar cambios en los radio buttons
    usuarioRadio.addEventListener("change", toggleServicios);
    tiendaRadio.addEventListener("change", toggleServicios);

    // Ejecutar al cargar (por si ya hay un valor preseleccionado)
    toggleServicios();
});

document.addEventListener("DOMContentLoaded", () => {
    const usuarioRadio = document.getElementById("usuario");
    const tiendaRadio = document.getElementById("tienda");
    const serviciosSection = document.getElementById("serviciosSection");
    const interesesSection = document.querySelector(".container-check-list"); // tu sección de intereses

    // Función para alternar visibilidad
    function toggleSections() {
        if (tiendaRadio.checked) {
            // Mostrar servicios, ocultar intereses
            serviciosSection.style.display = "block";
            interesesSection.style.display = "none";
        } else {
            // Mostrar intereses, ocultar servicios
            serviciosSection.style.display = "none";
            interesesSection.style.display = "block";
        }
    }

    // Escuchar cambios en los radios
    usuarioRadio.addEventListener("change", toggleSections);
    tiendaRadio.addEventListener("change", toggleSections);

    // Ejecutar una vez al cargar la página
    toggleSections();
});


btn.addEventListener('click', () => {
  const showing = pw.type === 'text';
  pw.type = showing ? 'password' : 'text';
  btn.setAttribute('aria-pressed', (!showing).toString());
  // Cambia el icono: bi-eye -> bi-eye-slash
  icon.classList.toggle('bi-eye');
  icon.classList.toggle('bi-eye-slash');
  btn.title = showing ? 'Mostrar contraseña' : 'Ocultar contraseña';
});

// Sincronizar con checkbox opcional
chk.addEventListener('change', (e) => {
  pw.type = e.target.checked ? 'text' : 'password';
  // actualizar icono y aria-pressed para consistencia
  const showing = pw.type === 'text';
  icon.classList.toggle('bi-eye', !showing);
  icon.classList.toggle('bi-eye-slash', showing);
  btn.setAttribute('aria-pressed', showing.toString());
});
    
menuToggle.addEventListener("click", () => {
  menuOptions.style.display =
    menuOptions.style.display === "block" ? "none" : "block";
});

// Cierra el menú si haces clic fuera de él
window.addEventListener("click", (event) => {
  if (!menuToggle.contains(event.target) && !menuOptions.contains(event.target)) {
    menuOptions.style.display = "none";
  }
});

// formulario de búsqueda
document.getElementById("searchForm").addEventListener("submit", function(event) {
event.preventDefault();
const query = document.getElementById("searchInput").value.trim();
if (query) {
alert(`🔍 Buscando: ${query}`);
// Aquí podrías redirigir a una página de resultados o hacer una búsqueda en el sitio
}
});

// formulario de registro
document.getElementById("registroForm").addEventListener("submit", function(event) {
event.preventDefault();

const nombre = document.getElementById("nombre").value.trim();
const email = document.getElementById("email").value.trim();
const password = document.getElementById("password").value;
const confirmPassword = document.getElementById("confirmPassword").value;

if (password !== confirmPassword) {
alert("⚠️ Las contraseñas no coinciden");
return;
}

if (password.length < 6) {
alert("⚠️ La contraseña debe tener al menos 6 caracteres");
return;
}

// Simulación de éxito
alert(`✅ Registro exitoso\nBienvenido, ${nombre}`);

// Aquí podrías enviar los datos al servidor con fetch()
});

// formulario de inicio de sesión
document.getElementById("loginForm").addEventListener("submit", function(event) {
event.preventDefault();
const email = document.getElementById("loginEmail").value.trim();
const password = document.getElementById("loginPassword").value;
// Simulación de éxito
alert(`✅ Inicio de sesión exitoso\nBienvenido de nuevo`);
});

