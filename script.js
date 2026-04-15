const IMAGES = {
  estruturas: [
    "501542715_3147428552099475_5340464520677315881_n.jpg",
    "505256519_3159364944239169_4636749748837795862_n.jpg",
    "505580052_3157839541058376_7116562050919602601_n.jpg",
    "66517922_1324814401027575_8565450074367197184_n.jpg",
  ],
  portoes: [
    "foto site.jpg",
    "83488618_1518167821692231_4105392928522764288_n.jpg",
    "84256096_1518167665025580_3906247381045215232_n.jpg",
    "84685102_1518168251692188_5088793929382363136_n.jpg",
  ],
  coberturas: [
    "49342436_1192148130960870_2817379300703993856_n.jpg",
    "505650793_3157839741058356_2122482606842207439_n.jpg",
    "505851032_3157839507725046_4602687791854613502_n.jpg",
    "94420860_1585148164994196_6288547422377345024_n.jpg",
  ],
  grades: [
    "49947073_1192148000960883_50225742696415232_n.jpg",
    "505439749_3159365130905817_2448716381801913348_n.jpg",
    "506310057_3160414927467504_1254393314826112784_n.jpg",
  ],
  carrinhos: [
    "49251320_1192150554293961_3208512012321554432_n.jpg",
    "49818620_1192149680960715_6454148966035488768_n.jpg",
    "50085482_1192149610960722_3195089694060707840_n.jpg",
    "506335625_3160414944134169_5942162815006528686_n.jpg",
  ],
  calhasrufos: [],
};

const SITE_MODEL_KEY = "tolepar_site_model";

const CATEGORY_META = [
  {
    key: "all",
    title: "Todos os trabalhos",
    subtitle: "Veja uma amostra geral das obras executadas",
  },
  {
    key: "estruturas",
    title: "Estruturas",
    subtitle: "Projetos metálicos e galpões",
  },
  {
    key: "portoes",
    title: "Portões",
    subtitle: "Serralheria personalizada",
  },
  {
    key: "coberturas",
    title: "Coberturas",
    subtitle: "Coberturas metálicas para obra",
  },
  {
    key: "grades",
    title: "Grades",
    subtitle: "Segurança e acabamento",
  },
  {
    key: "carrinhos",
    title: "Carrinhos",
    subtitle: "Linha reforçada para construção",
  },
  {
    key: "calhasrufos",
    title: "Calhas e Rufos",
    subtitle: "Categoria pronta para receber fotos",
  },
];

let activeAlbumItems = [];
let lightboxIndex = 0;
let editModeEnabled = false;

const HIDDEN_PHOTOS_KEY = "tolepar_hidden_photos";
const CUSTOM_PHOTOS_KEY = "tolepar_custom_photos";
const CUSTOM_VIDEOS_KEY = "tolepar_custom_videos";
const hiddenPhotos = new Set();
let customPhotos = [];
let customVideos = [];

function applySiteModel(model) {
  const selected = model === "model-2" ? "model-2" : "model-1";
  document.body.classList.remove("model-1", "model-2");
  document.body.classList.add(selected);
}

function initSiteModelSwitcher() {
  const select = document.getElementById("siteModel");
  if (!select) return;

  const savedModel = localStorage.getItem(SITE_MODEL_KEY) || "model-1";
  applySiteModel(savedModel);
  select.value = savedModel === "model-2" ? "model-2" : "model-1";

  select.addEventListener("change", () => {
    const selected = select.value === "model-2" ? "model-2" : "model-1";
    applySiteModel(selected);
    localStorage.setItem(SITE_MODEL_KEY, selected);
  });
}

