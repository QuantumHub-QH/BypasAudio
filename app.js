const $ = (selector) => document.querySelector(selector);
const API_BASE = (window.MONOFLOW_API_BASE || "").replace(/\/$/, "");

const audio = $("#audioPlayer");
const defaultSettings = { speed: 1, volume: 80, pitch: 0 };
let settings = { ...defaultSettings };
let currentFile = null;
let sessionApiKey = "";
const accountStorageKey = "mchlern.roblox.account";

function formatTime(seconds) {
  if (!Number.isFinite(seconds)) return "00:00";
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.floor(seconds % 60);
  return `${String(minutes).padStart(2, "0")}:${String(remainder).padStart(2, "0")}`;
}

function setMessage(target, text, type = "") {
  target.textContent = text;
  target.className = `inline-message ${type}`.trim();
}

function restoreAccount(result, apiKey, showMessage = false) {
  sessionApiKey = apiKey;
  $("#connectionStatus").classList.add("connected");
  $("#connectionStatus span:last-child").textContent = `@${result.username}`;
  $("#profileAvatar").src = result.avatarUrl;
  $("#profileDisplayName").textContent = result.displayName;
  $("#profileUsername").textContent = `@${result.username} · ID ${result.userId}`;
  $("#profileCard").classList.remove("hidden");
  if (showMessage) setMessage($("#sourceMessage"), `Akun Roblox ${result.displayName} berhasil terhubung.`, "success");
}

function saveAccount(result, apiKey) {
  localStorage.setItem(accountStorageKey, JSON.stringify({
    apiKey,
    userId: result.userId,
    username: result.username,
    displayName: result.displayName,
    avatarUrl: result.avatarUrl,
  }));
}

const savedAccount = localStorage.getItem(accountStorageKey);
if (savedAccount) {
  try {
    const account = JSON.parse(savedAccount);
    if (account.apiKey && account.userId && account.username) {
      $("#userId").value = account.userId;
      $("#apiKey").value = account.apiKey;
      restoreAccount(account, account.apiKey);
    }
  } catch {
    localStorage.removeItem(accountStorageKey);
  }
}

function updatePlayback() {
  const pitchFactor = Math.pow(2, settings.pitch / 12);
  audio.playbackRate = settings.speed * pitchFactor;
  audio.volume = settings.volume / 100;
  $("#speedControl").value = settings.speed;
  $("#volumeControl").value = settings.volume;
  $("#pitchControl").value = settings.pitch;
  $("#speedValue").textContent = `${Number(settings.speed).toFixed(2)}×`;
  $("#volumeValue").textContent = `${settings.volume}%`;
  $("#pitchValue").textContent = `${settings.pitch > 0 ? "+" : ""}${settings.pitch} st`;
  const recommendation = $("#recommendationText");
  const speed = Number(settings.speed);
  const recommended = speed >= 1.5 && speed <= 1.6;
  recommendation.innerHTML = recommended
    ? "✦ <b>Rekomendasi aktif:</b> speed ini cocok untuk musik tetap terasa normal saat bermain."
    : "✦ <b>Rekomendasi game:</b> gunakan 1.5× – 1.6× agar musik tetap terasa normal.";
  recommendation.classList.toggle("recommendation-active", recommended);
  document.querySelectorAll("[data-speed]").forEach((button) => {
    button.classList.toggle("active", Number(button.dataset.speed) === Number(settings.speed));
  });
}

function loadAudio(file, label = file.name, thumbnail = "") {
  currentFile = file;
  audio.src = URL.createObjectURL(file);
  $("#trackName").textContent = label;
  $("#trackDetail").textContent = `${(file.size / 1024 / 1024).toFixed(2)} MB · Local preview`;
  $("#fileBadge").textContent = "READY";
  $("#coverInitial").textContent = label.slice(0, 2).toUpperCase();
  const coverImage = $("#coverImage");
  coverImage.src = thumbnail;
  coverImage.classList.toggle("visible", Boolean(thumbnail));
  $("#coverInitial").classList.toggle("hidden", Boolean(thumbnail));
  $("#playerState").textContent = "Ready to preview";
  setMessage($("#sourceMessage"), "Audio berhasil dimuat. Atur playback lalu upload.", "success");
  updatePlayback();
}

function simulateProgress(wrap, bar, percent, label, done) {
  wrap.classList.remove("hidden");
  let value = 0;
  const timer = setInterval(() => {
    value = Math.min(100, value + Math.ceil(Math.random() * 13));
    bar.style.width = `${value}%`;
    percent.textContent = `${value}%`;
    if (value >= 100) {
      clearInterval(timer);
      done();
    }
  }, 100);
  return () => { label.textContent = "Processing audio..."; };
}

$("#connectForm").addEventListener("submit", (event) => {
  event.preventDefault();
  const userId = $("#userId").value.trim();
  const apiKey = $("#apiKey").value.trim();
  if (!userId || !apiKey) return;
  fetch(`${API_BASE}/api/connect`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ userId, apiKey }),
  }).then(async (response) => {
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Koneksi gagal.");
    restoreAccount(result, apiKey, true);
    saveAccount(result, apiKey);
  }).catch((error) => setMessage($("#sourceMessage"), error.message, "error"));
});

$("#revealKey").addEventListener("click", () => {
  const input = $("#apiKey");
  input.type = input.type === "password" ? "text" : "password";
});

document.querySelectorAll(".source-tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".source-tab").forEach((item) => item.classList.remove("active"));
    tab.classList.add("active");
    $("#linkSource").classList.toggle("hidden", tab.dataset.source !== "link");
    $("#fileSource").classList.toggle("hidden", tab.dataset.source !== "file");
  });
});

$("#audioFile").addEventListener("change", (event) => {
  const [file] = event.target.files;
  if (file) loadAudio(file);
});

