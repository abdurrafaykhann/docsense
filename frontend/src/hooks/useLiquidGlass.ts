import { useEffect } from 'react'

type Lens = { destroy?: () => void }

/**
 * Turns the element(s) matching `target` into liquid glass with liquidGL.
 *
 * The glass refracts `.ds-ambient` (a static gradient layer) rather than the whole page: the app is a
 * single-page app whose content changes on every route, and liquidGL's snapshot is static. Until the
 * library has rendered, and on devices without WebGL/WebGPU, the CSS `.ds-glass` look stays in place.
 */
export function useLiquidGlass(
  target: string,
  enabled = true,
  options: Record<string, unknown> = {},
) {
  useEffect(() => {
    if (!enabled || import.meta.env.MODE === 'test' || typeof window === 'undefined') return
    let cancelled = false
    let lenses: Lens[] = []
    const reduceMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false

    import('liquid-gl')
      .then(({ default: liquidGL }) => {
        if (cancelled || !document.querySelector(target)) return
        try {
          const made = liquidGL({
            target,
            snapshot: '.ds-ambient',
            resolution: 1.5,
            refraction: 0.018,
            bevelDepth: 0.06,
            bevelWidth: 0.16,
            frost: 2.5,
            shadow: true,
            specular: !reduceMotion,
            reveal: 'fade',
            tint: 'rgba(233, 216, 196, 0.34)',
            ...options,
          })
          lenses = (Array.isArray(made) ? made : [made]).filter(Boolean) as Lens[]
        } catch {
          // The CSS glass remains; nothing else depends on the effect.
        }
      })
      .catch(() => {})

    return () => {
      cancelled = true
      lenses.forEach((l) => l.destroy?.())
    }
    // options are static per call site
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target, enabled])
}
