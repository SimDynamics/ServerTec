"use strict";

const routeMessage = document.getElementById("route-message");
for (const button of document.querySelectorAll("[data-route]")) {
  button.addEventListener("click", () => {
    routeMessage.textContent = "Demostración: contenido todavía no integrado";
  });
}

const checkButton = document.getElementById("check-connection");
const result = document.getElementById("connection-result");
let lastRequestId = null;

checkButton.addEventListener("click", async () => {
  checkButton.disabled = true;
  result.dataset.state = "pending";
  result.textContent = "Comprobando conexión…";
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 10000);
  try {
    const bytes = crypto.getRandomValues(new Uint8Array(24));
    const challenge = Array.from(bytes, value => value.toString(16).padStart(2, "0")).join("");
    const response = await fetch(`/demo/status?challenge=${challenge}&_=${challenge}`, {
      method: "GET",
      cache: "no-store",
      credentials: "omit",
      redirect: "error",
      mode: "same-origin",
      headers: { "Accept": "application/json" },
      signal: controller.signal
    });
    if (!response.ok || !response.headers.get("content-type")?.startsWith("application/json") ||
        !response.headers.get("cache-control")?.includes("no-store")) {
      throw new Error("Respuesta no válida");
    }
    const status = await response.json();
    const marker = /^[a-f0-9]{32}$/;
    if (status.status !== "ok" || status.demo !== true || status.challenge !== challenge ||
        !marker.test(status.run_id) || !marker.test(status.request_id) ||
        status.request_id === lastRequestId ||
        typeof status.server_time_utc !== "string" || !status.server_time_utc.endsWith("Z") ||
        !Number.isFinite(Date.parse(status.server_time_utc))) {
      throw new Error("No se pudo verificar una respuesta nueva");
    }
    lastRequestId = status.request_id;
    result.dataset.state = "ok";
    result.textContent = `Conexión confirmada.\nHora UTC del servidor: ${status.server_time_utc}\nEjecución: ${status.run_id}\nRespuesta: ${status.request_id}`;
  } catch (_error) {
    result.dataset.state = "error";
    result.textContent = "No se pudo comprobar la conexión. Verifica la red y vuelve a intentarlo.";
  } finally {
    clearTimeout(timer);
    checkButton.disabled = false;
  }
});