$("#dropzone").addEventListener("dragover", (event) => event.preventDefault());
$("#dropzone").addEventListener("drop", (event) => {
  event.preventDefault();
  const [file] = event.dataTransfer.files;
  if (file && file.type.startsWith("audio/")) loadAudio(file);
});

$("#fetchButton").addEventListener("click", () => {
  const url = $("#audioUrl").value.trim();
  if (!url) {
    setMessage($("#sourceMessage"), "Tempel link YouTube, YouTube Music, atau TikTok terlebih dahulu.", "error");
    return;
  }
  if (!/^https?:\/\//i.test(url) || !/youtube\.com|youtu\.be|music\.youtube\.com|tiktok\.com/i.test(url)) {
    setMessage($("#sourceMessage"), "Link belum dikenali. Gunakan link YouTube, YouTube Music, atau TikTok.", "error");
    return;
  }
  let parsedUrl;
  try {
    parsedUrl = new URL(url);
  } catch {
    setMessage($("#sourceMessage"), "Format link tidak valid. Pastikan link diawali https://.", "error");
    return;
  }
  if (!sessionApiKey) {
    setMessage($("#sourceMessage"), "Konekin akun terlebih dahulu sebelum fetch.", "error");
    return;
  }
  const wrap = $("#fetchProgressWrap");
  const bar = $("#fetchProgress");
  const percent = $("#progressPercent");
  const label = $("#progressLabel");
  $("#fetchButton").disabled = true;
  wrap.classList.remove("hidden");
  bar.style.width = "20%"; percent.textContent = "20%"; label.textContent = "Fetching audio...";
  fetch(`${API_BASE}/api/fetch-yt`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ url }) })
    .then(async (response) => {
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Fetch gagal.");
      bar.style.width = "100%"; percent.textContent = "100%"; label.textContent = "Fetch selesai";
      const audioResponse = await fetch(`${API_BASE}${result.audioUrl}`);
      if (!audioResponse.ok) throw new Error("Audio hasil fetch tidak dapat diputar.");
      const blob = await audioResponse.blob();
      loadAudio(new File([blob], result.filename, { type: "audio/mpeg" }), result.title || `Audio dari ${result.source}`, result.thumbnail || "");
    })
    .catch((error) => setMessage($("#sourceMessage"), error.message, "error"))
    .finally(() => { $("#fetchButton").disabled = false; });
});

$("#playButton").addEventListener("click", async () => {
  if (!audio.src) {
    setMessage($("#sourceMessage"), "Pilih atau upload audio dulu untuk memulai preview.", "error");
    return;
  }
  if (audio.paused) {
    await audio.play();
    $("#playButton").textContent = "Ⅱ";
    $("#playerState").textContent = "Playing preview";
  } else {
    audio.pause();
    $("#playButton").textContent = "▶";
    $("#playerState").textContent = "Paused";
  }
});

audio.addEventListener("loadedmetadata", () => { $("#duration").textContent = formatTime(audio.duration); });
audio.addEventListener("timeupdate", () => {
  $("#currentTime").textContent = formatTime(audio.currentTime);
  $("#seekBar").value = audio.duration ? (audio.currentTime / audio.duration) * 100 : 0;
});
audio.addEventListener("ended", () => { $("#playButton").textContent = "▶"; $("#playerState").textContent = "Preview selesai"; });
$("#seekBar").addEventListener("input", (event) => { if (audio.duration) audio.currentTime = (event.target.value / 100) * audio.duration; });

$("#speedControl").addEventListener("input", (event) => { settings.speed = Number(event.target.value); updatePlayback(); });
$("#volumeControl").addEventListener("input", (event) => { settings.volume = Number(event.target.value); updatePlayback(); });
$("#pitchControl").addEventListener("input", (event) => { settings.pitch = Number(event.target.value); updatePlayback(); });
document.querySelectorAll("[data-speed]").forEach((button) => button.addEventListener("click", () => { settings.speed = Number(button.dataset.speed); updatePlayback(); }));
$("#resetButton").addEventListener("click", () => { settings = { ...defaultSettings }; updatePlayback(); setMessage($("#sourceMessage"), "Setelan dikembalikan ke normal: speed 1.0×, volume 80%, pitch 0 st.", "success"); });

$("#uploadButton").addEventListener("click", () => {
  if (!currentFile && !$("#audioUrl").value.trim()) {
    setMessage($("#uploadMessage"), "Pilih file atau fetch audio sebelum upload.", "error");
    return;
  }
  if (!sessionApiKey) {
    setMessage($("#uploadMessage"), "Konekin akun terlebih dahulu sebelum upload.", "error");
    return;
  }
  const wrap = $("#uploadProgressWrap");
  const bar = $("#uploadProgress");
  const percent = $("#uploadPercent");
  const label = $("#uploadLabel");
  $("#uploadButton").disabled = true;
  const formData = new FormData();
  if (currentFile) formData.append("audio", currentFile);
  formData.append("creator_id", $("#userId").value.trim());
  formData.append("title", $("#trackName").textContent || "MCHLERN Audio");
  formData.append("speed", String(settings.speed));
  formData.append("volume", String(settings.volume));
  fetch(`${API_BASE}/api/upload`, { method: "POST", headers: { "x-api-key": sessionApiKey }, body: formData })
    .then(async (response) => {
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "Upload gagal.");
      bar.style.width = "100%"; percent.textContent = "100%"; label.textContent = "Upload selesai";
      setMessage($("#uploadMessage"), `Audio ${result.filename} berhasil diupload.`, "success");
    })
    .catch((error) => setMessage($("#uploadMessage"), error.message, "error"))
    .finally(() => { $("#uploadButton").disabled = false; });
});

updatePlayback();
