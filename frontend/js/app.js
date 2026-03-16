const API_BASE = "http://127.0.0.1:8000/api";

document.addEventListener("DOMContentLoaded", () => {
  const userName = document.getElementById("userName");
  const userEmail = document.getElementById("userEmail");
  const userRole = document.getElementById("userRole");

  const logoutBtn = document.getElementById("logoutBtn");
  const refreshBtn = document.getElementById("refreshBtn");

  const documentList = document.getElementById("documentList");
  const documentTitle = document.getElementById("documentTitle");
  const documentViewer = document.getElementById("documentViewer");

  const chatBox = document.getElementById("chatBox");
  const questionInput = document.getElementById("questionInput");
  const sendBtn = document.getElementById("sendBtn");

  const chatDrawer = document.getElementById("chatDrawer");
  const chatToggleBtn = document.getElementById("chatToggleBtn");
  const chatCloseBtn = document.getElementById("chatCloseBtn");

  const brandLogo = document.getElementById("brandLogo");
  const chatFabAvatar = document.getElementById("chatFabAvatar");

  const BACKEND_BASE = API_BASE.replace(/\/api\/?$/, "");

  const logoCandidates = [
    "./assets/logo.png",
    `${BACKEND_BASE}/assets/logo.png`,
    "http://127.0.0.1:8000/assets/logo.png"
  ];

  const avatarCandidates = [
    "./assets/chatbot-avatar.png",
    `${BACKEND_BASE}/assets/chatbot-avatar.png`,
    "http://127.0.0.1:8000/assets/chatbot-avatar.png",
    "./assets/logo.png",
    `${BACKEND_BASE}/assets/logo.png`,
    "http://127.0.0.1:8000/assets/logo.png"
  ];

  let logoIndex = 0;
  let avatarIndex = 0;
  let currentUser = null;
  let currentDocument = "";
  let chatHistory = [];
  let currentFiles = [];
  let isSending = false;
  let isLoadingDocument = false;

  function resolveLogo() {
    if (!brandLogo) return;

    brandLogo.addEventListener("error", () => {
      logoIndex += 1;
      if (logoIndex < logoCandidates.length) {
        brandLogo.src = logoCandidates[logoIndex];
      }
    });

    brandLogo.src = logoCandidates[logoIndex];
  }

  function resolveAvatarImage(imageElement) {
    if (!imageElement) return;

    imageElement.addEventListener("error", () => {
      avatarIndex += 1;
      if (avatarIndex < avatarCandidates.length) {
        imageElement.src = avatarCandidates[avatarIndex];
      }
    });

    imageElement.src = avatarCandidates[avatarIndex];
  }

  function escapeHtml(value = "") {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  async function apiFetch(path, options = {}) {
    try {
      const response = await fetch(`${API_BASE}${path}`, {
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          ...(options.headers || {})
        },
        ...options
      });

      const text = await response.text();
      let data = {};

      try {
        data = text ? JSON.parse(text) : {};
      } catch (_) {
        data = {};
      }

      return { response, data };
    } catch (error) {
      return {
        response: { ok: false, status: 500 },
        data: {
          success: false,
          message: "No fue posible conectar con el servidor."
        }
      };
    }
  }

  function openChat() {
    chatDrawer.classList.add("open");
    chatDrawer.setAttribute("aria-hidden", "false");
    chatToggleBtn.setAttribute("aria-expanded", "true");
  }

  function closeChat() {
    chatDrawer.classList.remove("open");
    chatDrawer.setAttribute("aria-hidden", "true");
    chatToggleBtn.setAttribute("aria-expanded", "false");
  }

  function toggleChat() {
    if (chatDrawer.classList.contains("open")) {
      closeChat();
    } else {
      openChat();
      questionInput.focus();
    }
  }

  function autosizeTextarea() {
    if (!questionInput) return;
    questionInput.style.height = "auto";
    questionInput.style.height = `${Math.min(questionInput.scrollHeight, 180)}px`;
  }

  function setSendState(loading) {
    isSending = loading;
    sendBtn.disabled = loading;
    questionInput.disabled = loading;
    sendBtn.textContent = loading ? "Enviando..." : "Enviar";
  }

  function setViewerLoading(message = "Cargando documento...") {
    documentViewer.innerHTML = `
      <div class="document-placeholder">
        ${escapeHtml(message)}
      </div>
    `;
  }

  function renderDocument(htmlContent) {
    documentViewer.innerHTML = `
      <div class="document-page">
        ${htmlContent}
      </div>
    `;
  }

  function renderViewerMessage(message) {
    documentViewer.innerHTML = `
      <div class="document-placeholder">
        ${escapeHtml(message)}
      </div>
    `;
  }

  function syncActiveDocumentButton() {
    const allButtons = document.querySelectorAll(".doc-list button");

    allButtons.forEach((btn) => {
      const btnFile = btn.getAttribute("data-file");
      btn.classList.toggle("active", btnFile === currentDocument);
    });
  }

  function addMessage(content, role = "bot", sources = []) {
  const row = document.createElement("div");
  row.className = `message-row ${role}`;

  if (role === "bot") {
    const avatar = document.createElement("div");
    avatar.className = "message-avatar";

    const avatarImg = document.createElement("img");
    avatarImg.alt = "Avatar SWAN";
    resolveAvatarImage(avatarImg);

    avatar.appendChild(avatarImg);
    row.appendChild(avatar);
  }

  const wrapper = document.createElement("div");
  wrapper.className = `bubble ${role}`;
  wrapper.textContent = content;

  if (sources.length && role === "bot") {
    const sourcesBox = document.createElement("div");
    sourcesBox.className = "sources";

    const sourceLines = sources.map((item) => {
      const file = item.file || "Documento";
      const chunkId = item.chunk_id ?? "-";
      const score =
        item.score !== undefined && item.score !== null
          ? Number(item.score).toFixed(4)
          : "-";

      return `• ${file} | fragmento ${chunkId} | score ${score}`;
    });

    sourcesBox.innerHTML = `<strong>Fuentes:</strong><br>${sourceLines.join("<br>")}`;
    wrapper.appendChild(sourcesBox);
  }

  row.appendChild(wrapper);
  chatBox.appendChild(row);
  chatBox.scrollTop = chatBox.scrollHeight;
}

  function clearChat() {
    chatBox.innerHTML = "";
    chatHistory = [];
  }

  function renderFiles(files) {
    currentFiles = Array.isArray(files) ? files : [];
    documentList.innerHTML = "";

    if (!currentFiles.length) {
      const li = document.createElement("li");
      li.innerHTML = `
        <div class="document-placeholder" style="padding: 16px;">
          No hay documentos disponibles.
        </div>
      `;
      documentList.appendChild(li);
      return;
    }

    currentFiles.forEach((file) => {
      const li = document.createElement("li");
      const btn = document.createElement("button");

      btn.type = "button";
      btn.textContent = file.title || file.file || "Documento";
      btn.setAttribute("data-file", file.file || "");

      btn.addEventListener("click", async () => {
        if (!file.file || file.file === currentDocument || isLoadingDocument) return;
        await openDocument(file.file);
      });

      li.appendChild(btn);
      documentList.appendChild(li);
    });

    syncActiveDocumentButton();
  }

  async function loadProfile() {
    const { response, data } = await apiFetch("/auth/me", { method: "GET" });

    if (!response.ok || !data.success) {
      window.location.href = "./login.html";
      return false;
    }

    currentUser = data.user || {};
    userName.textContent = currentUser.nombre || "-";
    userEmail.textContent = currentUser.email || "-";
    userRole.textContent = currentUser.rol || "-";

    return true;
  }

  async function loadFiles() {
    const { data } = await apiFetch("/files", { method: "GET" });

    if (!data.success) {
      renderFiles([]);
      renderViewerMessage(data.message || "No fue posible consultar los documentos.");
      return;
    }

    const files = Array.isArray(data.files) ? data.files : [];
    renderFiles(files);

    if (files.length > 0) {
      await openDocument(files[0].file);
    } else {
      documentTitle.textContent = "Sin documentos";
      renderViewerMessage("No hay documentos cargados actualmente.");
    }
  }

  async function openDocument(fileName) {
    if (!fileName) return;

    isLoadingDocument = true;
    documentTitle.textContent = "Cargando...";
    setViewerLoading("Abriendo documento...");

    const { data } = await apiFetch(`/document?file=${encodeURIComponent(fileName)}`, {
      method: "GET"
    });

    isLoadingDocument = false;

    if (!data.success) {
      documentTitle.textContent = "Error";
      renderViewerMessage(data.message || "No se pudo abrir el documento.");
      return;
    }

    currentDocument = data.document?.file || fileName;
    documentTitle.textContent = data.document?.title || data.document?.file || "Documento";
    renderDocument(data.document?.html_content || "<p>Documento vacío.</p>");
    syncActiveDocumentButton();

    clearChat();
    addMessage(
      `Hola ${currentUser?.nombre || ""}, ya tengo cargado el documento "${data.document?.title || data.document?.file || "actual"}". Puedes preguntarme sobre su contenido.`,
      "bot"
    );
  }

  async function sendQuestion() {
    const question = questionInput.value.trim();

    if (!question || isSending) return;

    if (!currentDocument) {
      openChat();
      addMessage("Primero selecciona un documento para poder ayudarte.", "bot");
      return;
    }

    openChat();
    addMessage(question, "user");
    chatHistory.push({ role: "user", content: question });

    questionInput.value = "";
    autosizeTextarea();
    setSendState(true);

    const { data } = await apiFetch("/chat", {
      method: "POST",
      body: JSON.stringify({
        question,
        history: chatHistory,
        currentDocument
      })
    });

    setSendState(false);

    if (!data.success) {
      addMessage(data.message || "No fue posible procesar la pregunta.", "bot");
      return;
    }

    const answer = data.answer || "Sin respuesta.";
    addMessage(answer, "bot", data.sources || []);
    chatHistory.push({ role: "assistant", content: answer });
  }

  async function logout() {
    await apiFetch("/auth/logout", {
      method: "POST",
      body: JSON.stringify({})
    });

    window.location.href = "./login.html";
  }

  async function refreshCurrentView() {
    if (!currentFiles.length) {
      await loadFiles();
      return;
    }

    if (currentDocument) {
      await openDocument(currentDocument);
    } else {
      await loadFiles();
    }
  }

  chatToggleBtn?.addEventListener("click", toggleChat);
  chatCloseBtn?.addEventListener("click", closeChat);
  logoutBtn?.addEventListener("click", logout);
  refreshBtn?.addEventListener("click", refreshCurrentView);
  sendBtn?.addEventListener("click", sendQuestion);

  questionInput?.addEventListener("input", autosizeTextarea);

  questionInput?.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendQuestion();
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && chatDrawer.classList.contains("open")) {
      closeChat();
    }
  });

  (async function init() {
  resolveLogo();
  resolveAvatarImage(chatFabAvatar);
  autosizeTextarea();

    const ok = await loadProfile();
    if (!ok) return;

    await loadFiles();
  })();
});