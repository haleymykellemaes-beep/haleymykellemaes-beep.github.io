(function () {
  var nav = document.querySelector(".site-nav");
  if (!nav) return;
  var hero = document.querySelector(".home-hero, .case-hero");

  function updateNav() {
    var past = hero
      ? hero.getBoundingClientRect().bottom <= nav.offsetHeight + 8
      : window.scrollY > 36;
    nav.classList.toggle("is-past-profile", past);
  }

  updateNav();
  window.addEventListener("scroll", updateNav, { passive: true });
  window.addEventListener("resize", updateNav);
})();
