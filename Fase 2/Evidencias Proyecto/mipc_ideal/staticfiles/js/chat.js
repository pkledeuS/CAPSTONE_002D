(function () {
  // --- CSRF helper ---
  function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== "") {
      const cookies = document.cookie.split(";");
      for (let i = 0; i < cookies.length; i++) {
        const cookie = cookies[i].trim();
        if (cookie.substring(0, name.length + 1) === name + "=") {
          cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
          break;
        }
      }
    }
    return cookieValue;
  }
  const csrftoken = getCookie("csrftoken");

  const $panel = document.getElementById("chat-panel");
  const $toggle = document.getElementById("chat-toggle");
  const $close = document.getElementById("chat-close");
  const $msgs = document.getElementById("chat-messages");
  const $input = document.getElementById("chat-input");
  const $send = document.getElementById("chat-send");

  if (!$panel || !$toggle) return;

  function appendMsg(role, text) {
    const wrap = document.createElement("div");
    wrap.className = `msg ${role}`;
    const bubble = document.createElement("div");
    bubble.className = "bubble";
    bubble.textContent = text;
    wrap.appendChild(bubble);
    $msgs.appendChild(wrap);
    $msgs.scrollTop = $msgs.scrollHeight;
  }

  function appendProduct(p) {
    const card = document.createElement("div");
    card.className = "product-card";
    if (p.image) {
      const img = document.createElement("img");
      img.src = p.image;
      img.alt = p.name;
      card.appendChild(img);
    }
    const meta = document.createElement("div");
    meta.className = "meta";
    const price = p.price ? ` — $${p.price.toLocaleString("es-CL")}` : "";
    meta.innerHTML = `<div><strong>${p.name}</strong>${price}</div>
                      <div>${p.desc || ""}</div>
                      <div><a href="${p.detail}" class="btn btn-sm btn-primary" style="margin-top:6px;">Ver más</a></div>`;
    card.appendChild(meta);
    $msgs.appendChild(card);
    $msgs.scrollTop = $msgs.scrollHeight;
  }

  async function send() {
    const text = ($input.value || "").trim();
    if (!text) return;
    appendMsg("user", text);
    $input.value = "";

    try {
      const res = await fetch("/chat/ask/", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrftoken
        },
        body: JSON.stringify({ message: text })
      });
      const data = await res.json();
      if (!res.ok) {
        appendMsg("assistant", data.error || "Error al procesar tu mensaje.");
        return;
      }
      if (data.reply) appendMsg("assistant", data.reply);
      if (Array.isArray(data.products)) {
        data.products.forEach(appendProduct);
      }
    } catch (e) {
      appendMsg("assistant", "Ocurrió un problema de red.");
    }
  }

  $toggle.addEventListener("click", () => $panel.classList.toggle("hidden"));
  if ($close) $close.addEventListener("click", () => $panel.classList.add("hidden"));
  $send.addEventListener("click", send);
  $input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") send();
  });
})();