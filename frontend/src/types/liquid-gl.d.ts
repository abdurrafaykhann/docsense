declare module 'liquid-gl' {
  type LiquidLens = { destroy(): void; setTint?(tint: string | null): void }
  const liquidGL: (options: Record<string, unknown>) => LiquidLens | LiquidLens[]
  export default liquidGL
}
