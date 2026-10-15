// Panel de administración — Balboa Boxing Club Bogotá

// Agregar filas de talla/color en la ficha del producto
const variants = document.querySelector("[data-variants]");
const template = document.querySelector("[data-variant-template]");
const addButton = document.querySelector("[data-add-variant]");
if (variants && template && addButton) {
  let next = variants.querySelectorAll("[data-variant-row]").length;
  addButton.addEventListener("click", () => {
    const html = template.innerHTML.replaceAll("__i__", String(next++));
    variants.insertAdjacentHTML("beforeend", html);
    variants.lastElementChild.querySelector("input[type=text]").focus();
  });
}

// Avisar antes de salir de un formulario con cambios sin guardar
const productForm = document.querySelector(".adm-product");
if (productForm) {
  let dirty = false;
  productForm.addEventListener("input", () => (dirty = true));
  productForm.addEventListener("submit", () => (dirty = false));
  window.addEventListener("beforeunload", (e) => {
    if (dirty) e.preventDefault();
  });
}
