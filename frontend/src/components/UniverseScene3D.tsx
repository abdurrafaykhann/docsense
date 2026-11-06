import { Html, OrbitControls } from '@react-three/drei'
import { Canvas, useFrame } from '@react-three/fiber'
import { useLayoutEffect, useMemo, useRef, useState } from 'react'
import * as THREE from 'three'
import { colorFor, shouldFallback } from '../lib/universe'
import type { ColorBy, UCluster, UPoint } from '../lib/universe'

interface Props {
  points: UPoint[]
  clusters: UCluster[]
  colorBy: ColorBy
  onOpen: (id: number) => void
  onHover: (p: UPoint | null) => void
  onSlow: () => void
}

const SCALE = 3 // the cloud lives in a unit ball; scale it up for a comfortable camera distance

/** One InstancedMesh for every document: a single draw call keeps 60 fps for thousands of points. */
function Points({ points, colorBy, onOpen, onHover }: Omit<Props, 'clusters' | 'onSlow'>) {
  const mesh = useRef<THREE.InstancedMesh>(null)
  const dummy = useMemo(() => new THREE.Object3D(), [])
  const [hover, setHover] = useState<number | null>(null)

  useLayoutEffect(() => {
    const m = mesh.current
    if (!m) return
    const color = new THREE.Color()
    points.forEach((p, i) => {
      dummy.position.set(p.x * SCALE, p.y * SCALE, p.z * SCALE)
      dummy.scale.setScalar(i === hover ? 1.8 : 1)
      dummy.updateMatrix()
      m.setMatrixAt(i, dummy.matrix)
      m.setColorAt(i, color.set(colorFor(p, colorBy)))
    })
    m.instanceMatrix.needsUpdate = true
    if (m.instanceColor) m.instanceColor.needsUpdate = true
  }, [points, colorBy, hover, dummy])

  const hovered = hover !== null ? points[hover] : null
  return (
    <>
      <instancedMesh
        ref={mesh}
        args={[undefined, undefined, points.length]}
        onPointerMove={(e) => {
          e.stopPropagation()
          if (e.instanceId !== undefined && e.instanceId !== hover) {
            setHover(e.instanceId)
            onHover(points[e.instanceId])
          }
        }}
        onPointerOut={() => {
          setHover(null)
          onHover(null)
        }}
        onClick={(e) => {
          e.stopPropagation()
          if (e.instanceId !== undefined) onOpen(points[e.instanceId].id)
        }}
      >
        <sphereGeometry args={[0.05, 10, 10]} />
        <meshStandardMaterial roughness={0.45} />
      </instancedMesh>
      {hovered && (
        <Html
          position={[hovered.x * SCALE, hovered.y * SCALE + 0.15, hovered.z * SCALE]}
          center
          style={{ pointerEvents: 'none' }}
        >
          <div className="whitespace-nowrap rounded-md border border-slate-600 bg-slate-900/95 px-2 py-1 text-xs text-slate-100 shadow">
            <strong>{hovered.name}</strong>
            <div className="text-slate-400">
              {hovered.vendor ?? 'unreviewed'}{' '}
              {hovered.total != null && `· PKR ${hovered.total.toLocaleString()}`}
            </div>
          </div>
        </Html>
      )}
    </>
  )
}

/** Measures frame times inside the render loop and reports sustained slowness. */
function FpsWatch({ onSlow }: { onSlow: () => void }) {
  const frames = useRef<number[]>([])
  const fired = useRef(false)
  useFrame((_, delta) => {
    frames.current.push(delta * 1000)
    if (frames.current.length > 240) frames.current.shift()
    if (!fired.current && shouldFallback(frames.current)) {
      fired.current = true
      onSlow()
    }
  })
  return null
}

export default function UniverseScene3D({
  points,
  clusters,
  colorBy,
  onOpen,
  onHover,
  onSlow,
}: Props) {
  return (
    <Canvas
      camera={{ position: [0, 0, 8], fov: 50 }}
      dpr={[1, 2]}
      gl={{ antialias: points.length < 3000, powerPreference: 'high-performance' }}
      aria-label="3D document universe"
    >
      <color attach="background" args={['#020617']} />
      <ambientLight intensity={0.9} />
      <directionalLight position={[5, 5, 5]} intensity={1.2} />
      <Points points={points} colorBy={colorBy} onOpen={onOpen} onHover={onHover} />
      {clusters.map((c) => (
        <Html
          key={c.id}
          position={[c.centroid[0] * SCALE, c.centroid[1] * SCALE + 0.35, c.centroid[2] * SCALE]}
          center
          distanceFactor={9}
          style={{ pointerEvents: 'none' }}
        >
          <span className="whitespace-nowrap rounded bg-slate-800/80 px-1.5 py-0.5 text-[11px] text-slate-200">
            {c.label || `cluster ${c.id + 1}`} · {c.n}
          </span>
        </Html>
      ))}
      <OrbitControls
        enableDamping
        dampingFactor={0.08}
        autoRotate
        autoRotateSpeed={0.6}
        minDistance={2}
        maxDistance={20}
      />
      <FpsWatch onSlow={onSlow} />
    </Canvas>
  )
}
