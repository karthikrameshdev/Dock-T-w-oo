// Dock T(w)oo Modern Multipage Settings Console Logic

let currentConfig = null;
let debounceTimer = null;

// DOM Elements
const consoleBody = document.getElementById('consoleBody');
const togglePreviewBtn = document.getElementById('togglePreviewBtn');
const settingsSearch = document.getElementById('settingsSearch');
const navItems = document.querySelectorAll('.nav-item');
const pageViews = document.querySelectorAll('.page-view');
const toast = document.getElementById('toast');
const saveBtn = document.getElementById('saveBtn');
const resetBtn = document.getElementById('resetBtn');

// Placement & Sizing Controls
const edgeControl = document.getElementById('edgeControl');
const dockWidth = document.getElementById('dockWidth');
const dockWidthVal = document.getElementById('dockWidthVal');
const heightModeControl = document.getElementById('heightModeControl');
const fixedHeightGroup = document.getElementById('fixedHeightGroup');
const dockHeightFixed = document.getElementById('dockHeightFixed');
const dockHeightFixedVal = document.getElementById('dockHeightFixedVal');
const dockRadius = document.getElementById('dockRadius');
const dockRadiusVal = document.getElementById('dockRadiusVal');
const edgeOffsetX = document.getElementById('edgeOffsetX');
const edgeOffsetXVal = document.getElementById('edgeOffsetXVal');

// Appearance Controls
const themeControl = document.getElementById('themeControl');
const dockBgColor = document.getElementById('dockBgColor');
const dockBgHex = document.getElementById('dockBgHex');
const iconColor = document.getElementById('iconColor');
const iconColorHex = document.getElementById('iconColorHex');
const dockOpacity = document.getElementById('dockOpacity');
const dockOpacityVal = document.getElementById('dockOpacityVal');
const iconSize = document.getElementById('iconSize');
const iconSizeVal = document.getElementById('iconSizeVal');
const iconSpacing = document.getElementById('iconSpacing');
const iconSpacingVal = document.getElementById('iconSpacingVal');
const iconOpacity = document.getElementById('iconOpacity');
const iconOpacityVal = document.getElementById('iconOpacityVal');
const glowToggle = document.getElementById('glowToggle');

// Desktop & Work Area Controls
const reserveSpaceToggle = document.getElementById('reserveSpaceToggle');
const screenMarginGap = document.getElementById('screenMarginGap');
const screenMarginGapVal = document.getElementById('screenMarginGapVal');
const autoHideToggle = document.getElementById('autoHideToggle');

// Companion Drawers Controls
const attachedWidth = document.getElementById('attachedWidth');
const attachedWidthVal = document.getElementById('attachedWidthVal');
const attachedHeight = document.getElementById('attachedHeight');
const attachedHeightVal = document.getElementById('attachedHeightVal');
const attachedGap = document.getElementById('attachedGap');
const attachedGapVal = document.getElementById('attachedGapVal');
const attachedCornerRadius = document.getElementById('attachedCornerRadius');
const attachedCornerRadiusVal = document.getElementById('attachedCornerRadiusVal');

// Notes App Controls
const notesDefaultTitle = document.getElementById('notesDefaultTitle');
const notesAutoSave = document.getElementById('notesAutoSave');
const notesSortBy = document.getElementById('notesSortBy');
const notesFontSize = document.getElementById('notesFontSize');
const notesFontSizeVal = document.getElementById('notesFontSizeVal');
const notesMarkdownToggle = document.getElementById('notesMarkdownToggle');
const notesSpellcheckToggle = document.getElementById('notesSpellcheckToggle');

// Brain Voice Assistant Controls
const brainWakeWordToggle = document.getElementById('brainWakeWordToggle');
const brainWakeWord = document.getElementById('brainWakeWord');
const brainVoiceGender = document.getElementById('brainVoiceGender');
const brainOrbTheme = document.getElementById('brainOrbTheme');
const brainSpeechRate = document.getElementById('brainSpeechRate');
const brainSpeechRateVal = document.getElementById('brainSpeechRateVal');
const brainAutoListenToggle = document.getElementById('brainAutoListenToggle');
const brainHistoryToggle = document.getElementById('brainHistoryToggle');
const brainMicSensitivity = document.getElementById('brainMicSensitivity');
const brainMicSensitivityVal = document.getElementById('brainMicSensitivityVal');

// Vault Controls
const vaultAutoLock = document.getElementById('vaultAutoLock');
const vaultClearClipboard = document.getElementById('vaultClearClipboard');
const vaultMaskToggle = document.getElementById('vaultMaskToggle');
const vaultBiometricToggle = document.getElementById('vaultBiometricToggle');

// Apps List & Preview Controls
const appsList = document.getElementById('appsList');
const desktopMockup = document.getElementById('desktopMockup');
const mockupDock = document.getElementById('mockupDock');
const mockupAttached = document.getElementById('mockupAttached');
const mockupIcons = document.getElementById('mockupIcons');
const previewEdgeLabel = document.getElementById('previewEdgeLabel');

// Navigation Tab Switching
navItems.forEach(item => {
  item.addEventListener('click', () => {
    const targetPageId = item.dataset.page;
    if (!targetPageId) return;

    navItems.forEach(nav => nav.classList.remove('active'));
    item.classList.add('active');

    pageViews.forEach(view => {
      if (view.id === targetPageId) {
        view.classList.add('active');
      } else {
        view.classList.remove('active');
      }
    });

    window.scrollTo({ top: 0, behavior: 'smooth' });
  });
});

