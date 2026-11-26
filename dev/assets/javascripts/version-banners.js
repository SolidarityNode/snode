/*
 * Version banners (tools/docs/overrides/main.html, docs/releasing.md).
 *
 * - On a release build, the announcement bar is shown only while this version has the mike
 *   alias "latest" (versions.json); an older release shows Material's outdated banner instead.
 * - Links marked data-sn-version="dev" or "latest" open the same page in that version if it
 *   exists there, otherwise that version's home, in the current language. They are resolved
 *   on click, so the banner HTML (and the hash Material keeps for a dismissed bar) never changes.
 */
(function () {
  "use strict";
  var cfg = window.SN_DOCS || {};
  var announce = document.querySelector("[data-md-component=announce]");
  var root = new URL((cfg.base || ".") + "/", window.location.href); // this version's root
  var site = new URL("../", root); // the folder holding every version
  var current = root.pathname.replace(/\/$/, "").split("/").pop();
  var versions = fetch(new URL("versions.json", site).href)
    .then(function (r) {
      return r.ok ? r.json() : [];
    })
    .catch(function () {
      return [];
    });

  function entry(list, name) {
    return list.find(function (v) {
      return v.version === name || (v.aliases || []).indexOf(name) >= 0;
    });
  }

  // Release build: hide the bar until we know this version is the latest one.
  if (cfg.channel === "release" && announce && announce.querySelector("[data-sn-banner=latest]")) {
    var dismissed = announce.hidden;
    announce.hidden = true;
    versions.then(function (list) {
      var here = entry(list, current);
      if (here && (here.aliases || []).indexOf("latest") >= 0 && !dismissed) {
        announce.hidden = false;
      }
    });
  }

  // Dev build: the bar cannot be dismissed. The close button is hidden, not removed: Material
  // binds dismissal to the first element of the bar, which must stay the (hidden) button.
  if (cfg.channel === "dev" && announce) {
    var button = announce.querySelector(".md-banner__button");
    if (button) {
      button.hidden = true;
      button.style.display = "none";
    }
    if (announce.hidden && announce.querySelector("[data-sn-banner=dev]")) announce.hidden = false;
  }

  function home(target) {
    return new URL(target + "/" + (cfg.lang && cfg.lang !== "en" ? cfg.lang + "/" : ""), site);
  }

  function samePage(target) {
    var path = window.location.pathname;
    var rel = path.indexOf(root.pathname) === 0 ? path.slice(root.pathname.length) : "";
    return new URL(target + "/" + rel + window.location.hash, site);
  }

  document.addEventListener("click", function (event) {
    var link = event.target.closest && event.target.closest("a[data-sn-version]");
    if (!link) return;
    event.preventDefault();
    var target = link.getAttribute("data-sn-version");
    var page = samePage(target);
    fetch(page.href, { method: "HEAD" })
      .then(function (r) {
        window.location.href = r.ok ? page.href : home(target).href;
      })
      .catch(function () {
        window.location.href = home(target).href;
      });
  });
})();