function loadCustomMedia() {
  try {
    const photosRaw = localStorage.getItem(CUSTOM_PHOTOS_KEY);
    const videosRaw = localStorage.getItem(CUSTOM_VIDEOS_KEY);
    customPhotos = photosRaw ? JSON.parse(photosRaw) : [];
    customVideos = videosRaw ? JSON.parse(videosRaw) : [];
    if (!Array.isArray(customPhotos)) customPhotos = [];
    if (!Array.isArray(customVideos)) customVideos = [];
  } catch {
    customPhotos = [];
    customVideos = [];
    localStorage.removeItem(CUSTOM_PHOTOS_KEY);
    localStorage.removeItem(CUSTOM_VIDEOS_KEY);
  }
}

function saveCustomMedia() {
  try {
    localStorage.setItem(CUSTOM_PHOTOS_KEY, JSON.stringify(customPhotos));
    localStorage.setItem(CUSTOM_VIDEOS_KEY, JSON.stringify(customVideos));
  } catch {
    alert("Memória cheia no navegador. Remova algumas mídias manuais.");
  }
}

function fileToDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result || ""));
    reader.onerror = () => reject(new Error("Falha ao ler arquivo"));
    reader.readAsDataURL(file);
  });
}

function renderManualPhotos() {
  const grid = document.getElementById("manualPhotosGrid");
  if (!grid) return;
  grid.innerHTML = "";

  customPhotos.forEach((item, i) => {
    const card = document.createElement("button");
    card.className = "manual-photo-item";
    card.type = "button";
    card.setAttribute("aria-label", `Abrir foto manual ${i + 1}`);
    card.innerHTML = `<img src="${item.src}" alt="Foto manual ${i + 1}" loading="lazy" />`;
    card.addEventListener("click", () => {
      activeAlbumItems = customPhotos.map((p) => ({ src: p.src, cat: "manual" }));
      openLightbox(i);
    });
    grid.appendChild(card);
  });
}

function renderManualVideos() {
  const grid = document.getElementById("manualVideosGrid");
  if (!grid) return;
  grid.innerHTML = "";

  customVideos.forEach((item, i) => {
    const box = document.createElement("article");
    box.className = "manual-video-item";
    box.innerHTML = `
      <video controls preload="metadata">
        <source src="${item.src}" type="${item.type || "video/mp4"}" />
      </video>
    `;
    box.setAttribute("aria-label", `Video manual ${i + 1}`);
    grid.appendChild(box);
  });
}

async function handlePhotoUpload(fileList) {
  const files = Array.from(fileList || []).filter((f) => f.type.startsWith("image/"));
  if (!files.length) return;
  for (const file of files) {
    try {
      const src = await fileToDataUrl(file);
      customPhotos.push({ src, name: file.name, type: file.type });
    } catch {}
  }
  saveCustomMedia();
  renderManualPhotos();
}

async function handleVideoUpload(fileList) {
  const files = Array.from(fileList || []).filter((f) => f.type.startsWith("video/"));
  if (!files.length) return;
  for (const file of files) {
    try {
      const src = await fileToDataUrl(file);
      customVideos.push({ src, name: file.name, type: file.type || "video/mp4" });
    } catch {}
  }
  saveCustomMedia();
  renderManualVideos();
}

function loadHiddenPhotos() {
  hiddenPhotos.clear();
  try {
    const raw = localStorage.getItem(HIDDEN_PHOTOS_KEY);
    if (!raw) return;
    const list = JSON.parse(raw);
    if (Array.isArray(list)) {
      list.forEach((item) => {
        if (typeof item === "string") hiddenPhotos.add(item);
      });
    }
  } catch {
    localStorage.removeItem(HIDDEN_PHOTOS_KEY);
  }
}

function saveHiddenPhotos() {
  localStorage.setItem(HIDDEN_PHOTOS_KEY, JSON.stringify(Array.from(hiddenPhotos)));
}

function hidePhotoBySrc(src) {
  if (!src) return;
  hiddenPhotos.add(src);
  saveHiddenPhotos();
}

