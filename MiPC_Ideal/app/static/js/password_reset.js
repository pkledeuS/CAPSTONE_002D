document.addEventListener("DOMContentLoaded", () => {
  console.log("✅ Password reset script cargado");

  // --- FORMULARIOS ---
  const resetForm = document.getElementById("passwordResetForm");
  const confirmForm = document.getElementById("passwordResetConfirmForm");

  // --- Mostrar/ocultar contraseña ---
  const showPasswordCheckbox = document.getElementById("showPassword");
  const passwordInputs = document.querySelectorAll('.password-input');

  if (showPasswordCheckbox && passwordInputs.length > 0) {
    showPasswordCheckbox.addEventListener("change", (e) => {
      const type = e.target.checked ? "text" : "password";
      passwordInputs.forEach((input) => {
        input.type = type;
      });
    });
  }

  // ====================================
  // FORMULARIO 1: Verificar usuario y correo
  // ====================================
  if (resetForm) {
    const usernameInput = document.getElementById("username");
    const emailInput = document.getElementById("email");
    const usernameFeedback = document.getElementById("usernameFeedback");
    const emailFeedback = document.getElementById("emailFeedback");
    const submitBtn = document.getElementById("submitBtn");

    let usernameValid = false;
    let emailValid = false;

    // Validar que el usuario exista
    const validateUsername = () => {
      const username = usernameInput.value.trim();
      
      if (username.length < 3) {
        usernameFeedback.textContent = "";
        usernameValid = false;
        updateSubmitButton();
        return;
      }

      fetch(`/check_username/?username=${encodeURIComponent(username)}`)
        .then(res => res.json())
        .then(data => {
          if (data.exists) {
            usernameFeedback.textContent = "Usuario encontrado.";
            usernameFeedback.className = "feedback success";
            usernameValid = true;
          } else {
            usernameFeedback.textContent = "Este usuario no existe.";
            usernameFeedback.className = "feedback error";
            usernameValid = false;
          }
          updateSubmitButton();
        })
        .catch(err => {
          console.error("Error al verificar usuario:", err);
          usernameValid = false;
          updateSubmitButton();
        });
    };

    // Validar que el correo exista
    const validateEmail = () => {
      const email = emailInput.value.trim();
      
      if (email.length < 5 || !email.includes("@")) {
        emailFeedback.textContent = "";
        emailValid = false;
        updateSubmitButton();
        return;
      }

      fetch(`/check_email/?email=${encodeURIComponent(email)}`)
        .then(res => res.json())
        .then(data => {
          if (data.exists) {
            emailFeedback.textContent = "Correo encontrado.";
            emailFeedback.className = "feedback success";
            emailValid = true;
          } else {
            emailFeedback.textContent = "Este correo no está registrado.";
            emailFeedback.className = "feedback error";
            emailValid = false;
          }
          updateSubmitButton();
        })
        .catch(err => {
          console.error("Error al verificar correo:", err);
          emailValid = false;
          updateSubmitButton();
        });
    };

    // Habilitar/deshabilitar botón
    const updateSubmitButton = () => {
      if (usernameValid && emailValid) {
        submitBtn.disabled = false;
        submitBtn.style.opacity = "1";
        submitBtn.style.cursor = "pointer";
      } else {
        submitBtn.disabled = true;
        submitBtn.style.opacity = "0.6";
        submitBtn.style.cursor = "not-allowed";
      }
    };

    // Inicializar botón deshabilitado
    updateSubmitButton();

    // Event listeners
    usernameInput.addEventListener("input", validateUsername);
    emailInput.addEventListener("input", validateEmail);

    // Validación final al enviar
    resetForm.addEventListener("submit", (e) => {
      const username = usernameInput.value.trim();
      const email = emailInput.value.trim();

      if (!username || !email) {
        e.preventDefault();
        alert("Por favor, completa todos los campos.");
        return;
      }

      if (!usernameValid || !emailValid) {
        e.preventDefault();
        alert("Por favor, verifica que los datos sean correctos.");
      }
    });
  }

  // ====================================
  // FORMULARIO 2: Confirmar nueva contraseña
  // ====================================
  if (confirmForm) {
    const newPassword = document.getElementById("new_password");
    const confirmPassword = document.getElementById("confirm_password");
    const newPasswordFeedback = document.getElementById("newPasswordFeedback");
    const passwordFeedback = document.getElementById("passwordFeedback");
    const submitBtn = document.getElementById("submitBtn");

    let passwordStrengthValid = false;
    let passwordsMatch = false;

    // Validar fortaleza de contraseña
    const validatePasswordStrength = () => {
      const pass = newPassword.value.trim();
      
      if (!pass) {
        newPasswordFeedback.textContent = "";
        passwordStrengthValid = false;
        updateSubmitButton();
        return;
      }

      if (pass.length < 6) {
        newPasswordFeedback.textContent = "La contraseña debe tener al menos 6 caracteres.";
        newPasswordFeedback.className = "feedback error";
        passwordStrengthValid = false;
      } else {
        newPasswordFeedback.textContent = "Contraseña válida.";
        newPasswordFeedback.className = "feedback success";
        passwordStrengthValid = true;
      }
      
      updateSubmitButton();
      validatePasswordMatch(); // Revalidar match
    };

    // Validar que las contraseñas coincidan
    const validatePasswordMatch = () => {
      const pass = newPassword.value.trim();
      const confirm = confirmPassword.value.trim();
      
      if (!confirm) {
        passwordFeedback.textContent = "";
        passwordsMatch = false;
        updateSubmitButton();
        return;
      }
      
      if (pass !== confirm) {
        passwordFeedback.textContent = "Las contraseñas no coinciden.";
        passwordFeedback.className = "feedback error";
        passwordsMatch = false;
      } else {
        passwordFeedback.textContent = "Las contraseñas coinciden.";
        passwordFeedback.className = "feedback success";
        passwordsMatch = true;
      }
      
      updateSubmitButton();
    };

    // Habilitar/deshabilitar botón
    const updateSubmitButton = () => {
      if (passwordStrengthValid && passwordsMatch) {
        submitBtn.disabled = false;
        submitBtn.style.opacity = "1";
        submitBtn.style.cursor = "pointer";
      } else {
        submitBtn.disabled = true;
        submitBtn.style.opacity = "0.6";
        submitBtn.style.cursor = "not-allowed";
      }
    };

    // Inicializar botón deshabilitado
    updateSubmitButton();

    // Event listeners
    newPassword.addEventListener("input", validatePasswordStrength);
    confirmPassword.addEventListener("input", validatePasswordMatch);

    // Validación final al enviar
    confirmForm.addEventListener("submit", (e) => {
      if (!passwordStrengthValid || !passwordsMatch) {
        e.preventDefault();
        alert("Por favor, verifica que las contraseñas sean válidas y coincidan.");
      }
    });
  }
});