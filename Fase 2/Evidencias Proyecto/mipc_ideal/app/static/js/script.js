document.addEventListener("DOMContentLoaded", () => {
  console.log("🔹 Login JS cargado correctamente");

  // ==========================
  // VARIABLES
  // ==========================
  const loginForm = document.getElementById("loginForm");
  if (!loginForm) return; // 👈 evita errores si no estamos en login.html

  const usernameInput = document.querySelector("input[name='username']");
  const passwordInput = document.getElementById("password");
  const rememberCheckbox = document.getElementById("rememberMe");
  const showPasswordCheckbox = document.getElementById("showPassword");

  // ==========================
  // MOSTRAR / OCULTAR CONTRASEÑA
  // ==========================
  if (showPasswordCheckbox && passwordInput) {
    showPasswordCheckbox.addEventListener("change", (e) => {
      passwordInput.type = e.target.checked ? "text" : "password";
    });
  }

  // ==========================
  // RECORDAR USUARIO
  // ==========================
  if (rememberCheckbox && usernameInput) {
    // Cargar usuario recordado si existe
    const rememberedUser = localStorage.getItem("rememberedUser");
    if (rememberedUser) {
      usernameInput.value = rememberedUser;
      rememberCheckbox.checked = true;
      console.log("Usuario recordado:", rememberedUser);
    }

    // Guardar o eliminar usuario al enviar el formulario
    loginForm.addEventListener("submit", () => {
      if (rememberCheckbox.checked) {
        localStorage.setItem("rememberedUser", usernameInput.value);
        console.log("Usuario recordado:", usernameInput.value);
      } else {
        localStorage.removeItem("rememberedUser");
        console.log("Usuario eliminado de localStorage");
      }
    });
  }

  // ==========================
  // VALIDACIÓN SIMPLE
  // ==========================
  loginForm.addEventListener("submit", (e) => {
    const username = usernameInput?.value.trim();
    const password = passwordInput?.value.trim();

    if (!username || !password) {
      e.preventDefault();
      alert("Debes ingresar usuario y contraseña");
    }
  });
});