// Toggle Live Preview
if (togglePreviewBtn) {
  togglePreviewBtn.addEventListener('click', () => {
    consoleBody.classList.toggle('hide-preview');
    const isHidden = consoleBody.classList.contains('hide-preview');
    togglePreviewBtn.classList.toggle('active', !isHidden);
  });
}

// Search & Filter Settings
if (settingsSearch) {
  settingsSearch.addEventListener('input', (e) => {
    const query = e.target.value.toLowerCase().trim();
    if (!query) {
      navItems.forEach(n => n.style.display = '');
      return;
    }

    navItems.forEach(n => {
      const text = n.textContent.toLowerCase();
      n.style.display = text.includes(query) ? '' : 'none';
    });

    // Automatically switch to first matching page
    const firstMatch = Array.from(navItems).find(n => n.style.display !== 'none');
    if (firstMatch && !firstMatch.classList.contains('active')) {
      firstMatch.click();
    }
  });
}

// Load Configuration from API
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

// Populate UI Elements from Config
function initForm(cfg) {
  if (!cfg.app_settings) {
    cfg.app_settings = {
      notes: {},
      brain: {},
      vault: {}
    };
  }

  // 1. Placement & Sizing
  setSegmentActive(edgeControl, cfg.edge);
  setSegmentActive(heightModeControl, cfg.dock_height_mode);
  updateThicknessControl(cfg);
  dockRadius.value = cfg.dock_corner_radius;
  dockRadiusVal.textContent = `${cfg.dock_corner_radius} px`;
  edgeOffsetX.value = cfg.edge_offset_x || 12;
  edgeOffsetXVal.textContent = `${cfg.edge_offset_x || 12} px`;

  if (cfg.dock_height_mode === 'fixed') {
    fixedHeightGroup.style.display = 'flex';
  } else {
    fixedHeightGroup.style.display = 'none';
  }
  dockHeightFixed.value = cfg.dock_height_fixed || 700;
  dockHeightFixedVal.textContent = `${cfg.dock_height_fixed || 700} px`;

  // 2. Appearance & Theme
  setSegmentActive(themeControl, cfg.theme_mode);
  applyThemeBody(cfg.theme_mode);
  dockBgColor.value = cfg.dock_bg_color;
  dockBgHex.textContent = cfg.dock_bg_color;
  iconColor.value = cfg.icon_color;
  iconColorHex.textContent = cfg.icon_color;
  dockOpacity.value = Math.round(cfg.dock_opacity * 100);
  dockOpacityVal.textContent = `${dockOpacity.value}%`;
  iconSize.value = cfg.icon_size;
  iconSizeVal.textContent = `${cfg.icon_size} px`;
  iconSpacing.value = cfg.icon_spacing;
  iconSpacingVal.textContent = `${cfg.icon_spacing} px`;
  iconOpacity.value = Math.round(cfg.icon_opacity * 100);
  iconOpacityVal.textContent = `${iconOpacity.value}%`;
  if (glowToggle) glowToggle.checked = (cfg.glow_enabled !== false);

  // 3. Desktop & Work Area
  if (reserveSpaceToggle) reserveSpaceToggle.checked = (cfg.reserve_screen_space !== false);
  if (screenMarginGap) {
    screenMarginGap.value = cfg.screen_margin_gap || 8;
    screenMarginGapVal.textContent = `${cfg.screen_margin_gap || 8} px`;
  }
  if (autoHideToggle) autoHideToggle.checked = !!cfg.auto_hide;

  // 4. Companion Drawers
  attachedWidth.value = cfg.attached_width;
  attachedWidthVal.textContent = `${cfg.attached_width} px`;
  attachedHeight.value = cfg.attached_height;
  attachedHeightVal.textContent = `${cfg.attached_height} px`;
  attachedGap.value = cfg.attached_gap;
  attachedGapVal.textContent = `${cfg.attached_gap} px`;
  if (attachedCornerRadius) {
    attachedCornerRadius.value = cfg.attached_corner_radius || 20;
    attachedCornerRadiusVal.textContent = `${cfg.attached_corner_radius || 20} px`;
  }

  // 5. Notes App Settings
  const notesCfg = cfg.app_settings.notes || {};
  if (notesDefaultTitle) notesDefaultTitle.value = notesCfg.default_title || 'Untitled Note';
  if (notesAutoSave) notesAutoSave.value = notesCfg.auto_save_interval_sec || '1';
  if (notesSortBy) notesSortBy.value = notesCfg.sort_by || 'updated_desc';
  if (notesFontSize) {
    notesFontSize.value = notesCfg.font_size || 13;
    notesFontSizeVal.textContent = `${notesCfg.font_size || 13} px`;
  }
  if (notesMarkdownToggle) notesMarkdownToggle.checked = (notesCfg.markdown_preview !== false);
  if (notesSpellcheckToggle) notesSpellcheckToggle.checked = (notesCfg.spell_check !== false);

  // 6. Brain App Settings
  const brainCfg = cfg.app_settings.brain || {};
  if (brainWakeWordToggle) brainWakeWordToggle.checked = (brainCfg.wake_word_enabled !== false);
  if (brainWakeWord) brainWakeWord.value = brainCfg.wake_word || 'Hey Brain';
  if (brainVoiceGender) brainVoiceGender.value = brainCfg.voice_gender || 'neutral';
  if (brainOrbTheme) brainOrbTheme.value = brainCfg.orb_theme || 'neon_cyan';
  if (brainSpeechRate) {
    const rateVal = Math.round((brainCfg.speech_rate || 1.0) * 100);
    brainSpeechRate.value = rateVal;
    brainSpeechRateVal.textContent = `${(rateVal / 100).toFixed(1)}x`;
  }
  if (brainAutoListenToggle) brainAutoListenToggle.checked = !!brainCfg.auto_listen_on_open;
  if (brainHistoryToggle) brainHistoryToggle.checked = (brainCfg.keep_conversation_history !== false);
  if (brainMicSensitivity) {
    brainMicSensitivity.value = brainCfg.mic_sensitivity || 75;
    brainMicSensitivityVal.textContent = `${brainCfg.mic_sensitivity || 75}%`;
  }

  // 7. Vault App Settings
  const vaultCfg = cfg.app_settings.vault || {};
  if (vaultAutoLock) vaultAutoLock.value = vaultCfg.auto_lock_minutes !== undefined ? vaultCfg.auto_lock_minutes : '5';
  if (vaultClearClipboard) vaultClearClipboard.value = vaultCfg.clear_clipboard_seconds !== undefined ? vaultCfg.clear_clipboard_seconds : '30';
  if (vaultMaskToggle) vaultMaskToggle.checked = (vaultCfg.mask_passwords_by_default !== false);
  if (vaultBiometricToggle) vaultBiometricToggle.checked = (vaultCfg.biometric_unlock !== false);

  // 8. Apps List
  renderAppsList(cfg.apps || []);
}

