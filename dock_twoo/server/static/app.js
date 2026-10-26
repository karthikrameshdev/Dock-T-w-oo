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
    await loadDisplays();
    updatePreview(data);
  } catch (err) {
    console.error('Failed to load config:', err);
    showToast('Failed to connect to Dock T(w)oo', true);
  }
}

// Populate UI Elements from Config
function initForm(cfg) {
  document.getElementById("startOnBoot").checked = cfg.start_on_boot === true;
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
  if (brainWakeWord) brainWakeWord.value = 'Use each character’s name · Brain, Rio, Luma…';
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
      headers: { 'Content-Type': 'application/json', 'X-Brain-Request': 'local' },
      body: JSON.stringify(currentConfig),
    });
    const data = await res.json();
    if (data.success) {
      showToast('Settings saved & applied to Dock');
    } else {
      showToast(data.error || 'Could not save settings', true);
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
initStorageConsole();

// Global Storage & Data Management Console Module
async function initStorageConsole() {
  const globalStoragePath = document.getElementById('globalStoragePath');
  const browseStorageBtn = document.getElementById('browseStorageBtn');
  const applyStorageBtn = document.getElementById('applyStorageBtn');
  const refreshStorageBtn = document.getElementById('refreshStorageBtn');
  const storageStatusHint = document.getElementById('storageStatusHint');

  const storageNotesPath = document.getElementById('storageNotesPath');
  const storageNotesCount = document.getElementById('storageNotesCount');
  const storageNotesSize = document.getElementById('storageNotesSize');

  const storageVaultPath = document.getElementById('storageVaultPath');
  const storageVaultCount = document.getElementById('storageVaultCount');
  const storageVaultSize = document.getElementById('storageVaultSize');

  const storageModelsPath = document.getElementById('storageModelsPath');
  const storageModelsCount = document.getElementById('storageModelsCount');
  const storageModelsSize = document.getElementById('storageModelsSize');

  const storageBrainPath = document.getElementById('storageBrainPath');
  const storageBrainCount = document.getElementById('storageBrainCount');
  const storageBrainSize = document.getElementById('storageBrainSize');

  async function loadStorageData() {
    try {
      const res = await fetch('/api/storage');
      const data = await res.json();
      if (!data) return;

      if (globalStoragePath) globalStoragePath.value = data.storage_path || '~/.dock2';

      const subs = data.subsystems || {};
      if (subs.notes) {
        if (storageNotesPath) storageNotesPath.textContent = subs.notes.path;
        if (storageNotesCount) storageNotesCount.textContent = `${subs.notes.file_count} files`;
        if (storageNotesSize) storageNotesSize.textContent = `${subs.notes.size_mb} MB`;
      }
      if (subs.vault) {
        if (storageVaultPath) storageVaultPath.textContent = subs.vault.path;
        if (storageVaultCount) storageVaultCount.textContent = `${subs.vault.file_count} files`;
        if (storageVaultSize) storageVaultSize.textContent = `${subs.vault.size_mb} MB`;
      }
      if (subs.models) {
        if (storageModelsPath) storageModelsPath.textContent = subs.models.path;
        if (storageModelsCount) storageModelsCount.textContent = `${subs.models.file_count} files`;
        if (storageModelsSize) storageModelsSize.textContent = `${subs.models.size_mb} MB`;
      }
      if (subs.voice) {
        const voiceVault=document.getElementById("voiceVaultLocation");if(voiceVault)voiceVault.textContent=subs.voice.path;
        if (storageBrainPath) storageBrainPath.textContent = subs.voice.path;
        if (storageBrainCount) storageBrainCount.textContent = `${subs.voice.file_count} files`;
        if (storageBrainSize) storageBrainSize.textContent = `${subs.voice.size_mb} MB`;
      }
    } catch (err) {
      console.warn('Could not load storage data:', err);
    }
  }

  if (browseStorageBtn) {
    browseStorageBtn.addEventListener('click', async () => {
      try {
        showToast('Opening native folder picker…');
        const res = await fetch('/api/storage/browse', { method: 'POST' });
        const data = await res.json();
        if (data.success && data.path) {
          if (globalStoragePath) globalStoragePath.value = data.path;
          showToast(`Selected folder: ${data.path}`);
        } else if (!data.cancelled) {
          showToast('Folder browse cancelled', true);
        }
      } catch (err) {
        showToast('Failed to open folder picker', true);
      }
    });
  }

  if (applyStorageBtn) {
    applyStorageBtn.addEventListener('click', async () => {
      const targetPath = globalStoragePath ? globalStoragePath.value.trim() : '';
      if (!targetPath) {
        showToast('Please enter or select a root storage path', true);
        return;
      }
      try {
        showToast('Migrating all data to new storage path…');
        const res = await fetch('/api/storage/change', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ new_path: targetPath }),
        });
        const data = await res.json();
        if (data.success) {
          showToast(`Migrated all data to: ${data.storage_path}`);
          if (storageStatusHint) {
            storageStatusHint.textContent = `Root storage active at ${data.storage_path} (${data.migration?.file_count || 0} files migrated)`;
          }
          await loadStorageData();
        } else {
          showToast(`Storage change failed: ${data.error || 'Unknown error'}`, true);
        }
      } catch (err) {
        showToast('Failed to change storage path', true);
      }
    });
  }

  if (refreshStorageBtn) {
    refreshStorageBtn.addEventListener('click', async () => {
      await loadStorageData();
      showToast('Storage statistics refreshed');
    });
  }

  await loadStorageData();
}

