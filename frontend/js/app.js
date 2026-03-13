const API_BASE = "http://127.0.0.1:8000/api";

document.addEventListener("DOMContentLoaded", () => {
  const userName = document.getElementById("userName");
  const userEmail = document.getElementById("userEmail");
  const userRole = document.getElementById("userRole");
  const logoutBtn = document.getElementById("logoutBtn");
  const documentList = document.getElementById("documentList");
  const documentTitle = document.getElementById("documentTitle");
  const documentViewer = document.getElementById("documentViewer");
  const chatBox = document.getElementById("chatBox");
  const questionInput = document.getElementById("questionInput");
  const sendBtn = document.getElementById("sendBtn");
  const chatDrawer = document.getElementById("chatDrawer");
  const chatToggleBtn = document.getElementById("chatToggleBtn");
  const chatCloseBtn = document.getElementById("chatCloseBtn");

  let currentUser = null;
  let currentDocument = "";
  let chatHistory = [];

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

  function openChat() {
    chatDrawer.classList.add("open");
    chatDrawer.setAttribute("aria-hidden", "false");
  }

  function closeChat() {
    chatDrawer.classList.remove("open");
    chatDrawer.setAttribute("aria-hidden", "true");
  }

  function addMessage(content, role = "bot", sources = []) {
    const wrapper = document.createElement("div");
    wrapper.className = `bubble ${role}`;
    wrapper.textContent = content;

    if (sources.length && role === "bot") {
      const sourcesBox = document.createElement("div");
      sourcesBox.className = "sources";
      sourcesBox.innerHTML =
        "<strong>Fuentes:</strong><br>" +
        sources
          .map(item => `• ${item.file} | fragmento ${item.chunk_id} | score ${Number(item.score).toFixed(4)}`)
          .join("<br>");
      wrapper.appendChild(sourcesBox);
    }

    chatBox.appendChild(wrapper);
    chatBox.scrollTop = chatBox.scrollHeight;
  }

  function renderDocument(htmlContent) {
    documentViewer.innerHTML = `
      <div class="document-page">
        ${htmlContent}
      </div>
    `;
  }

  function renderFiles(files) {
    documentList.innerHTML = "";

    if (!files.length) {
      const li = document.createElement("li");
      li.textContent = "No hay documentos disponibles.";
      documentList.appendChild(li);
      return;
    }

    files.forEach(file => {
      const li = document.createElement("li");
      const btn = document.createElement("button");
      btn.type = "button";
      btn.textContent = file.title || file.file;

      btn.addEventListener("click", () => {
        openDocument(file.file, btn);
      });

      li.appendChild(btn);
      documentList.appendChild(li);
    });
  }

  async function loadProfile() {
    const { response, data } = await apiFetch("/auth/me", { method: "GET" });

    if (!response.ok || !data.success) {
      window.location.href = "./login.html";
      return false;
    }

    currentUser = data.user;
    userName.textContent = currentUser.nombre || "-";
    userEmail.textContent = currentUser.email || "-";
    userRole.textContent = currentUser.rol || "-";
    return true;
  }

  async function loadFiles() {
    const { data } = await apiFetch("/files", { method: "GET" });

    if (!data.success) {
      renderFiles([]);
      return;
    }

    renderFiles(data.files || []);

    if (data.files && data.files.length) {
      const first = data.files[0];
      await openDocument(first.file);
    }
  }

  async function openDocument(fileName, clickedBtn = null) {
    const { data } = await apiFetch(`/document?file=${encodeURIComponent(fileName)}`, {
      method: "GET"
    });

    if (!data.success) {
      documentTitle.textContent = "Error";
      documentViewer.innerHTML = `
        <div class="document-placeholder">
          ${data.message || "No se pudo abrir el documento."}
        </div>
      `;
      return;
    }

    currentDocument = data.document.file;
    documentTitle.textContent = data.document.title || data.document.file;
    renderDocument(data.document.html_content || "<p>Documento vacío.</p>");

    document.querySelectorAll(".doc-list button").forEach(btn => btn.classList.remove("active"));

    if (clickedBtn) {
      clickedBtn.classList.add("active");
    } else {
      document.querySelectorAll(".doc-list button").forEach(btn => {
        if (btn.textContent === (data.document.title || data.document.file)) {
          btn.classList.add("active");
        }
      });
    }
  }

  async function sendQuestion() {
    const question = questionInput.value.trim();
    if (!question) return;

    openChat();

    addMessage(question, "user");
    chatHistory.push({ role: "user", content: question });
    questionInput.value = "";

    const { data } = await apiFetch("/chat", {
      method: "POST",
      body: JSON.stringify({
        question,
        history: chatHistory,
        currentDocument
      })
    });

    if (!data.success) {
      addMessage(data.message || "No fue posible procesar la pregunta.", "bot");
      return;
    }

    addMessage(data.answer || "Sin respuesta.", "bot", data.sources || []);
    chatHistory.push({ role: "assistant", content: data.answer || "" });
  }

  if (chatToggleBtn) {
    chatToggleBtn.addEventListener("click", () => {
      if (chatDrawer.classList.contains("open")) {
        closeChat();
      } else {
        openChat();
      }
    });
  }

  if (chatCloseBtn) {
    chatCloseBtn.addEventListener("click", closeChat);
  }

  if (logoutBtn) {
    logoutBtn.addEventListener("click", async () => {
      await apiFetch("/auth/logout", {
        method: "POST",
        body: JSON.stringify({})
      });
      window.location.href = "./login.html";
    });
  }

  if (sendBtn) {
    sendBtn.addEventListener("click", sendQuestion);
  }

  if (questionInput) {
    questionInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendQuestion();
      }
    });
  }

  (async function init() {
    const ok = await loadProfile();
    if (!ok) return;

    addMessage(
      "Hola, soy SWAN. Ya cargué tu perfil y el documento disponible. Puedes preguntarme sobre su contenido.",
      "bot"
    );

    await loadFiles();
  })();
});