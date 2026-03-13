const API_BASE = "http://127.0.0.1:8000/api";

const loginForm = document.getElementById("loginForm");
const otpForm = document.getElementById("otpForm");
const resetStartForm = document.getElementById("resetStartForm");
const resetVerifyForm = document.getElementById("resetVerifyForm");
const resetCompleteForm = document.getElementById("resetCompleteForm");
const messageBox = document.getElementById("messageBox");

const forgotBtn = document.getElementById("forgotBtn");
const backToLoginBtn = document.getElementById("backToLoginBtn");
const cancelResetStartBtn = document.getElementById("cancelResetStartBtn");
const cancelResetVerifyBtn = document.getElementById("cancelResetVerifyBtn");
const cancelResetCompleteBtn = document.getElementById("cancelResetCompleteBtn");

let loginChallengeId = "";
let resetChallengeId = "";
let resetCode = "";

function showMessage(text, type = "info") {
  messageBox.className = `message ${type}`;
  messageBox.textContent = text;
  messageBox.classList.remove("hidden");
}

function clearMessage() {
  messageBox.className = "message info hidden";
  messageBox.textContent = "";
}

function showOnly(section) {
  [loginForm, otpForm, resetStartForm, resetVerifyForm, resetCompleteForm].forEach(el => {
    el.classList.add("hidden");
  });
  section.classList.remove("hidden");
  clearMessage();
}

async function apiFetch(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {})
    },
    ...options
  });

  const data = await response.json().catch(() => ({}));
  return { response, data };
}

async function checkSession() {
  try {
    const { response } = await apiFetch("/auth/me", { method: "GET" });
    if (response.ok) {
      window.location.href = "./index.html";
    }
  } catch (_) {}
}

loginForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  clearMessage();

  const email = document.getElementById("email").value.trim();
  const password = document.getElementById("password").value.trim();

  const { data } = await apiFetch("/auth/login/start", {
    method: "POST",
    body: JSON.stringify({ email, password })
  });

  if (!data.success) {
    showMessage(data.message || "No fue posible iniciar sesión.", "error");
    return;
  }

  if (data.otp_required) {
    loginChallengeId = data.challengeId;
    showOnly(otpForm);
    showMessage(data.message || "Te enviamos un código al correo.", "success");
    return;
  }

  window.location.href = "./index.html";
});

otpForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  clearMessage();

  const code = document.getElementById("otpCode").value.trim();

  const { data } = await apiFetch("/auth/login/verify", {
    method: "POST",
    body: JSON.stringify({ challengeId: loginChallengeId, code })
  });

  if (!data.success) {
    showMessage(data.message || "Código inválido.", "error");
    return;
  }

  window.location.href = "./index.html";
});

forgotBtn.addEventListener("click", () => {
  document.getElementById("resetEmail").value = document.getElementById("email").value.trim();
  showOnly(resetStartForm);
});

backToLoginBtn.addEventListener("click", () => showOnly(loginForm));
cancelResetStartBtn.addEventListener("click", () => showOnly(loginForm));
cancelResetVerifyBtn.addEventListener("click", () => showOnly(loginForm));
cancelResetCompleteBtn.addEventListener("click", () => showOnly(loginForm));

resetStartForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  clearMessage();

  const email = document.getElementById("resetEmail").value.trim();

  const { data } = await apiFetch("/auth/password-reset/start", {
    method: "POST",
    body: JSON.stringify({ email })
  });

  if (!data.success) {
    showMessage(data.message || "No se pudo enviar el código.", "error");
    return;
  }

  resetChallengeId = data.challengeId || "";
  showOnly(resetVerifyForm);
  showMessage(data.message || "Si el correo existe, se enviará un código.", "success");
});

resetVerifyForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  clearMessage();

  resetCode = document.getElementById("resetCode").value.trim();

  const { data } = await apiFetch("/auth/password-reset/verify", {
    method: "POST",
    body: JSON.stringify({
      challengeId: resetChallengeId,
      code: resetCode
    })
  });

  if (!data.success) {
    showMessage(data.message || "Código inválido.", "error");
    return;
  }

  showOnly(resetCompleteForm);
  showMessage("Código válido. Ahora escribe la nueva contraseña.", "success");
});

resetCompleteForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  clearMessage();

  const password = document.getElementById("newPassword").value.trim();
  const confirmPassword = document.getElementById("confirmPassword").value.trim();

  const { data } = await apiFetch("/auth/password-reset/complete", {
    method: "POST",
    body: JSON.stringify({
      challengeId: resetChallengeId,
      code: resetCode,
      password,
      confirmPassword
    })
  });

  if (!data.success) {
    const msg = data.errors ? `${data.message}\n- ${data.errors.join("\n- ")}` : data.message;
    showMessage(msg || "No se pudo cambiar la contraseña.", "error");
    return;
  }

  showOnly(loginForm);
  showMessage(data.message || "Contraseña actualizada correctamente.", "success");
});

checkSession();