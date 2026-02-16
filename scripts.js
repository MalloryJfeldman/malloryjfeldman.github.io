document.addEventListener("DOMContentLoaded", function() {
  const toggle = document.querySelector(".color-mode-toggle");
  if (!toggle) return;

  // set initial icon
  const icon = document.createElement("i");
  icon.classList.add("fa-solid", "fa-circle-half-stroke"); // initial icon
  toggle.appendChild(icon);

  // update icon on toggle
  toggle.addEventListener("click", () => {
    setTimeout(() => {  // wait for color mode change
      if (document.documentElement.getAttribute("data-color-mode") === "dark") {
        icon.classList.remove("fa-circle-half-stroke");
        icon.classList.add("fa-sun");
      } else {
        icon.classList.remove("fa-sun");
        icon.classList.add("fa-circle-half-stroke");
      }
    }, 50);
  });
});
