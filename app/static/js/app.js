// Balboa Boxing Club Bogotá — interacciones de la tienda

const API = "/api/v1/cart";
const toastEl = document.querySelector(".toast");
let toastTimer;

function toast(message, isError = false) {
  toastEl.textContent = message;
  toastEl.classList.toggle("is-error", isError);
  toastEl.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (toastEl.hidden = true), 3500);
}

async function cartRequest(path, method, body) {
  const res = await fetch(API + path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "No se pudo actualizar el carrito.");
  return data;
}

function updateBadge(count) {
  const badge = document.querySelector("[data-cart-count]");
  badge.textContent = count;
  badge.hidden = count === 0;
}

// Botones − y + de cantidad
document.addEventListener("click", (e) => {
  const step = e.target.closest("[data-qty-step]");
  if (!step) return;
  const input = step.parentElement.querySelector("input");
  const max = Number(input.max) || 99;
  const next = Math.min(Math.max(Number(input.value) + Number(step.dataset.qtyStep), 1), max);
  if (next !== Number(input.value)) {
    input.value = next;
    input.dispatchEvent(new Event("change", { bubbles: true }));
  }
});

// Página de producto: agregar al carrito
const buyForm = document.querySelector("[data-add-to-cart]");
if (buyForm) {
  // Al elegir una variante, el máximo de la cantidad pasa a ser su stock.
  buyForm.addEventListener("change", (e) => {
    if (e.target.name !== "variant_id") return;
    const qty = buyForm.elements.quantity;
    qty.max = e.target.dataset.stock;
    qty.value = Math.min(Number(qty.value), Number(qty.max));
  });

  buyForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const button = buyForm.querySelector("[type=submit]");
    button.disabled = true;
    try {
      const cart = await cartRequest("/items", "POST", {
        variant_id: Number(new FormData(buyForm).get("variant_id")),
        quantity: Number(buyForm.elements.quantity.value),
      });
      updateBadge(cart.count);
      toast("Agregado al carrito.");
    } catch (err) {
      toast(err.message, true);
    } finally {
      button.disabled = false;
    }
  });
}

// Página del carrito: cambiar cantidad y quitar
document.querySelectorAll("[data-cart-item]").forEach((line) => {
  const id = line.dataset.cartItem;
  const run = async (path, method, body) => {
    try {
      await cartRequest(path, method, body);
      location.reload();
    } catch (err) {
      toast(err.message, true);
    }
  };
  line.querySelector("[data-cart-qty]").addEventListener("change", (e) =>
    run(`/items/${id}`, "PATCH", { quantity: Math.max(Number(e.target.value), 1) })
  );
  line.querySelector("[data-cart-remove]").addEventListener("click", () => run(`/items/${id}`, "DELETE"));
});