function buildItems(category) {
  if (category === "all") {
    return Object.entries(IMAGES)
      .flatMap(([cat, files]) =>
        files.map((file) => ({ src: `images/${cat}/${encodeURIComponent(file)}`, cat }))
      )
      .filter((item) => !hiddenPhotos.has(item.src));
  }

  return (IMAGES[category] || [])
    .map((file) => ({
      src: `images/${category}/${encodeURIComponent(file)}`,
      cat: category,
    }))
    .filter((item) => !hiddenPhotos.has(item.src));
}

function openCategoryAlbum(category, index = 0) {
  activeAlbumItems = buildItems(category);
  if (!activeAlbumItems.length) return;
  openLightbox(index);
}

function buildCategoryCards() {
  const wrap = document.getElementById("galleryCategories");
  if (!wrap) return;

  wrap.innerHTML = "";

  CATEGORY_META.forEach(({ key, title, subtitle }) => {
    const items = buildItems(key);

    const card = document.createElement("article");
    card.className = "album-card";

    const top = document.createElement("div");
    top.className = "album-top";
    top.innerHTML = `
      <div>
        <h3>${title}</h3>
        <p>${subtitle}</p>
      </div>
      <span class="album-count">${items.length} fotos</span>
    `;

    const preview = document.createElement("div");
    preview.className = "album-preview";

    if (items.length) {
      items.slice(0, 4).forEach((item, i) => {
        const thumb = document.createElement("button");
        thumb.className = "album-thumb";
        thumb.type = "button";
        thumb.setAttribute("aria-label", `Abrir ${title} - foto ${i + 1}`);
        thumb.innerHTML = `<img src="${item.src}" alt="${title}" loading="lazy" />`;
        thumb.addEventListener("click", () => openCategoryAlbum(key, i));

        if (editModeEnabled) {
          const delBtn = document.createElement("button");
          delBtn.className = "thumb-delete";
          delBtn.type = "button";
          delBtn.title = "Excluir esta foto da visualização";
          delBtn.textContent = "x";
          delBtn.addEventListener("click", (event) => {
            event.stopPropagation();
            hidePhotoBySrc(item.src);
            buildCategoryCards();
          });
          thumb.appendChild(delBtn);
        }

        preview.appendChild(thumb);
      });
    } else {
      const empty = document.createElement("div");
      empty.className = "album-empty";
      empty.textContent = "Sem fotos por enquanto. Assim que enviar, entra aqui.";
      preview.appendChild(empty);
    }

    const actions = document.createElement("div");
    actions.className = "album-actions";

    const openBtn = document.createElement("button");
    openBtn.className = "btn btn-primary";
    openBtn.type = "button";
    openBtn.textContent = items.length ? "Abrir álbum" : "Sem fotos";
    openBtn.disabled = !items.length;

    if (items.length) {
      openBtn.addEventListener("click", () => openCategoryAlbum(key, 0));
    }

    actions.appendChild(openBtn);

    card.appendChild(top);
    card.appendChild(preview);
    card.appendChild(actions);
    wrap.appendChild(card);
  });
}

function openLightbox(index) {
  lightboxIndex = index;
  const lb = document.getElementById("lightbox");
  const img = document.getElementById("lbImg");

  if (!lb || !img || !activeAlbumItems.length) return;

  img.src = activeAlbumItems[lightboxIndex].src;
  lb.classList.add("open");
  document.body.style.overflow = "hidden";
}

function closeLightbox() {
  const lb = document.getElementById("lightbox");
  if (!lb) return;
  lb.classList.remove("open");
  document.body.style.overflow = "";
}

function moveLightbox(direction) {
  if (!activeAlbumItems.length) return;

  lightboxIndex =
    (lightboxIndex + direction + activeAlbumItems.length) % activeAlbumItems.length;

  const img = document.getElementById("lbImg");
  if (img) img.src = activeAlbumItems[lightboxIndex].src;
}