// Agent model profiles, shared local voice and persistent desktop controls
async function initBrainConsole() {
  const byId = id => document.getElementById(id);
  window.BrainUsage?.mount(document.getElementById('cloudUsageDashboard'));
  window.BrainActivity?.mount(document.getElementById('brainActivityTracker'));
  const headers = {'Content-Type':'application/json','X-Brain-Request':'local'};
  let generation=0, presets={}, catalog={};
  const post = async (path,body={}) => {
    const response=await fetch(path,{method:'POST',headers,body:JSON.stringify(body)});
    const data=await response.json();
    if (!response.ok || data.success===false) throw new Error(data.error || 'The request failed.');
    return data;
  };
  const report = error => showToast(error.message,true);
  document.querySelectorAll('.brain-tab-btn').forEach(button => button.addEventListener('click',()=>{
    document.querySelectorAll('.brain-tab-btn,.brain-tab-panel').forEach(el=>el.classList.remove('active'));
    button.classList.add('active');byId(button.dataset.tab)?.classList.add('active');
  }));
  let cloudProfiles=[],editingProfileId=null,newCloudProfile=false,activeCloudProfileId='';
  function agentModelFields() {
    const provider=byId('brainCloudProvider').value,cli=provider.endsWith('_cli');
    byId('agentCliFields').hidden=!cli;
    byId('brainCloudUrl').required=!cli;byId('brainCloudUrl').closest('.form-group').hidden=cli;
    byId('brainCloudProtocol').disabled=cli;
    byId('agentCliArguments').closest('.form-group').hidden=provider!=='custom_cli';
    if(cli&&!byId('agentCliExecutable').value)byId('agentCliExecutable').value={gemini_cli:'gemini',codex_cli:'codex',claude_cli:'claude',kilo_cli:'kilo'}[provider]||'';
  }
  function fillCloudProfile(config={}) {
    byId('brainCloudName').value=config.name||'';
    byId('brainCloudProvider').value=config.provider||'gemini';
    byId('brainCloudProtocol').value=config.protocol||'openai';
    byId('brainCloudUrl').value=config.base_url||presets[config.provider||'gemini']||'';
    byId('agentCliExecutable').value=config.executable||'';byId('agentCliArguments').value=JSON.stringify(config.arguments||[]);byId('agentCacheMode').value=config.cache_mode||'auto';
    agentModelFields();
    byId('brainCloudModel').value=config.model||'';byId('brainCloudKey').value='';
    byId('brainCloudActivate').disabled=!config.id||config.id===activeCloudProfileId;
    byId('brainCloudDelete').disabled=!config.id;
    byId('brainCloudTest').disabled=!config.id||config.status!=='configured';
    byId('brainCloudStatus').textContent=!config.id?'Enter a name, model and key, then save the new profile.':config.status==='not configured'?'Model is not configured. Enter a model ID and API key.':`${config.name} · ${config.model} · ${config.kind==='cli'?'Installed CLI':config.kind==='network'?'Network endpoint':'Key saved'}`;
    initSearchableDropdowns();
  }
  async function modelForm(preferred=editingProfileId) {
    const data=await (await fetch('/api/brain/model')).json();
    presets=data.presets;catalog=data.catalog;cloudProfiles=data.profiles||[data.model];activeCloudProfileId=data.model.id||'';
    const select=byId('brainCloudProfile');select.replaceChildren();
    for(const profile of cloudProfiles)select.add(new Option(profile.name+(profile.id===activeCloudProfileId?' · Active':''),profile.id));
    const config=cloudProfiles.find(p=>p.id===preferred)||cloudProfiles.find(p=>p.id===activeCloudProfileId);
    editingProfileId=config?.id||null;newCloudProfile=!config;
    if(!config)select.add(new Option('New profile','__new__'));
    select.value=editingProfileId||'__new__';
    byId('brainCloudActive').textContent=activeCloudProfileId?`Active: ${data.model.name}. Running requests retain their original profile.`:'Model is not configured. Create a profile to get started.';
    fillCloudProfile(config);
  }
  byId('brainCloudProfile').addEventListener('change',()=>{
    editingProfileId=byId('brainCloudProfile').value;newCloudProfile=false;
    fillCloudProfile(cloudProfiles.find(p=>p.id===editingProfileId));
  });
  byId('brainCloudNew').addEventListener('click',()=>{
    editingProfileId=null;newCloudProfile=true;
    const select=byId('brainCloudProfile');if(!select.querySelector('option[value="__new__"]'))select.add(new Option('New profile','__new__'));
    select.value='__new__';fillCloudProfile();byId('brainCloudName').focus();
  });
  byId('brainCloudActivate').addEventListener('click',async()=>{
    try{await post('/api/brain/activate-profile',{profile_id:editingProfileId});await modelForm();showToast('Default agent model switched.');}catch(error){report(error);}
  });
  byId('brainCloudDelete').addEventListener('click',async()=>{
    if(!editingProfileId)return;
    if(!confirm('Delete this saved profile and its credential? Usage history will remain.'))return;
    try{await post('/api/brain/profile/delete',{profile_id:editingProfileId});editingProfileId=null;await modelForm();showToast('Profile deleted; usage history retained.');}catch(error){report(error);}
  });
  byId('brainCloudProvider').addEventListener('change',()=>{
    const provider=byId('brainCloudProvider').value;
    byId('brainCloudUrl').value=presets[provider]||'';
    byId('brainCloudProtocol').value=provider==='anthropic'?'anthropic':'openai';byId('brainCloudKey').value='';byId('agentCliExecutable').value='';agentModelFields();initSearchableDropdowns();
  });
  byId('brainCloudForm').addEventListener('input',()=>{byId('brainCloudTest').disabled=true;});
  byId('brainCloudForm').addEventListener('submit',async event=>{
    event.preventDefault();
    try {
      const result=await post(newCloudProfile?'/api/brain/profiles':'/api/brain/profile',{...(editingProfileId?{id:editingProfileId}:{}),name:byId('brainCloudName').value.trim(),provider:byId('brainCloudProvider').value,protocol:byId('brainCloudProtocol').value,base_url:byId('brainCloudUrl').value.trim(),model:byId('brainCloudModel').value.trim(),api_key:byId('brainCloudKey').value.trim(),executable:byId('agentCliExecutable').value.trim(),arguments:JSON.parse(byId('agentCliArguments').value||'[]'),cache_mode:byId('agentCacheMode').value});
      editingProfileId=result.profile.id;byId('brainCloudKey').value='';await modelForm();showToast('Agent model profile saved.');
    } catch(error){report(error);}
  });
  byId('brainCloudTest').addEventListener('click',async()=>{
    const button=byId('brainCloudTest');button.disabled=true;byId('brainCloudStatus').textContent='Testing the saved profile…';
    try {const result=await post('/api/brain/model/test',{profile_id:editingProfileId});byId('brainCloudStatus').textContent=result.message;}catch(error){byId('brainCloudStatus').textContent=error.message;}finally{button.disabled=false;}
  });
  byId('brainRequestForm').addEventListener('submit',async event=>{
    event.preventDefault();const text=byId('brainRequestText').value.trim();if(!text)return;
    try{await post('/api/brain/request',{text});byId('brainRequestStatus').textContent='Brain is working on your request…';}catch(error){report(error);}
  });
  byId('brainStopAgent').addEventListener('click',()=>post('/api/brain/stop').catch(report));
  for (const [id,action] of [['brainSummonBtn','summon'],['brainHideBtn','hide'],['brainTalkBtn','talk'],['brainLoopAnimBtn','animation']]) {
    byId(id)?.addEventListener('click',()=>post('/api/brain/action',{action,name:'loop'}).catch(report));
  }
  document.querySelectorAll('[data-reader]').forEach(button=>button.addEventListener('click',async()=>{
    try{const response=await fetch('/api/brain/action',{method:'POST',headers:{...headers,'X-Brain-Reader':'local'},body:JSON.stringify({action:button.dataset.reader})});const data=await response.json();if(!response.ok)throw new Error(data.error);}catch(error){report(error);}
  }));
  document.querySelectorAll('[data-anim]').forEach(button=>button.addEventListener('click',()=>post('/api/brain/action',{action:'animation',name:button.dataset.anim}).catch(report)));
  const release=await (await fetch('/brain3d/character.json')).json();
  const select=byId('brainCharacterAction');if(select) for(const action of Object.keys(release.actions))if(action!=='idle')select.add(new Option(action.replaceAll('_',' '),action));
  if(byId('brainCharacterRelease'))byId('brainCharacterRelease').textContent=`Brain ${release.version} · ${release.design} · ${Object.keys(release.actions).length} animations`;
  byId('brainCharacterPlay')?.addEventListener('click',()=>post('/api/brain/action',{action:'animation',name:select.value}).catch(report));
  async function save(settings){try{await post('/api/brain/settings',settings);}catch(error){report(error);}}
  for(const [id,key] of [['brainWakeWordToggle','wake_word_enabled'],['brainSpeakRepliesToggle','voice_reply'],['brainRoamingToggle','roaming'],['brainFollowCursorToggle','follow_cursor'],['brainReduceMotionToggle','reduced_motion']])byId(id)?.addEventListener('change',event=>save({[key]:event.target.checked}));
  for(const [id,key] of [['brainOwnerName','owner_first_name'],['brainPushToTalkKey','push_to_talk_shortcut'],['brainVoiceName','voice_name']])byId(id)?.addEventListener('change',event=>save({[key]:event.target.value}));
  byId('brainSpeechRate')?.addEventListener('input',event=>{const speed=Number(event.target.value)/100;byId('brainSpeechRateVal').textContent=speed.toFixed(1)+'x';save({speech_rate:speed});});
  byId('brainVoiceCheckBtn')?.addEventListener('click',()=>fetch('/api/brain/voice-check',{method:'POST',headers:{'X-Brain-Voice-Check':'local'}}).catch(report));
  byId('brainEnrollVoiceBtn')?.addEventListener('click',()=>post('/api/brain/enroll-owner').catch(report));
  byId('keepAwakeBtn')?.addEventListener('click',async()=>{
    try{const result=await post('/api/keep-awake',{enabled:byId('keepAwakeBtn').getAttribute('aria-pressed')!=='true'});awake(result);}catch(error){report(error);}
  });
  function awake(value){const button=byId('keepAwakeBtn');if(button){button.setAttribute('aria-pressed',String(value.enabled));button.textContent='Keep Awake · '+(value.enabled?'On':'Off');}}
  async function refresh(){
    try{
      const data=await (await fetch('/api/brain/status',{headers:{'X-Brain-Request':'local'}})).json();
      const input=data.voice_input||{},diag=input.wake_diagnostics||{},model=data.language_model||{};
      byId('brainAgentStatusBadge').textContent=`Voice Assistant ${data.character?.version||''} · ${data.activity||'idle'}`;
      byId('brainTalkBtn').textContent=diag.recording?'✓ Finish speaking':(diag.decoding?'Processing speech…':'🎤 Talk to Brain');
      byId('brainTalkBtn').disabled=Boolean(diag.decoding);
      const devices=diag.audio_devices||{};
      byId('brainVoiceInputStatus').textContent=(model.state==='not configured'?'Model is not configured. Set it up in Cloud Model.':`Agent model profile: ${data.active_profile?.name || model.name || "Default"} · ${model.model}.`)+` System defaults · Microphone: ${devices.input||diag.input_device||'unavailable'} · Speaker: ${devices.output||'unavailable'}.`;
      byId('brainWakeDiagnostics').textContent=`Wake ${input.wake_ready?'ready':'preparing'} · ${diag.recognizer_engine||'local speech'} · ${input.recognizer_ready?'ready':'preparing'} · ${diag.last_decision||''}`;
      byId('brainLocalSpeechStatus').textContent=`Local speech: ${data.local_speech?.engine||'Kokoro ONNX'} · ${data.local_speech?.state||'preparing'}${data.local_speech?.error?' · '+data.local_speech.error:''}`;
      byId('brainAgentProgress').textContent=(data.agent?.message && data.agent?.step>0?`Step ${data.agent.step||0} · ${data.agent.message}`:'')+(data.queue?.pending?.length?` · ${data.queue.pending.length} request${data.queue.pending.length===1?'':'s'} queued`:'');
      if(data.last_response?.generation>generation){byId('brainRequestStatus').textContent=data.last_response.text;generation=data.last_response.generation;}
      const check=diag.voice_check||{};
      if(check.active || check.heard?.length)byId('brainVoiceCheckStatus').textContent=`${check.active?'Listening '+check.seconds_remaining+'s':'Check finished'} · ${(check.heard||[]).map(entry=>entry.heard).join(' · ')}`;
      const settings=data.settings||{};
      for(const [id,key] of [['brainWakeWordToggle','wake_word_enabled'],['brainSpeakRepliesToggle','voice_reply'],['brainRoamingToggle','roaming'],['brainFollowCursorToggle','follow_cursor'],['brainReduceMotionToggle','reduced_motion']])if(byId(id))byId(id).checked=!!settings[key];
      for(const [id,key] of [['brainOwnerName','owner_first_name'],['brainPushToTalkKey','push_to_talk_shortcut']])if(byId(id)&&document.activeElement!==byId(id))byId(id).value=settings[key]||'';
      if(document.activeElement!==byId('brainSpeechRate')){byId('brainSpeechRate').value=Math.round((settings.speech_rate||1)*100);byId('brainSpeechRateVal').textContent=(settings.speech_rate||1).toFixed(1)+'x';}
      if(byId('brainReadingStatus'))byId('brainReadingStatus').textContent=data.reading?.error|| (data.reading?.active?`Reading ${data.reading.window||'text'} · page ${data.reading.pages_read||1}`:'Choose an existing selection or a document window to read.');
      if(document.activeElement!==byId('brainVoiceName'))byId('brainVoiceName').value=settings.voice_name in {af_heart:1,af_bella:1,am_adam:1,am_michael:1,bf_emma:1,bm_george:1}?settings.voice_name:'af_heart';
      initSearchableDropdowns();
      awake(await (await fetch('/api/keep-awake')).json());
    }catch(error){console.warn('Brain status:',error.message);}
  }
  const dateInput=byId('tasksDay');
  dateInput.value=new Date(Date.now()-new Date().getTimezoneOffset()*60000).toISOString().slice(0,10);
  async function tasks() {
    try {
      const data=await (await fetch('/api/tasks'+(dateInput.value?'?date='+dateInput.value:''))).json();
      if(data.error)throw new Error(data.error);
      const list=byId('tasksList');list.replaceChildren();let previous='';
      for(const task of data.tasks){
        if(task.day!==previous){const heading=document.createElement('h3');heading.textContent=task.day;list.append(heading);previous=task.day;}
        const row=document.createElement('div');row.className='toggle-card-item';
        const title=document.createElement('span');title.textContent=task.title;row.append(title);
        const toggle=document.createElement('button');toggle.className='btn btn-secondary';toggle.textContent=task.status==='done'?'Done':'Mark done';
        toggle.addEventListener('click',async()=>{try{await post('/api/tasks',{id:task.id,status:task.status==='done'?'todo':'done'});await tasks();}catch(error){report(error);}});
        row.append(toggle);list.append(row);
      }
      byId('tasksStatus').textContent=data.tasks.length?`${data.tasks.length} entries${data.next_offset?' · Choose a date to see more':''}`:'No work entries for this date yet.';
    }catch(error){byId('tasksStatus').textContent=error.message;}
  }
  dateInput.addEventListener('change',tasks);byId('tasksAllDays').addEventListener('click',()=>{dateInput.value='';tasks();});
  byId('tasksForm').addEventListener('submit',async event=>{
    event.preventDefault();try{await post('/api/tasks',{title:byId('tasksTitle').value.trim(),date:dateInput.value||undefined,status:'done'});byId('tasksTitle').value='';await tasks();}catch(error){report(error);}
  });
  await tasks();setInterval(()=>{if(byId('page-tasks').classList.contains('active'))tasks();},2500);
  await modelForm();await refresh();setInterval(refresh,1500);initSearchableDropdowns();
}


