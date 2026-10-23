// Dock T(w)oo Settings Console Frontend Logic

let currentConfig = null;
const state = {};

// Elements
const edgeControl = document.getElementById('edgeControl');
const heightModeControl = document.getElementById('heightModeControl');
const themeControl = document.getElementById('themeControl');
const dockWidth = document.getElementById('dockWidth');
const dockWidthVal = document.getElementById('dockWidthVal');
const dockRadius = document.getElementById('dockRadius');
const dockRadiusVal = document.getElementById('dockRadiusVal');
const iconSize = document.getElementById('iconSize');
const iconSizeVal = document.getElementById('iconSizeVal');
const iconSpacing = document.getElementById('iconSpacing');
const iconSpacingVal = document.getElementById('iconSpacingVal');
const iconOpacity = document.getElementById('iconOpacity');
const iconOpacityVal = document.getElementById('iconOpacityVal');
const dockBgColor = document.getElementById('dockBgColor');
const dockBgHex = document.getElementById('dockBgHex');
const iconColor = document.getElementById('iconColor');
const iconColorHex = document.getElementById('iconColorHex');
const dockOpacity = document.getElementById('dockOpacity');
const dockOpacityVal = document.getElementById('dockOpacityVal');
const attachedWidth = document.getElementById('attachedWidth');
const attachedWidthVal = document.getElementById('attachedWidthVal');
const attachedHeight = document.getElementById('attachedHeight');
const attachedHeightVal = document.getElementById('attachedHeightVal');
const attachedGap = document.getElementById('attachedGap');
const attachedGapVal = document.getElementById('attachedGapVal');
const appsList = document.getElementById('appsList');
const desktopMockup = document.getElementById('desktopMockup');
const mockupDock = document.getElementById('mockupDock');
const mockupAttached = document.getElementById('mockupAttached');
const mockupIcons = document.getElementById('mockupIcons');
const previewEdgeLabel = document.getElementById('previewEdgeLabel');
const reserveSpaceToggle = document.getElementById('reserveSpaceToggle');
const autoHideToggle = document.getElementById('autoHideToggle');
const glowToggle = document.getElementById('glowToggle');
const saveBtn = document.getElementById('saveBtn');
const resetBtn = document.getElementById('resetBtn');
const toast = document.getElementById('toast');

// Load config from API
async function loadConfig() {
  try {
    const res = await fetch('/api/config');
    const data = await res.json();
    currentConfig = data;
    initForm(data);
    updatePreview(data);
  } catch (err) {
    console.error('Failed to load config:', err);
    showToast('Failed to connect to Dock T(w)oo', true);
  }
}

// Populate UI form from config object
function initForm(cfg) {
  // Edge
  setSegmentActive(edgeControl, cfg.edge);
  // Height mode
  setSegmentActive(heightModeControl, cfg.dock_height_mode);
  // Theme
  setSegmentActive(themeControl, cfg.theme_mode);

  // Sliders
  dockWidth.value = cfg.dock_width;
  dockWidthVal.textContent = `${cfg.dock_width} px`;

  dockRadius.value = cfg.dock_corner_radius;
  dockRadiusVal.textContent = `${cfg.dock_corner_radius} px`;

  iconSize.value = cfg.icon_size;
  iconSizeVal.textContent = `${cfg.icon_size} px`;

  iconSpacing.value = cfg.icon_spacing;
  iconSpacingVal.textContent = `${cfg.icon_spacing} px`;

  iconOpacity.value = Math.round(cfg.icon_opacity * 100);
  iconOpacityVal.textContent = `${iconOpacity.value}%`;

  dockOpacity.value = Math.round(cfg.dock_opacity * 100);
  dockOpacityVal.textContent = `${dockOpacity.value}%`;

  attachedWidth.value = cfg.attached_width;
  attachedWidthVal.textContent = `${cfg.attached_width} px`;

  attachedHeight.value = cfg.attached_height;
  attachedHeightVal.textContent = `${cfg.attached_height} px`;

  attachedGap.value = cfg.attached_gap;
  attachedGapVal.textContent = `${cfg.attached_gap} px`;

  // Colors
  dockBgColor.value = cfg.dock_bg_color;
  dockBgHex.textContent = cfg.dock_bg_color;

  iconColor.value = cfg.icon_color;
  iconColorHex.textContent = cfg.icon_color;

  // Space & Visibility Toggles
  if (reserveSpaceToggle) reserveSpaceToggle.checked = (cfg.reserve_screen_space !== false);
  if (autoHideToggle) autoHideToggle.checked = !!cfg.auto_hide;
  if (glowToggle) glowToggle.checked = (cfg.glow_enabled !== false);

  // Apps
  renderAppsList(cfg.apps || []);
}

