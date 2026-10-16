/* Site behaviour, shared by every page. A classic script (not a module) so the
   pages keep working when opened straight from disk.

   1. Header turns solid after you scroll past the banner.
   2. Mobile menu opens and closes (button, link click, Escape).
   3. Rows: previous/next buttons for rows that scroll sideways.
   4. Quick look: a native <dialog> filled from a <template> per project.
   5. Print and copy buttons (resume, cover letter).
   6. Cover letter: fills the letter in as you type, in this browser only.
   7. "Replay intro" on the opening screen.
   The cinematic intro itself lives in intro.js.

   Controls that need this script ship with the `hidden` attribute and are only
   revealed here, so a visitor without JavaScript never sees a button that does
   nothing. */
(function () {
  "use strict";

  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  function each(selector, fn) { Array.prototype.forEach.call(document.querySelectorAll(selector), fn); }

  // ------------------------------------------------------------- header
  function initHeader() {
    var header = document.querySelector("[data-header]");
    if (!header) return;
    var update = function () { header.classList.toggle("is-scrolled", window.scrollY > 24); };
    update();
    window.addEventListener("scroll", update, { passive: true });
  }

  // ------------------------------------------------------------- menu
  function initMenu() {
    var button = document.querySelector("[data-menu-button]");
    var nav = document.getElementById("site-nav");
    if (!button || !nav) return;
    var setOpen = function (open) {
      button.setAttribute("aria-expanded", String(open));
      nav.classList.toggle("is-open", open);
    };
    button.addEventListener("click", function () {
      setOpen(button.getAttribute("aria-expanded") !== "true");
    });
    nav.addEventListener("click", function (e) {
      if (e.target.closest("a")) setOpen(false);
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && button.getAttribute("aria-expanded") === "true") {
        setOpen(false);
        button.focus();
      }
    });
  }

  // ------------------------------------------------------------- rows (shelves)
  function initShelves() {
    each("[data-shelf]", function (shelf) {
      var track = shelf.querySelector("[data-shelf-track]");
      var controls = shelf.querySelector("[data-shelf-controls]");
      var prev = shelf.querySelector("[data-shelf-prev]");
      var next = shelf.querySelector("[data-shelf-next]");
      if (!track || !controls || !prev || !next) return;

      // One press moves as many whole tiles as fit, measured from the real
      // tile width and gap, so it is right at every screen size.
      function step() {
        var card = track.firstElementChild;
        if (!card) return track.clientWidth;
        var gap = parseFloat(getComputedStyle(track).columnGap) || 0;
        var size = card.getBoundingClientRect().width + gap;
        return Math.max(1, Math.floor((track.clientWidth + gap) / size)) * size;
      }
      // aria-disabled (not `disabled`) keeps a pressed button focusable at the end of the row.
      function setState(button, off) { button.setAttribute("aria-disabled", String(off)); }
      function update() {
        var max = track.scrollWidth - track.clientWidth;
        controls.hidden = max <= 2;
        setState(prev, track.scrollLeft <= 2);
        setState(next, track.scrollLeft >= max - 2);
      }
      function go(direction, button) {
        if (button.getAttribute("aria-disabled") === "true") return;
        track.scrollBy({ left: direction * step(), behavior: reduceMotion.matches ? "auto" : "smooth" });
      }
      prev.addEventListener("click", function () { go(-1, prev); });
      next.addEventListener("click", function () { go(1, next); });
      track.addEventListener("scroll", update, { passive: true });
      if (window.ResizeObserver) new ResizeObserver(update).observe(track);
      else window.addEventListener("resize", update);
      update();
    });
  }

  // ------------------------------------------------------------- quick look
  function initQuickLook() {
    var dialog = document.querySelector("[data-quick-look-dialog]");
    // No dialog on this page, or an old browser: buttons stay hidden and the
    // tile artwork keeps working as a plain link to the project page.
    if (!dialog || typeof dialog.showModal !== "function") return;
    var body = dialog.querySelector("[data-quick-look-body]");
    var opener = null;

    each("button[data-quick-look]", function (b) { b.hidden = false; });

    // One listener for every tile (event delegation), instead of one per tile.
    document.addEventListener("click", function (e) {
      var trigger = e.target.closest("[data-quick-look]");
      if (!trigger) return;
      // Ctrl/Cmd/Shift-click on a tile still opens the full page, as a link should.
      if (trigger.tagName === "A" && (e.ctrlKey || e.metaKey || e.shiftKey || e.button !== 0)) return;
      var template = document.getElementById("ql-" + trigger.getAttribute("data-quick-look"));
      if (!template) return;
      e.preventDefault();
      opener = trigger;
      body.replaceChildren(template.content.cloneNode(true));   // a copy of inert markup: no HTML strings
      var title = body.querySelector("h2[id]");
      if (title) dialog.setAttribute("aria-labelledby", title.id);
      dialog.showModal();       // traps focus, makes the page behind inert, Escape closes
      dialog.scrollTop = 0;
    });

    dialog.querySelector("[data-quick-look-close]").addEventListener("click", function () { dialog.close(); });
    // A click on the dimmed backdrop lands on the <dialog> itself.
    dialog.addEventListener("click", function (e) { if (e.target === dialog) dialog.close(); });
    dialog.addEventListener("close", function () {
      body.replaceChildren();
      if (opener) { opener.focus(); opener = null; }   // back to what opened it
    });
  }

  // ------------------------------------------------------------- print, copy
  function initPrint() {
    each("[data-print]", function (b) {
      b.hidden = false;
      b.addEventListener("click", function () { window.print(); });
    });
  }

  // ------------------------------------------------------------- cover letter
  function initCoverLetter() {
    var form = document.querySelector("[data-letter-form]");
    var letter = document.querySelector("[data-letter]");
    if (!form || !letter) return;
    form.hidden = false;
    var defaults = { role: "Forward Deployed Engineer", company: "your company", why: "" };

    function fill() {
      var data = new FormData(form);
      ["role", "company", "why"].forEach(function (key) {
        var value = (data.get(key) || "").toString().trim() || defaults[key];
        // textContent, never innerHTML: whatever is typed stays plain text.
        letter.querySelectorAll('[data-fill="' + key + '"]').forEach(function (el) { el.textContent = value; });
      });
      var whyBlock = letter.querySelector('[data-fill-block="why"]');
      if (whyBlock) whyBlock.hidden = !(data.get("why") || "").toString().trim();
      var focus = data.get("focus");
      letter.querySelectorAll("[data-focus]").forEach(function (p) { p.hidden = p.getAttribute("data-focus") !== focus; });
    }
    form.addEventListener("input", fill);
    form.addEventListener("submit", function (e) { e.preventDefault(); });
    fill();

    var copy = document.querySelector("[data-copy-letter]");
    if (copy && navigator.clipboard) {
      copy.hidden = false;
      copy.addEventListener("click", function () {
        navigator.clipboard.writeText(letter.innerText.trim()).then(function () {
          copy.textContent = "Copied";
          setTimeout(function () { copy.textContent = "Copy letter"; }, 1800);
        });
      });
    }
  }

  // ------------------------------------------------------------- replay intro
  function initReplay() {
    var button = document.querySelector("[data-replay-intro]");
    if (!button || reduceMotion.matches) return;   // the intro never plays with reduced motion
    button.hidden = false;
    button.addEventListener("click", function () {
      try { sessionStorage.removeItem("ks-intro"); } catch (e) { /* ignore */ }
      window.scrollTo(0, 0);
      window.location.reload();
    });
  }

  initHeader();
  initMenu();
  initShelves();
  initQuickLook();
  initPrint();
  initCoverLetter();
  initReplay();
})();
