document.addEventListener("DOMContentLoaded", () => {
  console.log("✅ Script cargado correctamente");

  // --- Campos generales ---
  const showPasswordCheckbox = document.getElementById("showPassword");
  const passwordInputs = document.querySelectorAll('input[type="password"]');

  // --- FORMULARIOS ---
  const registerForm = document.getElementById("registroForm");
  const loginForm = document.getElementById("loginForm");

  // ==========================
  // Mostrar / ocultar contraseña
  // ==========================
  if (showPasswordCheckbox && passwordInputs.length > 0) {
    showPasswordCheckbox.addEventListener("change", (e) => {
      const type = e.target.checked ? "text" : "password";
      passwordInputs.forEach((input) => {
        input.type = type;
      });
    });
  }

  // ==========================
  // Registro: Validaciones en tiempo real
  // ==========================
  if (registerForm) {
    const usernameInput = document.getElementById("username");
    const emailInput = document.getElementById("email");
    const passwordInput = document.getElementById("password");
    const confirmPasswordInput = document.getElementById("confirmPassword");

    const usernameFeedback = document.getElementById("usernameFeedback");
    const emailFeedback = document.getElementById("emailFeedback");
    const passwordStrengthFeedback = document.getElementById("passwordStrengthFeedback");
    const passwordFeedback = document.getElementById("passwordFeedback");

    let passwordStrengthValid = false;
    let passwordsMatch = false;

    // Validar fortaleza de contraseña (mínimo 6 caracteres)
    const validatePasswordStrength = () => {
      const pass = passwordInput.value.trim();
      
      if (!pass) {
        passwordStrengthFeedback.textContent = "";
        passwordStrengthValid = false;
        return false;
      }

      if (pass.length < 6) {
        passwordStrengthFeedback.textContent = "La contraseña debe tener al menos 6 caracteres.";
        passwordStrengthFeedback.className = "feedback error";
        passwordStrengthValid = false;
        return false;
      } else {
        passwordStrengthFeedback.textContent = "Contraseña válida.";
        passwordStrengthFeedback.className = "feedback success";
        passwordStrengthValid = true;
        return true;
      }
    };

    // Validar contraseñas iguales
    const validatePasswords = () => {
      const pass = passwordInput.value.trim();
      const confirm = confirmPasswordInput.value.trim();
      
      if (!confirm) {
        passwordFeedback.textContent = "";
        passwordsMatch = false;
        return false;
      }
      
      if (pass !== confirm) {
        passwordFeedback.textContent = "Las contraseñas no coinciden.";
        passwordFeedback.className = "feedback error";
        passwordsMatch = false;
        return false;
      } else {
        passwordFeedback.textContent = "Las contraseñas coinciden.";
        passwordFeedback.className = "feedback success";
        passwordsMatch = true;
        return true;
      }
    };

    passwordInput.addEventListener("input", () => {
      validatePasswordStrength();
      validatePasswords(); // Revalidar coincidencia cuando cambia la principal
    });

    confirmPasswordInput.addEventListener("input", validatePasswords);

    // Validar usuario
    usernameInput.addEventListener("input", () => {
      const username = usernameInput.value.trim();
      if (username.length < 3) {
        usernameFeedback.textContent = "";
        return;
      }

      fetch(`/check_username/?username=${encodeURIComponent(username)}`)
        .then(res => res.json())
        .then(data => {
          if (data.exists) {
            usernameFeedback.textContent = "Este nombre de usuario ya está en uso.";
            usernameFeedback.className = "feedback error";
          } else {
            usernameFeedback.textContent = "Nombre de usuario disponible.";
            usernameFeedback.className = "feedback success";
          }
        })
        .catch(err => console.error("Error al verificar usuario:", err));
    });

    // Validar correo
    emailInput.addEventListener("input", () => {
      const email = emailInput.value.trim();
      if (email.length < 5 || !email.includes("@")) {
        emailFeedback.textContent = "";
        return;
      }

      fetch(`/check_email/?email=${encodeURIComponent(email)}`)
        .then(res => res.json())
        .then(data => {
          if (data.exists) {
            emailFeedback.textContent = "Este correo ya está registrado.";
            emailFeedback.className = "feedback error";
          } else {
            emailFeedback.textContent = "Correo disponible.";
            emailFeedback.className = "feedback success";
          }
        })
        .catch(err => console.error("Error al verificar correo:", err));
    });

    // Validación final
    registerForm.addEventListener("submit", (e) => {
      if (!passwordStrengthValid) {
        e.preventDefault();
        alert("La contraseña debe tener al menos 6 caracteres.");
        return;
      }
      
      if (!passwordsMatch) {
        e.preventDefault();
        alert("Las contraseñas no coinciden.");
        return;
      }
    });
  }

  // ==========================
  // Login: Validación simple
  // ==========================
  if (loginForm) {
    loginForm.addEventListener("submit", (e) => {
      const username = loginForm.querySelector('input[name="username"]').value.trim();
      const password = loginForm.querySelector('input[name="password"]').value.trim();

      if (!username || !password) {
        e.preventDefault();
        alert("Por favor, completa todos los campos.");
      }
    });
  }
});