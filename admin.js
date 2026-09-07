const form = document.querySelector("#cookieForm");
const message = document.querySelector("#message");
const button = document.querySelector("#submitButton");

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const password = document.querySelector("#adminPassword").value;
  const file = document.querySelector("#cookieFile").files[0];
  if (!file) return;
  button.disabled = true;
  message.textContent = "Menghubungkan ke Railway...";
  message.className = "";
  try {
    const body = new FormData();
    body.append("cookies", file);
    const response = await fetch("/api/admin/cookies", {
      method: "POST",
      headers: { "x-admin-password": password },
      body,
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Update gagal.");
    message.textContent = result.message;
    message.className = "success";
    form.reset();
  } catch (error) {
    message.textContent = error.message;
    message.className = "error";
  } finally {
    button.disabled = false;
  }
});