function syncLightboxDeleteVisibility() {
  const lbDelete = document.getElementById("lbDelete");
  if (!lbDelete) return;
  lbDelete.classList.toggle("hidden", !editModeEnabled);
}

function deleteCurrentLightboxPhoto() {
  if (!activeAlbumItems.length) return;
  const current = activeAlbumItems[lightboxIndex];
  hidePhotoBySrc(current.src);

  activeAlbumItems.splice(lightboxIndex, 1);
  if (!activeAlbumItems.length) {
    closeLightbox();
  } else {
    lightboxIndex = lightboxIndex % activeAlbumItems.length;
    const img = document.getElementById("lbImg");
    if (img) img.src = activeAlbumItems[lightboxIndex].src;
  }

  buildCategoryCards();
}

document.addEventListener("DOMContentLoaded", () => {
  initSiteModelSwitcher();

  const menuBtn = document.getElementById("menuBtn");
  const nav = document.getElementById("mainNav");

  if (menuBtn && nav) {
    menuBtn.addEventListener("click", () => {
      const open = nav.classList.toggle("open");
      menuBtn.setAttribute("aria-expanded", String(open));
    });

    nav.querySelectorAll("a").forEach((link) => {
      link.addEventListener("click", () => nav.classList.remove("open"));
    });
  }

  const year = document.getElementById("year");
  if (year) year.textContent = String(new Date().getFullYear());

  loadHiddenPhotos();
  loadCustomMedia();

  const addPhotosBtn = document.getElementById("addPhotosBtn");
  const addVideosBtn = document.getElementById("addVideosBtn");
  const photoInput = document.getElementById("photoInput");
  const videoInput = document.getElementById("videoInput");

  if (addPhotosBtn && photoInput) {
    addPhotosBtn.addEventListener("click", () => photoInput.click());
    photoInput.addEventListener("change", async () => {
      await handlePhotoUpload(photoInput.files);
      photoInput.value = "";
    });
  }

  if (addVideosBtn && videoInput) {
    addVideosBtn.addEventListener("click", () => videoInput.click());
    videoInput.addEventListener("change", async () => {
      await handleVideoUpload(videoInput.files);
      videoInput.value = "";
    });
  }

  const editToggle = document.getElementById("toggleEditMode");
  const resetHiddenPhotos = document.getElementById("resetHiddenPhotos");

  if (editToggle) {
    editToggle.addEventListener("change", () => {
      editModeEnabled = editToggle.checked;
      buildCategoryCards();
      syncLightboxDeleteVisibility();
    });
  }

  if (resetHiddenPhotos) {
    resetHiddenPhotos.addEventListener("click", () => {
      hiddenPhotos.clear();
      saveHiddenPhotos();
      buildCategoryCards();
    });
  }

  buildCategoryCards();
  renderManualPhotos();
  renderManualVideos();

  const lb = document.getElementById("lightbox");
  const lbClose = document.getElementById("lbClose");
  const lbPrev = document.getElementById("lbPrev");
  const lbNext = document.getElementById("lbNext");
  const lbDelete = document.getElementById("lbDelete");

  if (lbClose) lbClose.addEventListener("click", closeLightbox);
  if (lbPrev) lbPrev.addEventListener("click", () => moveLightbox(-1));
  if (lbNext) lbNext.addEventListener("click", () => moveLightbox(1));
  if (lbDelete) lbDelete.addEventListener("click", deleteCurrentLightboxPhoto);
  syncLightboxDeleteVisibility();

  if (lb) {
    lb.addEventListener("click", (event) => {
      if (event.target === lb) closeLightbox();
    });
  }

  document.addEventListener("keydown", (event) => {
    if (!lb || !lb.classList.contains("open")) return;

    if (event.key === "Escape") closeLightbox();
    if (event.key === "ArrowLeft") moveLightbox(-1);
    if (event.key === "ArrowRight") moveLightbox(1);
  });
});
