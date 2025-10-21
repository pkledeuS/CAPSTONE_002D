document.addEventListener("DOMContentLoaded", () => {
  console.log("✅ JS cargado correctamente");

  const loginForm = document.getElementById("loginForm");
  const registerForm = document.getElementById("registroForm");
  const passwordInput = document.getElementById("password");
  const showPasswordCheckbox = document.getElementById("showPassword");

  // ==========================
  // MOSTRAR / OCULTAR CONTRASEÑA
  // ==========================
  if (showPasswordCheckbox && passwordInput) {
    showPasswordCheckbox.addEventListener("change", (e) => {
      passwordInput.type = e.target.checked ? "text" : "password";
      console.log("🔁 Alternando visibilidad contraseña");
    });
  }

  // ==========================
  // VERIFICAR USUARIO EN TIEMPO REAL (solo registro)
  // ==========================
  if (registerForm) {
    const usernameInput = document.querySelector("input[name='username']");
    const feedback = document.getElementById("usernameFeedback");

    if (usernameInput && feedback) {
      usernameInput.addEventListener("input", () => {
        const username = usernameInput.value.trim();
        if (username.length < 3) {
          feedback.textContent = "";
          return;
        }

        fetch(`/check_username/?username=${encodeURIComponent(username)}`)
          .then((res) => res.json())
          .then((data) => {
            if (data.exists) {
              feedback.textContent = "Este nombre de usuario ya está en uso.";
              feedback.style.color = "red";
            } else {
              feedback.textContent = "Nombre de usuario disponible.";
              feedback.style.color = "green";
            }
          })
          .catch((err) => console.error("Error al verificar usuario:", err));
      });
    }

    registerForm.addEventListener("submit", (e) => {
      const email = document.querySelector("input[name='email']").value.trim();
      const password = document.querySelector("input[name='password']").value.trim();
      const username = document.querySelector("input[name='username']").value.trim();

      if (!username || !email || !password) {
        e.preventDefault();
        alert("Por favor completa todos los campos.");
      }
    });
  }

  // ==========================
  // VERIFICAR CORREO EN TIEMPO REAL (solo registro)
  // ==========================
  if (registerForm) {
    const emailInput = document.getElementById("email");
    const emailFeedback = document.getElementById("emailFeedback");

    if (emailInput && emailFeedback) {
      emailInput.addEventListener("input", () => {
        const email = emailInput.value.trim();
        if (email.length < 5 || !email.includes("@")) {
          emailFeedback.textContent = "";
          return;
        }

        fetch(`/check_email/?email=${encodeURIComponent(email)}`)
          .then((res) => res.json())
          .then((data) => {
            if (data.exists) {
              emailFeedback.textContent = "Este correo ya está registrado.";
              emailFeedback.style.color = "red";
            } else {
              emailFeedback.textContent = "Correo disponible.";
              emailFeedback.style.color = "green";
            }
          })
          .catch((err) => console.error("Error al verificar correo:", err));
      });
    }
  }

  // ==========================
  // RECORDAR USUARIO Y VALIDAR LOGIN (solo login)
  // ==========================
  if (loginForm) {
    const rememberCheckbox = document.getElementById("rememberMe");
    const usernameInput = document.querySelector("input[name='username']");

    if (rememberCheckbox && usernameInput) {
      const rememberedUser = localStorage.getItem("rememberedUser");
      if (rememberedUser) {
        usernameInput.value = rememberedUser;
        rememberCheckbox.checked = true;
      }

      loginForm.addEventListener("submit", () => {
        if (rememberCheckbox.checked) {
          localStorage.setItem("rememberedUser", usernameInput.value);
        } else {
          localStorage.removeItem("rememberedUser");
        }
      });
    }

    loginForm.addEventListener("submit", (e) => {
      const username = usernameInput?.value.trim();
      const password = passwordInput?.value.trim();
      if (!username || !password) {
        e.preventDefault();
        alert("Debes ingresar usuario y contraseña");
      }
    });
  }
});