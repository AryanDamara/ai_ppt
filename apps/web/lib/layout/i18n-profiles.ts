/**
 * Module 4 — i18n Typography Profiles (BiDi-Aware)
 * Frontend version: Script-specific typography settings.
 */

import type { TypographyProfile } from './types'

// Elements that NEVER flip in RTL layouts
export const NEVER_MIRROR_ELEMENT_TYPES = new Set([
  'chart', 'image', 'video',
])

// Icons that should NOT flip in RTL
export const NON_DIRECTIONAL_ICONS = new Set([
  'search', 'settings', 'home', 'user', 'mail', 'bell',
  'star', 'heart', 'share', 'download', 'upload', 'close',
  'plus', 'minus', 'check', 'info', 'warning', 'error',
])

// Icons that SHOULD flip in RTL
export const DIRECTIONAL_ICONS = new Set([
  'arrow_left', 'arrow_right', 'chevron_left', 'chevron_right',
  'forward', 'back', 'next', 'previous', 'undo', 'redo',
])

export const LATIN: TypographyProfile = {
  script: 'latin',
  line_height_multiplier: 1.2,
  title_to_body_ratio: 1.8,
  min_body_font_size_px: 18.0,
  max_body_font_size_px: 28.0,
  rtl: false,
  mirror_horizontal: false,
  text_align: () => 'left',
}

export const CJK: TypographyProfile = {
  script: 'cjk',
  line_height_multiplier: 1.75,
  title_to_body_ratio: 1.6,
  min_body_font_size_px: 16.0,
  max_body_font_size_px: 24.0,
  rtl: false,
  mirror_horizontal: false,
  text_align: () => 'left',
}

export const RTL: TypographyProfile = {
  script: 'rtl',
  line_height_multiplier: 1.4,
  title_to_body_ratio: 1.8,
  min_body_font_size_px: 18.0,
  max_body_font_size_px: 28.0,
  rtl: true,
  mirror_horizontal: true,
  text_align: () => 'right',
}

const PROFILE_MAP: Record<string, TypographyProfile> = {
  en: LATIN, 'en-US': LATIN, 'en-GB': LATIN,
  fr: LATIN, de: LATIN, es: LATIN, it: LATIN,
  pt: LATIN, nl: LATIN, pl: LATIN,
  zh: CJK, 'zh-CN': CJK, 'zh-TW': CJK,
  ja: CJK, ko: CJK,
  ar: RTL, he: RTL, fa: RTL, ur: RTL,
}

export function getProfile(language: string): TypographyProfile {
  if (PROFILE_MAP[language]) return PROFILE_MAP[language]
  const prefix = language.split('-')[0]
  if (PROFILE_MAP[prefix]) return PROFILE_MAP[prefix]
  return LATIN
}

export function shouldMirrorElement(
  profile: TypographyProfile,
  elementType: string,
  iconName?: string,
): boolean {
  if (!profile.mirror_horizontal) return false
  if (NEVER_MIRROR_ELEMENT_TYPES.has(elementType)) return false
  if (elementType === 'icon' && iconName) {
    if (NON_DIRECTIONAL_ICONS.has(iconName)) return false
    if (DIRECTIONAL_ICONS.has(iconName)) return true
  }
  return true
}

export function flipXCoordinate(x: number, width: number, slideWidth = 1000): number {
  return slideWidth - x - width
}

export function flipVisualAnchor(anchor: string, profile: TypographyProfile): string {
  if (!profile.mirror_horizontal) return anchor
  if (anchor === 'left') return 'right'
  if (anchor === 'right') return 'left'
  return anchor
}