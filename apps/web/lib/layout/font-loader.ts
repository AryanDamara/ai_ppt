/**
 * Module 8 — Font Loader (FOIT/FOUT Prevention)
 * Ensures fonts are loaded before text measurement.
 */

interface LoadedFont {
  family: string
  url: string
  face: FontFace
  metricsKey: string
}

const _loadedFonts = new Map<string, LoadedFont>()

const THEME_FONT_URLS: Record<string, Array<{ family: string; url: string }>> = {
  corporate_dark: [
    { family: 'Inter', url: '/fonts/inter/Inter-Regular.woff2' },
    { family: 'Inter Bold', url: '/fonts/inter/Inter-Bold.woff2' },
  ],
  modern_light: [
    { family: 'Inter', url: '/fonts/inter/Inter-Regular.woff2' },
    { family: 'Playfair Display', url: '/fonts/playfair/PlayfairDisplay-Regular.woff2' },
  ],
  startup_minimal: [
    { family: 'Inter', url: '/fonts/inter/Inter-Regular.woff2' },
    { family: 'Inter Bold', url: '/fonts/inter/Inter-Bold.woff2' },
  ],
  healthcare_clinical: [
    { family: 'Inter', url: '/fonts/inter/Inter-Regular.woff2' },
    { family: 'Inter Bold', url: '/fonts/inter/Inter-Bold.woff2' },
  ],
  financial_formal: [
    { family: 'Inter', url: '/fonts/inter/Inter-Regular.woff2' },
    { family: 'Playfair Display', url: '/fonts/playfair/PlayfairDisplay-Regular.woff2' },
  ],
}

export async function loadFont(family: string, url: string): Promise<LoadedFont> {
  const cacheKey = `${family}::${url}`

  if (_loadedFonts.has(cacheKey)) {
    return _loadedFonts.get(cacheKey)!
  }

  const face = new FontFace(family, `url(${url})`)

  // CRITICAL: await this — do not proceed until font is fully loaded
  await face.load()

  // Add to document so CSS can use it
  document.fonts.add(face)

  // Also wait for document.fonts.ready to ensure layout is stable
  await document.fonts.ready

  const loaded: LoadedFont = { family, url, face, metricsKey: cacheKey }
  _loadedFonts.set(cacheKey, loaded)

  return loaded
}

export async function preloadThemeFonts(theme: string): Promise<void> {
  const fonts = THEME_FONT_URLS[theme] || THEME_FONT_URLS.modern_light

  // Load all theme fonts in parallel — but wait for ALL before proceeding
  await Promise.all(fonts.map(f => loadFont(f.family, f.url)))
}

export function areFontsLoaded(families: string[]): boolean {
  return families.every(family =>
    [..._loadedFonts.values()].some(f => f.family === family)
  )
}

export function getLoadedFont(family: string): LoadedFont | undefined {
  return [..._loadedFonts.values()].find(f => f.family === family)
}

export function clearFontCache(): void {
  _loadedFonts.clear()
}