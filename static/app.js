const chat = document.getElementById("chat");
const form = document.getElementById("form");
const input = document.getElementById("input");
const resetBtn = document.getElementById("reset");
const sessionInfo = document.getElementById("session-info");

let sessionId = null;

function append(role, text) {
  const div = document.createElement("div");
  div.className = `msg ${role}`;
  div.textContent = text;
  chat.appendChild(div);
  chat.scrollTop = chat.scrollHeight;
  return div;
}

function appendToolCalls(calls) {
  if (!calls || !calls.length) return;
  for (const c of calls) {
    const summary = `[tool] ${c.name}(${JSON.stringify(c.input)}) -> ${JSON.stringify(c.result).slice(0, 240)}`;
    append("tool", summary);
  }
}

async function sendMessage(message) {
  const pending = append("bot", "...");
  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, session_id: sessionId }),
    });
    if (!res.ok) {
      pending.remove();
      append("error", `Request failed (${res.status}): ${await res.text()}`);
      return;
    }
    const data = await res.json();
    sessionId = data.session_id;
    sessionInfo.textContent = `session: ${sessionId}`;
    pending.remove();
    appendToolCalls(data.tool_calls);
    append("bot", data.reply || "(no reply)");
  } catch (err) {
    pending.remove();
    append("error", `Network error: ${err.message}`);
  }
}

form.addEventListener("submit", (e) => {
  e.preventDefault();
  const text = input.value.trim();
  if (!text) return;
  append("user", text);
  input.value = "";
  sendMessage(text);
});

resetBtn.addEventListener("click", () => {
  sessionId = null;
  chat.innerHTML = "";
  sessionInfo.textContent = "";
  loadWelcome();
});

async function loadWelcome() {
  try {
    const res = await fetch("/api/welcome");
    const data = await res.json();
    append("bot", data.message);
  } catch {
    append("bot", "Hello! I'm ProcureBot. What do you need help with today?");
  }
}

loadWelcome();
