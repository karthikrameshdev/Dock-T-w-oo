import os

icons = {
    "logo": '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" fill="none">
  <defs>
    <linearGradient id="gD2" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#00F5FF" />
      <stop offset="60%" stop-color="#0072FF" />
      <stop offset="100%" stop-color="#7000FF" />
    </linearGradient>
    <linearGradient id="gTwo2" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#A100FF" />
      <stop offset="50%" stop-color="#E000B0" />
      <stop offset="100%" stop-color="#FF006E" />
    </linearGradient>
  </defs>
  <!-- "2" Layer (Behind) -->
  <path d="M15 12.5 C15 9.2 17.5 7 21 7 C24.5 7 27.2 9.5 27.2 13 C27.2 16.8 23.6 20.2 18.2 24.2 L15 26.6 H27.5" 
        stroke="url(#gTwo2)" stroke-width="3.6" stroke-linecap="round" stroke-linejoin="round" opacity="0.95" />
  <!-- "D" Layer (Foreground) with translucent glass fill -->
  <path d="M5 5 H12.5 C17.8 5 21.8 8.8 21.8 14 C21.8 19.2 17.8 23 12.5 23 H5 V5 Z" 
        stroke="url(#gD2)" stroke-width="3.8" stroke-linecap="round" stroke-linejoin="round" fill="rgba(0, 245, 255, 0.08)" />
</svg>''',

    "apps": '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <rect x="3" y="3" width="7" height="7" rx="2" />
  <rect x="14" y="3" width="7" height="7" rx="2" />
  <rect x="14" y="14" width="7" height="7" rx="2" />
  <rect x="3" y="14" width="7" height="7" rx="2" />
</svg>''',

    "calendar": '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
  <rect x="3" y="4" width="18" height="18" rx="3" />
  <line x1="16" y1="2" x2="16" y2="5" />
  <line x1="8" y1="2" x2="8" y2="5" />
  <line x1="3" y1="9" x2="21" y2="9" />
  <text x="12" y="17.5" font-size="7.5" font-family="-apple-system, system-ui, sans-serif" font-weight="bold" fill="currentColor" stroke="none" text-anchor="middle">12</text>
</svg>''',

    "star": '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
  <path d="M19 21l-7-4-7 4V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" />
  <polygon points="12 7 13.1 9.6 16 9.8 13.8 11.6 14.5 14.5 12 13 9.5 14.5 10.2 11.6 8 9.8 10.9 9.6 12 7" fill="currentColor" stroke="none" />
</svg>''',

    "weather": '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
  <path d="M17.5 19H9a7 7 0 1 1 6.71-9h1.79a4.5 4.5 0 1 1 0 9Z" />
  <polyline points="13 11 11 15 14 15 12 19" fill="currentColor" stroke="currentColor" stroke-width="1.2" />
</svg>''',

    "vault": '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
  <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
  <path d="M7 11V7a5 5 0 0 1 10 0v4" />
  <circle cx="12" cy="16.5" r="1.5" fill="currentColor" stroke="none" />
  <line x1="12" y1="18" x2="12" y2="20" stroke-width="2" />
</svg>''',

    "notes": '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
  <polyline points="14 2 14 8 20 8" />
  <line x1="16" y1="13" x2="8" y2="13" />
  <line x1="16" y1="17" x2="8" y2="17" />
  <line x1="10" y1="9" x2="8" y2="9" />
</svg>''',

    "checklist": '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
  <path d="M3 7l2 2 4-4" />
  <line x1="12" y1="7" x2="21" y2="7" />
  <path d="M3 15l2 2 4-4" />
  <line x1="12" y1="15" x2="21" y2="15" />
</svg>''',

    "team": '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
  <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
  <circle cx="9" cy="7" r="4" />
  <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
  <path d="M16 3.13a4 4 0 0 1 0 7.75" />
</svg>''',

    "bookmark": '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
  <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" />
</svg>''',

    "bell": '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
  <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
  <path d="M13.73 21a2 2 0 0 1-3.46 0" />
</svg>''',

    "chat": '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
  <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
  <line x1="8" y1="10" x2="8.01" y2="10" stroke-width="2.5" />
  <line x1="12" y1="10" x2="12.01" y2="10" stroke-width="2.5" />
  <line x1="16" y1="10" x2="16.01" y2="10" stroke-width="2.5" />
</svg>''',

    "sliders": '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
  <line x1="4" y1="21" x2="4" y2="14" />
  <line x1="4" y1="10" x2="4" y2="3" />
  <line x1="12" y1="21" x2="12" y2="12" />
  <line x1="12" y1="8" x2="12" y2="3" />
  <line x1="20" y1="21" x2="20" y2="16" />
  <line x1="20" y1="12" x2="20" y2="3" />
  <line x1="1" y1="14" x2="7" y2="14" />
  <line x1="9" y1="8" x2="15" y2="8" />
  <line x1="17" y1="16" x2="23" y2="16" />
</svg>''',

    "headset": '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
  <path d="M3 18v-6a9 9 0 0 1 18 0v6" />
  <path d="M21 19a2 2 0 0 1-2 2h-1a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2h3zM3 19a2 2 0 0 0 2 2h1a2 2 0 0 0 2-2v-3a2 2 0 0 0-2-2H3z" />
  <path d="M12 21h4" />
</svg>''',

    "feedback": '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
  <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
  <line x1="12" y1="8" x2="12" y2="12" stroke-width="2" />
  <line x1="12" y1="15" x2="12.01" y2="15" stroke-width="2.5" />
</svg>''',

    "more": '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor">
  <circle cx="5" cy="12" r="2" />
  <circle cx="12" cy="12" r="2" />
  <circle cx="19" cy="12" r="2" />
</svg>''',

    "brain": '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
  <path d="M9.5 2A4.5 4.5 0 0 0 5 6.5c0 .76.19 1.48.52 2.11A4 4 0 0 0 3 12.5a4 4 0 0 0 3.2 3.92A4.5 4.5 0 0 0 10.5 22h.5" />
  <path d="M14.5 2A4.5 4.5 0 0 1 19 6.5c0 .76-.19 1.48-.52 2.11A4 4 0 0 1 21 12.5a4 4 0 0 1-3.2 3.92A4.5 4.5 0 0 1 13.5 22h-.5" />
  <path d="M12 2v20" />
  <path d="M9 7.5a2.5 2.5 0 0 1 3-1" />
  <path d="M15 7.5a2.5 2.5 0 0 0-3-1" />
  <path d="M8 12h4" />
  <path d="M12 12h4" />
  <path d="M8.5 16.5a2.5 2.5 0 0 0 3.5 1" />
  <path d="M15.5 16.5a2.5 2.5 0 0 1-3.5 1" />
</svg>''',

    "tent": '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
  <path d="M19 21 12 4 5 21" />
  <path d="M12 4v17" />
  <path d="m2 21 10-17 10 17" />
  <path d="M9 21h6" />
</svg>'''
}

out_dir = "/Users/karthikramesh/Projects/Self/OSS/Dock T(w)oo/assets/icons"
os.makedirs(out_dir, exist_ok=True)
for name, svg in icons.items():
    with open(os.path.join(out_dir, f"{name}.svg"), "w") as f:
        f.write(svg)

print(f"Generated {len(icons)} SVG icons in {out_dir}")
