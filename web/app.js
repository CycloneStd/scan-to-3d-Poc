import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { SparkRenderer, SplatMesh } from "@sparkjsdev/spark";

const $ = (id) => document.getElementById(id);
const params = new URLSearchParams(location.search);

async function main() {
  const cfg = await (await fetch("config.json", { cache: "no-cache" })).json();
  document.title = cfg.title ?? document.title;

  const renderer = new THREE.WebGLRenderer({ antialias: false, powerPreference: "high-performance" });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, cfg.maxPixelRatio ?? 2));
  renderer.setSize(innerWidth, innerHeight);
  document.body.prepend(renderer.domElement);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(cfg.fov ?? 60, innerWidth / innerHeight, 0.01, 1000);
  camera.position.set(...cfg.camera.position);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.target.set(...cfg.camera.target);
  controls.enableDamping = true;
  controls.update();

  const spark = new SparkRenderer({ renderer });
  scene.add(spark);
  const splat = new SplatMesh({ url: cfg.asset });
  splat.quaternion.set(...cfg.orientation); // x, y, z, w
  scene.add(splat);
  if (splat.initialized) await splat.initialized;
  $("loading").classList.add("hidden");

  // Hotspots: DOM buttons projected from world positions each frame
  const layer = $("hotspots");
  const items = (cfg.hotspots ?? []).map((h) => {
    const el = document.createElement("button");
    el.className = "hotspot";
    el.setAttribute("aria-label", h.title ?? "Hotspot");
    el.addEventListener("click", () => openPanel(h));
    layer.appendChild(el);
    return { h, el, pos: new THREE.Vector3(...h.position) };
  });

  function openPanel(h) {
    $("panel-title").textContent = h.title ?? "";
    $("panel-body").textContent = h.body ?? "";
    const media = $("panel-media");
    media.replaceChildren();
    if (h.media) {
      const isVideo = /\.(mp4|webm)$/i.test(h.media);
      const m = document.createElement(isVideo ? "video" : "img");
      m.src = h.media;
      if (isVideo) { m.controls = true; m.playsInline = true; }
      media.appendChild(m);
    }
    $("panel").classList.remove("hidden");
  }
  $("close").addEventListener("click", () => $("panel").classList.add("hidden"));

  const v = new THREE.Vector3();
  function updateHotspots() {
    for (const { el, pos } of items) {
      v.copy(pos).project(camera);
      const visible = v.z < 1 && Math.abs(v.x) < 1.1 && Math.abs(v.y) < 1.1;
      el.style.display = visible ? "block" : "none";
      if (visible) {
        el.style.transform = `translate(-50%, -50%) translate(${(v.x * 0.5 + 0.5) * innerWidth}px, ${(-v.y * 0.5 + 0.5) * innerHeight}px)`;
      }
    }
  }

  // Authoring: ?author=1, orbit/pan so the item is at the screen centre, press H
  if (params.has("author")) {
    addEventListener("keydown", (e) => {
      if (e.key.toLowerCase() !== "h") return;
      const p = controls.target.toArray().map((n) => +n.toFixed(3));
      const snippet = JSON.stringify({ id: "hotspot-" + Date.now(), position: p, title: "Title", body: "", media: "" });
      console.log(snippet);
      navigator.clipboard?.writeText(snippet).catch(() => {});
      const t = $("toast");
      t.textContent = "Hotspot JSON copied (also in console)";
      t.classList.remove("hidden");
      setTimeout(() => t.classList.add("hidden"), 2500);
    });
  }

  // Performance readout: ?stats=1
  const stats = $("stats");
  let frames = 0, last = performance.now();
  if (params.has("stats")) stats.classList.remove("hidden");

  addEventListener("resize", () => {
    renderer.setSize(innerWidth, innerHeight);
    camera.aspect = innerWidth / innerHeight;
    camera.updateProjectionMatrix();
  });

  renderer.setAnimationLoop(() => {
    controls.update();
    renderer.render(scene, camera);
    updateHotspots();
    frames++;
    const now = performance.now();
    if (now - last >= 500) {
      if (params.has("stats")) stats.textContent = `${Math.round((frames * 1000) / (now - last))} FPS | DPR ${renderer.getPixelRatio()}`;
      frames = 0;
      last = now;
    }
  });
}

main().catch((err) => {
  $("loading").textContent = "Could not load the scene: " + err.message;
  console.error(err);
});
