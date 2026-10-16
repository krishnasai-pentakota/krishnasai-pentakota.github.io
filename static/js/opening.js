/* The opening screen: the intro film, then the role tiles.

   index.html's head script has already decided, before anything painted:
   - "tiles-go" on <html>: the five role tiles fade up one by one. CSS does that.
   - "intro-pending": the intro film plays first. This script plays it, then hands the
     page over to the role tiles when the film ends, on Skip / Esc / Enter / Space, or as soon
     as anything goes wrong (autoplay blocked, no playable format, slow connection).
   Every way out ends on the role picker, which is always there underneath.

   A classic script (not a module) so the page also works when opened from disk. */
(function () {
  "use strict";

  var html = document.documentElement;
  if (!html.classList.contains("intro-pending")) return;

  var intro = document.querySelector("[data-intro]");
  var video = document.querySelector("[data-intro-video]");
  var controls = document.querySelector("[data-intro-controls]");
  var skip = document.querySelector("[data-intro-skip]");
  var sound = document.querySelector("[data-intro-sound]");
  var soundLabel = document.querySelector("[data-intro-sound-label]");
  if (!intro || !video || !controls || !skip) {
    html.classList.remove("intro-pending");
    return;
  }

  var done = false;
  var started = false;
  html.classList.add("intro-playing");
  try { sessionStorage.setItem("ks-intro", "1"); } catch (e) { /* private mode: fine */ }

  function finish() {
    if (done) return;
    done = true;
    // The film fades out over the picker while the role tiles fade up underneath it.
    html.classList.add("intro-leaving");
    html.classList.remove("intro-pending", "intro-playing");
    window.removeEventListener("keydown", onKey);
    setTimeout(function () {
      try { video.pause(); } catch (e) { /* already gone */ }
      intro.remove();
      controls.remove();
      html.classList.remove("intro-leaving");
    }, 800);
  }

  function onKey(e) {
    if (e.key === "Escape" || e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      finish();
    }
  }

  skip.addEventListener("click", finish);
  window.addEventListener("keydown", onKey);

  if (sound && soundLabel) {
    sound.addEventListener("click", function () {
      video.muted = !video.muted;
      sound.setAttribute("aria-pressed", String(!video.muted));
      soundLabel.textContent = video.muted ? "Sound on" : "Sound off";
    });
  }

  video.addEventListener("playing", function () { started = true; });
  video.addEventListener("ended", finish);
  // Start the hand-over just before the last frame, so film and tiles feel like one move.
  video.addEventListener("timeupdate", function () {
    if (video.duration && video.currentTime > video.duration - 0.35) finish();
  });
  // The last <source> failing means this browser can play none of them.
  var sources = video.querySelectorAll("source");
  if (sources.length) sources[sources.length - 1].addEventListener("error", finish);
  video.addEventListener("error", finish);

  video.muted = true; // browsers only autoplay muted video
  var playing = video.play();
  if (playing && typeof playing.catch === "function") playing.catch(finish); // autoplay blocked, e.g. battery saver

  // Slow connection: if the film hasn't started within 4 s, nobody waits for it.
  setTimeout(function () { if (!started) finish(); }, 4000);
  // And never longer than 14 s, whatever happens.
  setTimeout(finish, 14000);
})();