function setSegmentActive(container, value) {
  if (!container) return;
  Array.from(container.querySelectorAll('.segment')).forEach(btn => {
    if (btn.dataset.edge === value || btn.dataset.mode === value || btn.dataset.theme === value) {
      btn.classList.add('active');
    } else {
      btn.classList.remove('active');
    }
  });
}

function applyThemeBody(theme) {
  if (theme === 'light') {
    document.body.className = 'theme-light';
  } else {
    document.body.className = 'theme-dark';
  }
}

function renderAppsList(apps) {
  if (!appsList) return;
  appsList.innerHTML = '';
  apps.forEach((app, idx) => {
    if (app.is_separator) return;

    const row = document.createElement('div');
    row.className = 'app-toggle-item';
    row.innerHTML = `
      <div class="app-toggle-left">
        <div class="app-toggle-icon">
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2">
            <circle cx="12" cy="12" r="9"/>
            <polyline points="12 6 12 12 16 14"/>
          </svg>
        </div>
        <div>
          <span class="app-toggle-title">${escapeHtml(app.name)}</span>
          <p style="font-size: 11px; color: var(--text-muted); margin: 0;">${escapeHtml(app.tooltip || app.name)}</p>
        </div>
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
  return (str || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function updateThicknessControl(cfg) {
  const dockWidthLabel = document.getElementById('dockWidthLabel');
  const dockWidthHelp = document.getElementById('dockWidthHelp');
  const isHoriz = (cfg.edge === 'top' || cfg.edge === 'bottom');
  if (isHoriz) {
    if (dockWidthLabel) dockWidthLabel.textContent = 'Dock Height';
    if (dockWidthHelp) dockWidthHelp.textContent = 'Capsule cross-axis height along the screen edge';
    const val = (cfg.dock_height !== undefined ? cfg.dock_height : (cfg.dock_width || 60));
    dockWidth.value = val;
    dockWidthVal.textContent = `${val} px`;
  } else {
    if (dockWidthLabel) dockWidthLabel.textContent = 'Dock Width';
    if (dockWidthHelp) dockWidthHelp.textContent = 'Capsule cross-axis width along the screen edge';
    const val = cfg.dock_width || 60;
    dockWidth.value = val;
    dockWidthVal.textContent = `${val} px`;
  }
}

// Live Update Desktop Preview Mockup
function updatePreview(cfg) {
  if (!cfg || !desktopMockup || !mockupDock) return;

  // 1. Edge orientation
  desktopMockup.classList.remove('edge-left', 'edge-top', 'edge-bottom');
  if (cfg.edge === 'left') {
    desktopMockup.classList.add('edge-left');
    previewEdgeLabel.textContent = 'Left Edge';
  } else if (cfg.edge === 'top') {
    desktopMockup.classList.add('edge-top');
    previewEdgeLabel.textContent = 'Top Edge';
  } else if (cfg.edge === 'bottom') {
    desktopMockup.classList.add('edge-bottom');
    previewEdgeLabel.textContent = 'Bottom Edge';
  } else {
    previewEdgeLabel.textContent = 'Right Edge';
  }

  // 2. Dock Dimensions & Styling
  const isHoriz = (cfg.edge === 'top' || cfg.edge === 'bottom');
  const thickness = isHoriz
    ? (cfg.dock_height !== undefined ? cfg.dock_height : (cfg.dock_width || 60))
    : (cfg.dock_width || 60);

  if (isHoriz) {
    mockupDock.style.height = `${thickness}px`;
    mockupDock.style.width = '90%';
  } else {
    mockupDock.style.width = `${thickness}px`;
    mockupDock.style.height = '90%';
  }
  mockupDock.style.borderRadius = `${cfg.dock_corner_radius}px`;
  mockupDock.style.backgroundColor = cfg.dock_bg_color;
  mockupDock.style.opacity = cfg.dock_opacity;

  if (cfg.glow_enabled !== false) {
    mockupDock.style.boxShadow = '0 0 16px rgba(255, 255, 255, 0.28), 0 0 0 1px rgba(255, 255, 255, 0.3)';
    if (mockupAttached) {
      mockupAttached.style.boxShadow = '0 0 18px rgba(255, 255, 255, 0.22), 0 0 0 1px rgba(255, 255, 255, 0.25)';
    }
  } else {
    mockupDock.style.boxShadow = '0 4px 16px rgba(0, 0, 0, 0.4)';
    if (mockupAttached) {
      mockupAttached.style.boxShadow = '0 4px 16px rgba(0, 0, 0, 0.4)';
    }
  }

  // 3. Attached Drawer Sizing
  if (mockupAttached) {
    mockupAttached.style.width = `${Math.min(240, Math.round(cfg.attached_width * 0.6))}px`;
    mockupAttached.style.borderRadius = `${cfg.attached_corner_radius || 18}px`;
  }

  // 4. Render App Icons
  if (mockupIcons) {
    mockupIcons.innerHTML = '';
    const apps = cfg.apps || [];

    const topApps = apps.filter(a => !a.is_bottom && a.enabled);
    topApps.forEach(app => {
      const item = document.createElement('div');
      item.className = 'mockup-icon-item active';
      item.title = app.name;
      item.style.color = cfg.icon_color;
      item.style.opacity = cfg.icon_opacity;
      if (app.icon === 'vault') {
        item.innerHTML = `
          <svg viewBox="0 0 24 24" style="width:${cfg.icon_size}px; height:${cfg.icon_size}px" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
            <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
            <path d="M7 11V7a5 5 0 0 1 10 0v4" />
            <circle cx="12" cy="16.5" r="1.5" fill="currentColor" stroke="none" />
            <line x1="12" y1="18" x2="12" y2="20" stroke-width="2" />
          </svg>
        `;
      } else {
        item.innerHTML = `
          <svg viewBox="0 0 24 24" style="width:${cfg.icon_size}px; height:${cfg.icon_size}px" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
            <polyline points="14 2 14 8 20 8"/>
            <line x1="16" y1="13" x2="8" y2="13"/>
            <line x1="16" y1="17" x2="8" y2="17"/>
          </svg>
        `;
      }
      mockupIcons.appendChild(item);
    });
  }

  // 5. Render Bottom Items (Settings, Brain)
  const bottomContainer = document.querySelector('.mockup-bottom');
  if (bottomContainer) {
    bottomContainer.innerHTML = '';
    const bottomApps = (cfg.apps || []).filter(a => a.is_bottom && a.enabled);
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
        item.title = 'Settings';
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
        item.title = 'Brain';
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

// Attach Event Listeners to Controls

// Edge Selection
if (edgeControl) {
  edgeControl.addEventListener('click', (e) => {
    const btn = e.target.closest('.segment');
    if (!btn) return;
    setSegmentActive(edgeControl, btn.dataset.edge);
    currentConfig.edge = btn.dataset.edge;
    updateThicknessControl(currentConfig);
    updatePreview(currentConfig);
    autoSave();
  });
}

// Height Mode Selection
if (heightModeControl) {
  heightModeControl.addEventListener('click', (e) => {
    const btn = e.target.closest('.segment');
    if (!btn) return;
    setSegmentActive(heightModeControl, btn.dataset.mode);
    currentConfig.dock_height_mode = btn.dataset.mode;
    if (btn.dataset.mode === 'fixed') {
      fixedHeightGroup.style.display = 'flex';
    } else {
      fixedHeightGroup.style.display = 'none';
    }
    updatePreview(currentConfig);
    autoSave();
  });
}

// Theme Selection
if (themeControl) {
  themeControl.addEventListener('click', (e) => {
    const btn = e.target.closest('.segment');
    if (!btn) return;
    setSegmentActive(themeControl, btn.dataset.theme);
    currentConfig.theme_mode = btn.dataset.theme;
    applyThemeBody(btn.dataset.theme);
    updatePreview(currentConfig);
    autoSave();
  });
}

// Placement Sliders
dockWidth.addEventListener('input', (e) => {
  const val = parseInt(e.target.value);
  dockWidthVal.textContent = `${val} px`;
  if (currentConfig.edge === 'top' || currentConfig.edge === 'bottom') {
    currentConfig.dock_height = val;
  } else {
    currentConfig.dock_width = val;
  }
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

edgeOffsetX.addEventListener('input', (e) => {
  const val = parseInt(e.target.value);
  edgeOffsetXVal.textContent = `${val} px`;
  currentConfig.edge_offset_x = val;
  updatePreview(currentConfig);
});
edgeOffsetX.addEventListener('change', autoSave);

dockHeightFixed.addEventListener('input', (e) => {
  const val = parseInt(e.target.value);
  dockHeightFixedVal.textContent = `${val} px`;
  currentConfig.dock_height_fixed = val;
  updatePreview(currentConfig);
});
dockHeightFixed.addEventListener('change', autoSave);

// Appearance Inputs
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

dockOpacity.addEventListener('input', (e) => {
  const val = parseInt(e.target.value);
  dockOpacityVal.textContent = `${val}%`;
  currentConfig.dock_opacity = val / 100;
  updatePreview(currentConfig);
});
dockOpacity.addEventListener('change', autoSave);

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

if (glowToggle) {
  glowToggle.addEventListener('change', () => {
    currentConfig.glow_enabled = glowToggle.checked;
    updatePreview(currentConfig);
    autoSave();
  });
}

// Desktop & Work Area
if (reserveSpaceToggle) {
  reserveSpaceToggle.addEventListener('change', () => {
    currentConfig.reserve_screen_space = reserveSpaceToggle.checked;
    autoSave();
  });
}

if (screenMarginGap) {
  screenMarginGap.addEventListener('input', (e) => {
    const val = parseInt(e.target.value);
    screenMarginGapVal.textContent = `${val} px`;
    currentConfig.screen_margin_gap = val;
  });
  screenMarginGap.addEventListener('change', autoSave);
}

if (autoHideToggle) {
  autoHideToggle.addEventListener('change', () => {
    currentConfig.auto_hide = autoHideToggle.checked;
    autoSave();
  });
}

// Drawers
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

if (attachedCornerRadius) {
  attachedCornerRadius.addEventListener('input', (e) => {
    const val = parseInt(e.target.value);
    attachedCornerRadiusVal.textContent = `${val} px`;
    currentConfig.attached_corner_radius = val;
    updatePreview(currentConfig);
  });
  attachedCornerRadius.addEventListener('change', autoSave);
}

// Individual App Settings: Notes
function ensureAppSettings() {
  if (!currentConfig.app_settings) currentConfig.app_settings = {};
  if (!currentConfig.app_settings.notes) currentConfig.app_settings.notes = {};
  if (!currentConfig.app_settings.brain) currentConfig.app_settings.brain = {};
  if (!currentConfig.app_settings.vault) currentConfig.app_settings.vault = {};
}

if (notesDefaultTitle) {
  notesDefaultTitle.addEventListener('change', (e) => {
    ensureAppSettings();
    currentConfig.app_settings.notes.default_title = e.target.value;
    autoSave();
  });
}

if (notesAutoSave) {
  notesAutoSave.addEventListener('change', (e) => {
    ensureAppSettings();
    currentConfig.app_settings.notes.auto_save_interval_sec = parseInt(e.target.value);
    autoSave();
  });
}

if (notesSortBy) {
  notesSortBy.addEventListener('change', (e) => {
    ensureAppSettings();
    currentConfig.app_settings.notes.sort_by = e.target.value;
    autoSave();
  });
}

if (notesFontSize) {
  notesFontSize.addEventListener('input', (e) => {
    const val = parseInt(e.target.value);
    notesFontSizeVal.textContent = `${val} px`;
    ensureAppSettings();
    currentConfig.app_settings.notes.font_size = val;
  });
  notesFontSize.addEventListener('change', autoSave);
}

if (notesMarkdownToggle) {
  notesMarkdownToggle.addEventListener('change', (e) => {
    ensureAppSettings();
    currentConfig.app_settings.notes.markdown_preview = e.target.checked;
    autoSave();
  });
}

if (notesSpellcheckToggle) {
  notesSpellcheckToggle.addEventListener('change', (e) => {
    ensureAppSettings();
    currentConfig.app_settings.notes.spell_check = e.target.checked;
    autoSave();
  });
}

// Individual App Settings: Brain
if (brainWakeWordToggle) {
  brainWakeWordToggle.addEventListener('change', (e) => {
    ensureAppSettings();
    currentConfig.app_settings.brain.wake_word_enabled = e.target.checked;
    autoSave();
  });
}

if (brainWakeWord) {
  brainWakeWord.addEventListener('change', (e) => {
    ensureAppSettings();
    currentConfig.app_settings.brain.wake_word = e.target.value;
    autoSave();
  });
}

if (brainVoiceGender) {
  brainVoiceGender.addEventListener('change', (e) => {
    ensureAppSettings();
    currentConfig.app_settings.brain.voice_gender = e.target.value;
    autoSave();
  });
}

if (brainOrbTheme) {
  brainOrbTheme.addEventListener('change', (e) => {
    ensureAppSettings();
    currentConfig.app_settings.brain.orb_theme = e.target.value;
    autoSave();
  });
}

if (brainSpeechRate) {
  brainSpeechRate.addEventListener('input', (e) => {
    const val = parseInt(e.target.value);
    brainSpeechRateVal.textContent = `${(val / 100).toFixed(1)}x`;
    ensureAppSettings();
    currentConfig.app_settings.brain.speech_rate = val / 100;
  });
  brainSpeechRate.addEventListener('change', autoSave);
}

if (brainAutoListenToggle) {
  brainAutoListenToggle.addEventListener('change', (e) => {
    ensureAppSettings();
    currentConfig.app_settings.brain.auto_listen_on_open = e.target.checked;
    autoSave();
  });
}

if (brainHistoryToggle) {
  brainHistoryToggle.addEventListener('change', (e) => {
    ensureAppSettings();
    currentConfig.app_settings.brain.keep_conversation_history = e.target.checked;
    autoSave();
  });
}

if (brainMicSensitivity) {
  brainMicSensitivity.addEventListener('input', (e) => {
    const val = parseInt(e.target.value);
    brainMicSensitivityVal.textContent = `${val}%`;
    ensureAppSettings();
    currentConfig.app_settings.brain.mic_sensitivity = val;
  });
  brainMicSensitivity.addEventListener('change', autoSave);
}

// Individual App Settings: Vault
if (vaultAutoLock) {
  vaultAutoLock.addEventListener('change', (e) => {
    ensureAppSettings();
    currentConfig.app_settings.vault.auto_lock_minutes = parseInt(e.target.value);
    autoSave();
  });
}

if (vaultClearClipboard) {
  vaultClearClipboard.addEventListener('change', (e) => {
    ensureAppSettings();
    currentConfig.app_settings.vault.clear_clipboard_seconds = parseInt(e.target.value);
    autoSave();
  });
}

if (vaultMaskToggle) {
  vaultMaskToggle.addEventListener('change', (e) => {
    ensureAppSettings();
    currentConfig.app_settings.vault.mask_passwords_by_default = e.target.checked;
    autoSave();
  });
}

if (vaultBiometricToggle) {
  vaultBiometricToggle.addEventListener('change', (e) => {
    ensureAppSettings();
    currentConfig.app_settings.vault.biometric_unlock = e.target.checked;
    autoSave();
  });
}

// System Actions
const openNotesFolderBtn = document.getElementById('openNotesFolderBtn');
if (openNotesFolderBtn) {
  openNotesFolderBtn.addEventListener('click', () => {
    showToast('Notes folder: ~/.dock_twoo/notes/');
  });
}

const resetAllSettingsBtn = document.getElementById('resetAllSettingsBtn');
if (resetAllSettingsBtn) {
  resetAllSettingsBtn.addEventListener('click', () => {
    if (resetBtn) resetBtn.click();
  });
}

// Debounced Auto-Save & Manual Save
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

if (saveBtn) saveBtn.addEventListener('click', saveConfig);

if (resetBtn) {
  resetBtn.addEventListener('click', async () => {
    if (!confirm('Reset all Dock T(w)oo settings to default factory values?')) return;
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
}

function showToast(msg, isError = false) {
  if (!toast) return;
  toast.textContent = msg;
  toast.style.background = isError ? '#ef4444' : '#10b981';
  toast.classList.add('show');
  setTimeout(() => toast.classList.remove('show'), 2400);
}

// Initial Load
loadConfig();
initBrainConsole();

// Brain Voice Assistant Console Module
async function initBrainConsole() {
  const agentStatusBadge = document.getElementById('brainAgentStatusBadge');
  const summonBtn = document.getElementById('brainSummonBtn');
  const hideBtn = document.getElementById('brainHideBtn');
  const talkBtn = document.getElementById('brainTalkBtn');
  const loopAnimBtn = document.getElementById('brainLoopAnimBtn');
  const activeProfileSel = document.getElementById('brainActiveProfile');
  const providerSel = document.getElementById('brainProvider');
  const modelIdInput = document.getElementById('brainModelId');
  const baseUrlInput = document.getElementById('brainBaseUrl');
  const apiKeyInput = document.getElementById('brainApiKey');
  const saveKeyBtn = document.getElementById('brainSaveKeyBtn');
  const keyStatusHint = document.getElementById('brainKeyStatusHint');
  const localOnlyToggle = document.getElementById('brainLocalOnlyToggle');
  const voiceNameSel = document.getElementById('brainVoiceName');
  const speechRateSlider = document.getElementById('brainSpeechRate');
  const speechRateVal = document.getElementById('brainSpeechRateVal');
  const voiceStyleInput = document.getElementById('brainVoiceStyle');
  const speakRepliesToggle = document.getElementById('brainSpeakRepliesToggle');
  const roamingToggle = document.getElementById('brainRoamingToggle');
  const mascotPoseSel = document.getElementById('brainMascotPose');
  const mascotCornerSel = document.getElementById('brainMascotCorner');
  const reduceMotionToggle = document.getElementById('brainReduceMotionToggle');
  const wakeWordToggle = document.getElementById('brainWakeWordToggle');
  const wakeWordInput = document.getElementById('brainWakeWord');
  const pushToTalkSel = document.getElementById('brainPushToTalkKey');

  // Brain Multi-Tab Switching Logic
  document.querySelectorAll('.brain-tab-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.brain-tab-btn').forEach((b) => b.classList.remove('active'));
      document.querySelectorAll('.brain-tab-panel').forEach((p) => p.classList.remove('active'));
      btn.classList.add('active');
      const targetPanel = document.getElementById(btn.dataset.tab);
      if (targetPanel) targetPanel.classList.add('active');
    });
  });

  // Robotic Animation Buttons
  document.querySelectorAll('.brain-anim-trigger').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const animName = btn.dataset.anim;
      try {
        await fetch('/api/brain/action', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action: 'animation', name: animName }),
        });
        showToast(`Playing ${animName.replace('_', ' ')} animation`);
      } catch (err) {
        showToast('Animation trigger failed', true);
      }
    });
  });

  // Quick Action Buttons
  if (summonBtn) {
    summonBtn.addEventListener('click', async () => {
      await fetch('/api/brain/action', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'summon' }),
      });
      showToast('Summoned Mini Agent on desktop');
      loadBrainStatus();
    });
  }

  if (hideBtn) {
    hideBtn.addEventListener('click', async () => {
      await fetch('/api/brain/action', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'hide' }),
      });
      showToast('Mini Agent hidden');
      loadBrainStatus();
    });
  }

  if (talkBtn) {
    talkBtn.addEventListener('click', async () => {
      await fetch('/api/brain/action', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'talk' }),
      });
      showToast('Listening for speech turn…');
      loadBrainStatus();
    });
  }

  if (loopAnimBtn) {
    loopAnimBtn.addEventListener('click', async () => {
      await fetch('/api/brain/action', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'animation', name: 'loop' }),
      });
      showToast('Playing animation sequence');
    });
  }

  if (speechRateSlider && speechRateVal) {
    speechRateSlider.addEventListener('input', () => {
      const val = (speechRateSlider.value / 100).toFixed(1);
      speechRateVal.textContent = `${val}x`;
      saveBrainSettings({ speech_rate: parseFloat(val) });
    });
  }

  if (saveKeyBtn && apiKeyInput) {
    saveKeyBtn.addEventListener('click', async () => {
      const provider = providerSel ? providerSel.value : 'gemini';
      const keyVal = apiKeyInput.value.trim();
      if (!keyVal) {
        showToast('Please enter an API Key', true);
        return;
      }
      try {
        const res = await fetch('/api/brain/key', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ provider, key: keyVal }),
        });
        const data = await res.json();
        if (data.success) {
          showToast(`${provider.toUpperCase()} API Key saved`);
          if (keyStatusHint) keyStatusHint.textContent = `Key configured for ${provider}`;
          apiKeyInput.value = '';
        }
      } catch (err) {
        showToast('Failed to save API key', true);
      }
    });
  }

  // Auto-save listeners on change
  [
    [speakRepliesToggle, 'voice_reply', (el) => el.checked],
    [roamingToggle, 'roaming', (el) => el.checked],
    [reduceMotionToggle, 'reduced_motion', (el) => el.checked],
    [wakeWordToggle, 'wake_word_enabled', (el) => el.checked],
    [wakeWordInput, 'wake_word', (el) => el.value],
    [pushToTalkSel, 'push_to_talk_shortcut', (el) => el.value],
    [voiceNameSel, 'voice_name', (el) => el.value],
    [voiceStyleInput, 'voice_style', (el) => el.value],
    [mascotPoseSel, 'mascot_pose', (el) => el.value],
    [mascotCornerSel, 'mascot_corner', (el) => el.value],
    [retentionDaysSel, 'retention_days', (el) => parseInt(el.value, 10)],
    [retentionMbSel, 'retention_max_mb', (el) => parseInt(el.value, 10)],
  ].forEach(([el, key, getter]) => {
    if (!el) return;
    el.addEventListener('change', () => {
      const update = {};
      update[key] = getter(el);
      saveBrainSettings(update);
    });
  });

  if (activeProfileSel) {
    activeProfileSel.addEventListener('change', async () => {
      try {
        const res = await fetch('/api/brain/activate-profile', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ profile_id: activeProfileSel.value }),
        });
        const data = await res.json();
        if (data.success) {
          showToast(`Active profile set to: ${data.active.name}`);
          loadBrainStatus();
        }
      } catch (err) {
        showToast('Failed to switch profile', true);
      }
    });
  }

  async function loadBrainStatus() {
    try {
      const res = await fetch('/api/brain/status');
      const data = await res.json();
      if (!data) return;

      if (agentStatusBadge) {
        agentStatusBadge.textContent = data.is_mini_agent_visible
          ? `Mini Agent Active (${data.activity})`
          : 'Mini Agent Docked';
        agentStatusBadge.style.background = data.is_mini_agent_visible ? 'rgba(16, 185, 129, 0.2)' : 'rgba(255, 255, 255, 0.08)';
        agentStatusBadge.style.color = data.is_mini_agent_visible ? '#34d399' : '#94a3b8';
      }

      const s = data.settings || {};
      if (speakRepliesToggle) speakRepliesToggle.checked = s.voice_reply !== false;
      if (roamingToggle) roamingToggle.checked = !!s.roaming;
      if (reduceMotionToggle) reduceMotionToggle.checked = !!s.reduced_motion;
      if (wakeWordToggle) wakeWordToggle.checked = s.wake_word_enabled !== false;
      if (wakeWordInput && s.wake_word) wakeWordInput.value = s.wake_word;
      if (pushToTalkSel && s.push_to_talk_shortcut) pushToTalkSel.value = s.push_to_talk_shortcut;
      if (voiceNameSel && s.voice_name) voiceNameSel.value = s.voice_name;
      if (voiceStyleInput && s.voice_style) voiceStyleInput.value = s.voice_style;
      if (mascotPoseSel && s.mascot_pose) mascotPoseSel.value = s.mascot_pose;
      if (mascotCornerSel && s.mascot_corner) mascotCornerSel.value = s.mascot_corner;
      if (retentionDaysSel && s.retention_days !== undefined) retentionDaysSel.value = String(s.retention_days);
      if (retentionMbSel && s.retention_max_mb !== undefined) retentionMbSel.value = String(s.retention_max_mb);

      if (speechRateSlider && s.speech_rate) {
        speechRateSlider.value = Math.round(s.speech_rate * 100);
        if (speechRateVal) speechRateVal.textContent = `${s.speech_rate.toFixed(1)}x`;
      }

      // Populate Profiles
      if (activeProfileSel && data.profiles) {
        activeProfileSel.innerHTML = '';
        data.profiles.forEach((p) => {
          const opt = document.createElement('option');
          opt.value = p.id;
          const status = (p.status || 'active').toLowerCase();
          const displayStatus = status === 'not configured' ? 'Not Configured' : (status === 'offline' ? 'Offline' : 'Active');
          opt.textContent = `${p.name} (${displayStatus})`;
          opt.dataset.status = status;
          if (data.active_profile && p.id === data.active_profile.id) opt.selected = true;
          activeProfileSel.appendChild(opt);
        });
        if (activeProfileSel._refreshCustomDropdown) {
          activeProfileSel._refreshCustomDropdown();
        }
      }

      // Populate Active Profile fields
      const ap = data.active_profile || {};
      if (providerSel && ap.provider) providerSel.value = ap.provider;
      if (modelIdInput && ap.model) modelIdInput.value = ap.model;
      if (baseUrlInput) baseUrlInput.value = ap.base_url || '';
      if (localOnlyToggle) localOnlyToggle.checked = !!ap.local_only;

      // Refresh any initialized dropdowns with new values
      document.querySelectorAll('select.select-input').forEach((sel) => {
        if (sel._refreshCustomDropdown) sel._refreshCustomDropdown();
      });
    } catch (err) {
      console.warn('Could not load brain status:', err);
    }
  }

  async function saveBrainSettings(settingsObj) {
    try {
      const res = await fetch('/api/brain/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settingsObj),
      });
      const data = await res.json();
      if (data.success) {
        showToast('Brain setting updated');
      }
    } catch (err) {
      showToast('Error updating Brain setting', true);
    }
  }

  await loadBrainStatus();
  initSearchableDropdowns();
}

// Universal Custom Searchable Dropdown for all select.select-input elements
function initSearchableDropdowns() {
  document.querySelectorAll('select.select-input').forEach((select) => {
    if (select._hasCustomDropdown) {
      if (select._refreshCustomDropdown) select._refreshCustomDropdown();
      return;
    }
    select._hasCustomDropdown = true;

    // Hide native select visually
    select.style.display = 'none';

    const wrapper = document.createElement('div');
    wrapper.className = 'custom-dropdown-container';

    const trigger = document.createElement('button');
    trigger.type = 'button';
    trigger.className = 'custom-dropdown-trigger';

    const triggerText = document.createElement('span');
    triggerText.className = 'custom-dropdown-value';

    const chevron = document.createElement('span');
    chevron.className = 'custom-dropdown-arrow';
    chevron.innerHTML = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M6 9l6 6 6-6"/></svg>';

    trigger.appendChild(triggerText);
    trigger.appendChild(chevron);
    wrapper.appendChild(trigger);

    const menu = document.createElement('div');
    menu.className = 'custom-dropdown-menu';
    menu.style.display = 'none';

    // Search input
    const searchBox = document.createElement('input');
    searchBox.type = 'text';
    searchBox.className = 'custom-dropdown-search';
    searchBox.placeholder = 'Search…';
    searchBox.autocomplete = 'off';

    const searchWrapper = document.createElement('div');
    searchWrapper.className = 'custom-dropdown-search-wrapper';
    searchWrapper.appendChild(searchBox);
    menu.appendChild(searchWrapper);

    const list = document.createElement('div');
    list.className = 'custom-dropdown-list';
    menu.appendChild(list);

    wrapper.appendChild(menu);
    select.parentNode.insertBefore(wrapper, select.nextSibling);

    function updateOptions() {
      list.innerHTML = '';
      const query = searchBox.value.toLowerCase().trim();
      let hasMatch = false;

      Array.from(select.options).forEach((opt) => {
        const text = opt.textContent;
        const val = opt.value;
        const matches = text.toLowerCase().includes(query);
        if (!matches && query) return;

        hasMatch = true;
        const item = document.createElement('div');
        item.className = 'custom-dropdown-item' + (opt.selected ? ' selected' : '');
        item.dataset.value = val;

        const labelSpan = document.createElement('span');
        labelSpan.className = 'item-label';
        labelSpan.textContent = text;
        item.appendChild(labelSpan);

        if (opt.selected) {
          const check = document.createElement('span');
          check.className = 'item-check';
          check.innerHTML = '✓';
          item.appendChild(check);
        }

        item.addEventListener('click', () => {
          select.value = val;
          select.dispatchEvent(new Event('change', { bubbles: true }));
          syncTrigger();
          closeMenu();
        });

        list.appendChild(item);
      });

      if (!hasMatch) {
        const empty = document.createElement('div');
        empty.className = 'custom-dropdown-empty';
        empty.textContent = 'No matching options';
        list.appendChild(empty);
      }
    }

    function syncTrigger() {
      const selected = select.options[select.selectedIndex];
      triggerText.textContent = selected ? selected.textContent : 'Select…';
      updateOptions();
    }

    function openMenu() {
      document.querySelectorAll('.custom-dropdown-menu').forEach((m) => {
        if (m !== menu) m.style.display = 'none';
      });
      document.querySelectorAll('.custom-dropdown-container').forEach((c) => {
        if (c !== wrapper) c.classList.remove('open', 'drop-up');
      });

      // Flip upward if close to viewport bottom
      const rect = wrapper.getBoundingClientRect();
      const spaceBelow = window.innerHeight - rect.bottom;
      if (spaceBelow < 260 && rect.top > 260) {
        wrapper.classList.add('drop-up');
      } else {
        wrapper.classList.remove('drop-up');
      }

      menu.style.display = 'flex';
      wrapper.classList.add('open');
      searchBox.value = '';
      updateOptions();
      searchBox.focus();
    }

    function closeMenu() {
      menu.style.display = 'none';
      wrapper.classList.remove('open', 'drop-up');
    }

    trigger.addEventListener('click', (e) => {
      e.stopPropagation();
      if (menu.style.display === 'flex') {
        closeMenu();
      } else {
        openMenu();
      }
    });

    searchBox.addEventListener('input', () => {
      updateOptions();
    });

    searchBox.addEventListener('keydown', (e) => {
      const items = Array.from(list.querySelectorAll('.custom-dropdown-item'));
      const activeItem = list.querySelector('.custom-dropdown-item.keyboard-focus');
      let idx = items.indexOf(activeItem);

      if (e.key === 'ArrowDown') {
        e.preventDefault();
        if (items.length > 0) {
          if (activeItem) activeItem.classList.remove('keyboard-focus');
          idx = (idx + 1) % items.length;
          items[idx].classList.add('keyboard-focus');
          items[idx].scrollIntoView({ block: 'nearest' });
        }
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        if (items.length > 0) {
          if (activeItem) activeItem.classList.remove('keyboard-focus');
          idx = idx <= 0 ? items.length - 1 : idx - 1;
          items[idx].classList.add('keyboard-focus');
          items[idx].scrollIntoView({ block: 'nearest' });
        }
      } else if (e.key === 'Escape') {
        closeMenu();
        trigger.focus();
      } else if (e.key === 'Enter') {
        e.preventDefault();
        if (activeItem) {
          activeItem.click();
        } else if (items.length > 0) {
          items[0].click();
        }
      }
    });

    select._refreshCustomDropdown = syncTrigger;
    syncTrigger();
  });

  document.addEventListener('click', (e) => {
    if (!e.target.closest('.custom-dropdown-container')) {
      document.querySelectorAll('.custom-dropdown-menu').forEach((m) => {
        m.style.display = 'none';
      });
      document.querySelectorAll('.custom-dropdown-container').forEach((w) => {
        w.classList.remove('open');
      });
    }
  });
}

// Initial boot
document.addEventListener('DOMContentLoaded', () => {
  initSearchableDropdowns();
});