// Display inventory is supplied by Qt on the GUI thread; never infer monitors
// from browser screen dimensions (the console may be on a different display).
let connectedDisplays=[],displayRenderSignature='';
async function loadDisplays() {
  const response=await fetch('/api/displays',{headers:{'X-Brain-Request':'local'}});
  if(!response.ok)throw new Error('Could not load displays');
  const data=await response.json();connectedDisplays=data.displays || [];
  const mode=document.getElementById('displayMode');
  mode.value=currentConfig.display_mode || 'single';
  if(!currentConfig.display_ids?.length && connectedDisplays.length) {
    currentConfig.display_ids=connectedDisplays.filter(d=>d.selected).map(d=>d.id);
  }
  renderDisplayChoices(data.fallback);
}
function renderDisplayChoices(fallback=false) {
  const list=document.getElementById('displayChecklist'),mode=document.getElementById('displayMode').value;
  const signature=JSON.stringify([mode,currentConfig.display_ids,connectedDisplays,fallback]);
  if(signature===displayRenderSignature)return;
  displayRenderSignature=signature;
  list.replaceChildren();
  connectedDisplays.forEach(display=>{
    const label=document.createElement('label');label.className='display-choice';
    Object.assign(label.style,{display:'flex',alignItems:'center',gap:'12px',padding:'12px 16px',border:'1px solid var(--border-color, #505057)',borderRadius:'10px',cursor:mode==='all'?'default':'pointer'});
    const input=document.createElement('input');input.type=mode==='single'?'radio':'checkbox';input.name='dock-display';input.value=display.id;
    input.checked=mode==='all' || currentConfig.display_ids.includes(display.id);input.disabled=mode==='all';
    input.style.width='18px';input.style.height='18px';input.style.flex='0 0 18px';
    const title=document.createElement('span');title.textContent=`Screen ${display.number} · ${display.name}${display.primary?' · Primary':''} · ${display.geometry[2]} × ${display.geometry[3]}`;
    label.append(input,title);list.append(label);
    input.addEventListener('change',()=>{
      const ids=Array.from(list.querySelectorAll('input:checked')).map(field=>field.value);
      if(!ids.length){input.checked=true;showToast('Keep at least one screen selected',true);return;}
      currentConfig.display_ids=ids;autoSave();
    });
  });
  // Retain disconnected choices so plugging them in restores the saved layout.
  const disconnected=(currentConfig.display_ids || []).filter(id=>!connectedDisplays.some(d=>d.id===id));
  const note=document.getElementById('displayStatus');
  note.textContent=fallback?'Saved screens are disconnected. Dock is temporarily on the primary screen.':`${connectedDisplays.length} connected display${connectedDisplays.length===1?'':'s'}.`;
  if(disconnected.length)note.textContent+=` ${disconnected.length} disconnected selection${disconnected.length===1?' is':'s are'} retained.`;
  window.ConsoleControls?.enhance?.();
}
document.getElementById('displayMode')?.addEventListener('change',event=>{
  currentConfig.display_mode=event.target.value;
  if(event.target.value==='single')currentConfig.display_ids=(currentConfig.display_ids || []).slice(0,1);
  if(!currentConfig.display_ids?.length && connectedDisplays.length)currentConfig.display_ids=[connectedDisplays.find(d=>d.primary)?.id || connectedDisplays[0].id];
  renderDisplayChoices();autoSave();
});
// Hot-plug updates the checklist while preserving unsaved in-flight edits.
setInterval(()=>{if(document.visibilityState==='visible' && currentConfig && document.getElementById('page-placement')?.classList.contains('active'))loadDisplays().catch(()=>{});},5000);

// Preview is deliberately per-tab and off on every console open.
document.getElementById('startOnBoot').addEventListener('change', async event => {
  const previous=currentConfig.start_on_boot;
  try {
    const response=await fetch('/api/config',{method:'POST',headers:{'Content-Type':'application/json','X-Brain-Request':'local'},body:JSON.stringify({start_on_boot:event.target.checked})});
    const data=await response.json();if(!response.ok || !data.success)throw new Error(data.error||'Startup setting could not be applied');
    currentConfig.start_on_boot=event.target.checked;showToast('Startup setting saved');
  } catch(error){event.target.checked=previous===true;showToast(error.message,true);}
});