function setSegmentActive(container, value) {
  Array.from(container.querySelectorAll('.segment')).forEach(btn => {
    if (btn.dataset.edge === value || btn.dataset.mode === value || btn.dataset.theme === value) {
      btn.classList.add('active');
    } else {
      btn.classList.remove('active');
    }
  });
}

function renderAppsList(apps) {
  appsList.innerHTML = '';
  apps.forEach((app, idx) => {
    if (app.is_separator) return;

    const row = document.createElement('div');
    row.className = 'app-toggle-item';
    row.innerHTML = `
      <div class="app-toggle-left">
        <div class="app-toggle-icon">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
            <circle cx="12" cy="12" r="6" />
          </svg>
        </div>
        <span class="app-toggle-title">${escapeHtml(app.name)}</span>
      </div>
      <label class="switch">
        <input type="checkbox" data-index="${idx}" ${app.enabled ? 'checked' : ''}>
        <span class="slider-switch"></span>
      </label>
    `;

    const input = row.querySelector('input');
    input.addEventListener('change', () => {
      currentConfig.apps[idx].enabled = input.checked;
      updatePreview(currentConfig);
      autoSave();
    });

    appsList.appendChild(row);
  });
}

function escapeHtml(str) {
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// Live Update Preview Mockup
function updatePreview(cfg) {
  if (!cfg) return;

  // Edge positioning
  if (cfg.edge === 'left') {
    desktopMockup.classList.add('edge-left');
    previewEdgeLabel.textContent = 'Left Edge';
  } else {
    desktopMockup.classList.remove('edge-left');
    previewEdgeLabel.textContent = 'Right Edge';
  }

  // Dock styling
  mockupDock.style.width = `${cfg.dock_width}px`;
  mockupDock.style.borderRadius = `${cfg.dock_corner_radius}px`;
  mockupDock.style.backgroundColor = cfg.dock_bg_color;
  mockupDock.style.opacity = cfg.dock_opacity;
  if (cfg.glow_enabled !== false) {
    mockupDock.style.boxShadow = '0 0 16px rgba(255, 255, 255, 0.28), 0 0 0 1px rgba(255, 255, 255, 0.3)';
    mockupAttached.style.boxShadow = '0 0 18px rgba(255, 255, 255, 0.22), 0 0 0 1px rgba(255, 255, 255, 0.25)';
  } else {
    mockupDock.style.boxShadow = '0 4px 16px rgba(0, 0, 0, 0.3)';
    mockupAttached.style.boxShadow = '0 4px 16px rgba(0, 0, 0, 0.3)';
  }

  // Attached window matches dock height
  mockupAttached.style.width = `${Math.min(260, Math.round(cfg.attached_width * 0.6))}px`;
  mockupAttached.style.height = `94%`;
  mockupAttached.style.top = `3%`;

  // Render dock mockup icons
  mockupIcons.innerHTML = '';
  const apps = cfg.apps || [];

  // Top icons (Notes)
  const topApps = apps.filter(a => !a.is_bottom && a.enabled);
  topApps.forEach(app => {
    const item = document.createElement('div');
    item.className = 'mockup-icon-item active';
    item.title = app.name;
    item.style.color = cfg.icon_color;
    item.style.opacity = cfg.icon_opacity;
    item.innerHTML = `
      <svg viewBox="0 0 24 24" style="width:${cfg.icon_size}px; height:${cfg.icon_size}px" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
        <polyline points="14 2 14 8 20 8"/>
        <line x1="16" y1="13" x2="8" y2="13"/>
        <line x1="16" y1="17" x2="8" y2="17"/>
      </svg>
    `;
    mockupIcons.appendChild(item);
  });

  // Bottom container in mockup
  const bottomContainer = document.querySelector('.mockup-bottom');
  if (bottomContainer) {
    bottomContainer.innerHTML = '';
    const bottomApps = apps.filter(a => a.is_bottom && a.enabled);
    bottomApps.forEach(app => {
      if (app.is_separator) {
        const div = document.createElement('div');
        div.className = 'mockup-dots-div';
        div.style.cssText = 'color:' + cfg.icon_color + '; opacity:0.35; font-size:12px; letter-spacing:2px; line-height:1; user-select:none; margin:2px 0;';
        div.textContent = '•••';
        bottomContainer.appendChild(div);
      } else if (app.id === 'settings') {
        const item = document.createElement('div');
        item.className = 'mockup-icon-item';
        item.title = 'Settings & Console';
        item.style.color = cfg.icon_color;
        item.style.opacity = cfg.icon_opacity;
        item.innerHTML = `
          <svg viewBox="0 0 24 24" style="width:${cfg.icon_size}px; height:${cfg.icon_size}px" fill="none" stroke="currentColor" stroke-width="2">
            <line x1="4" y1="21" x2="4" y2="14" /><line x1="4" y1="10" x2="4" y2="3" />
            <line x1="12" y1="21" x2="12" y2="12" /><line x1="12" y1="8" x2="12" y2="3" />
            <line x1="20" y1="21" x2="20" y2="16" /><line x1="20" y1="12" x2="20" y2="3" />
            <line x1="1" y1="14" x2="7" y2="14" /><line x1="9" y1="8" x2="15" y2="8" /><line x1="17" y1="16" x2="23" y2="16" />
          </svg>
        `;
        bottomContainer.appendChild(item);
      } else if (app.id === 'brain') {
        const item = document.createElement('div');
        item.className = 'mockup-icon-item';
        item.title = 'Brain Voice Assistant';
        item.style.color = cfg.icon_color;
        item.style.opacity = cfg.icon_opacity;
        item.innerHTML = `
          <svg viewBox="0 0 24 24" style="width:${cfg.icon_size}px; height:${cfg.icon_size}px" fill="none" stroke="currentColor" stroke-width="1.8">
            <line x1="12" y1="2" x2="12" y2="4.5" />
            <circle cx="12" cy="2" r="1" fill="currentColor" stroke="none" />
            <rect x="1.5" y="10" width="2" height="6" rx="1" />
            <rect x="20.5" y="10" width="2" height="6" rx="1" />
            <rect x="3.5" y="4.5" width="17" height="15.5" rx="4.5" />
            <rect x="6" y="7.5" width="12" height="10" rx="2.5" stroke-width="1.2" />
            <circle cx="9" cy="12" r="1.2" fill="currentColor" stroke="none" />
            <circle cx="15" cy="12" r="1.2" fill="currentColor" stroke="none" />
            <path d="M10.2 14.6 Q12 16.2 13.8 14.6" stroke-width="1.2" fill="none" />
          </svg>
        `;
        bottomContainer.appendChild(item);
      }
    });
  }
}

// Attach Event Listeners
edgeControl.addEventListener('click', (e) => {
  const btn = e.target.closest('.segment');
  if (!btn) return;
  setSegmentActive(edgeControl, btn.dataset.edge);
  currentConfig.edge = btn.dataset.edge;
  updatePreview(currentConfig);
  autoSave();
});

heightModeControl.addEventListener('click', (e) => {
  const btn = e.target.closest('.segment');
  if (!btn) return;
  setSegmentActive(heightModeControl, btn.dataset.mode);
  currentConfig.dock_height_mode = btn.dataset.mode;
  updatePreview(currentConfig);
  autoSave();
});

themeControl.addEventListener('click', (e) => {
  const btn = e.target.closest('.segment');
  if (!btn) return;
  setSegmentActive(themeControl, btn.dataset.theme);
  currentConfig.theme_mode = btn.dataset.theme;
  if (btn.dataset.theme === 'light') {
    document.body.className = 'theme-light';
  } else {
    document.body.className = 'theme-dark';
  }
  updatePreview(currentConfig);
  autoSave();
});

// Real-time Slider Listeners
dockWidth.addEventListener('input', (e) => {
  const val = parseInt(e.target.value);
  dockWidthVal.textContent = `${val} px`;
  currentConfig.dock_width = val;
  updatePreview(currentConfig);
});
dockWidth.addEventListener('change', autoSave);

dockRadius.addEventListener('input', (e) => {
  const val = parseInt(e.target.value);
  dockRadiusVal.textContent = `${val} px`;
  currentConfig.dock_corner_radius = val;
  updatePreview(currentConfig);
});
dockRadius.addEventListener('change', autoSave);

iconSize.addEventListener('input', (e) => {
  const val = parseInt(e.target.value);
  iconSizeVal.textContent = `${val} px`;
  currentConfig.icon_size = val;
  updatePreview(currentConfig);
});
iconSize.addEventListener('change', autoSave);

iconSpacing.addEventListener('input', (e) => {
  const val = parseInt(e.target.value);
  iconSpacingVal.textContent = `${val} px`;
  currentConfig.icon_spacing = val;
  updatePreview(currentConfig);
});
iconSpacing.addEventListener('change', autoSave);

iconOpacity.addEventListener('input', (e) => {
  const val = parseInt(e.target.value);
  iconOpacityVal.textContent = `${val}%`;
  currentConfig.icon_opacity = val / 100;
  updatePreview(currentConfig);
});
iconOpacity.addEventListener('change', autoSave);

dockOpacity.addEventListener('input', (e) => {
  const val = parseInt(e.target.value);
  dockOpacityVal.textContent = `${val}%`;
  currentConfig.dock_opacity = val / 100;
  updatePreview(currentConfig);
});
dockOpacity.addEventListener('change', autoSave);

attachedWidth.addEventListener('input', (e) => {
  const val = parseInt(e.target.value);
  attachedWidthVal.textContent = `${val} px`;
  currentConfig.attached_width = val;
  updatePreview(currentConfig);
});
attachedWidth.addEventListener('change', autoSave);

attachedHeight.addEventListener('input', (e) => {
  const val = parseInt(e.target.value);
  attachedHeightVal.textContent = `${val} px`;
  currentConfig.attached_height = val;
  updatePreview(currentConfig);
});
attachedHeight.addEventListener('change', autoSave);

attachedGap.addEventListener('input', (e) => {
  const val = parseInt(e.target.value);
  attachedGapVal.textContent = `${val} px`;
  currentConfig.attached_gap = val;
  updatePreview(currentConfig);
});
attachedGap.addEventListener('change', autoSave);

dockBgColor.addEventListener('input', (e) => {
  dockBgHex.textContent = e.target.value;
  currentConfig.dock_bg_color = e.target.value;
  updatePreview(currentConfig);
});
dockBgColor.addEventListener('change', autoSave);

iconColor.addEventListener('input', (e) => {
  iconColorHex.textContent = e.target.value;
  currentConfig.icon_color = e.target.value;
  updatePreview(currentConfig);
});
iconColor.addEventListener('change', autoSave);

if (reserveSpaceToggle) {
  reserveSpaceToggle.addEventListener('change', () => {
    currentConfig.reserve_screen_space = reserveSpaceToggle.checked;
    autoSave();
  });
}

if (autoHideToggle) {
  autoHideToggle.addEventListener('change', () => {
    currentConfig.auto_hide = autoHideToggle.checked;
    autoSave();
  });
}

if (glowToggle) {
  glowToggle.addEventListener('change', () => {
    currentConfig.glow_enabled = glowToggle.checked;
    updatePreview(currentConfig);
    autoSave();
  });
}

// Save / Reset
let debounceTimer = null;
function autoSave() {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(saveConfig, 300);
}

async function saveConfig() {
  if (!currentConfig) return;
  try {
    const res = await fetch('/api/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(currentConfig),
    });
    const data = await res.json();
    if (data.success) {
      showToast('Settings saved & applied to Dock');
    }
  } catch (err) {
    console.error('Failed to save config:', err);
    showToast('Error saving settings', true);
  }
}

saveBtn.addEventListener('click', saveConfig);

resetBtn.addEventListener('click', async () => {
  if (!confirm('Reset all Dock T(w)oo settings to default values?')) return;
  try {
    const res = await fetch('/api/reset', { method: 'POST' });
    const data = await res.json();
    if (data.success) {
      currentConfig = data.config;
      initForm(currentConfig);
      updatePreview(currentConfig);
      showToast('Reset to default settings');
    }
  } catch (err) {
    console.error('Failed to reset config:', err);
    showToast('Failed to reset settings', true);
  }
});

function showToast(msg, isError = false) {
  toast.textContent = msg;
  toast.style.background = isError ? '#ef4444' : '#10b981';
  toast.classList.add('show');
  setTimeout(() => toast.classList.remove('show'), 2400);
}

// Initial load
loadConfig();
