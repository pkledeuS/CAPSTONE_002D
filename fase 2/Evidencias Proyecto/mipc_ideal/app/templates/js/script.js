// menú desplegable
const menuToggle = document.getElementById("menuToggle");
const menuOptions = document.getElementById("menuOptions");

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

