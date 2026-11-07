import { OrbitControls } from '@react-three/drei'
import { Canvas, useFrame } from '@react-three/fiber'
import { useLayoutEffect, useMemo, useRef, useState } from 'react'
import type { MutableRefObject } from 'react'
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
        <sphereGeometry args={[0.09, 12, 12]} />
        <meshStandardMaterial roughness={0.45} />
      </instancedMesh>
    </>
  )
}

/**
 * Cluster labels are ordinary DOM nodes positioned from the camera projection each frame.
 * (drei's <Html> mounts its own React root inside the canvas; unmounting it on navigation threw
 * "removeChild: not a child of this node" and could leave the next page half-rendered.)
 */
function LabelProjector({
  clusters,
  els,
}: {
  clusters: UCluster[]
  els: MutableRefObject<(HTMLSpanElement | null)[]>
}) {
  const v = useMemo(() => new THREE.Vector3(), [])
  useFrame(({ camera, size }) => {
    clusters.forEach((c, i) => {
      const el = els.current[i]
      if (!el) return
      v.set(c.centroid[0] * SCALE, c.centroid[1] * SCALE + 0.35, c.centroid[2] * SCALE).project(
        camera,
      )
      el.style.display = v.z > 1 ? 'none' : 'block'
      el.style.transform = `translate(-50%, -50%) translate(${(v.x * 0.5 + 0.5) * size.width}px, ${
        (-v.y * 0.5 + 0.5) * size.height
      }px)`
    })
  })
  return null
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
      // never unmount the canvas from inside its own render loop (React/DOM error): defer
      setTimeout(onSlow, 0)
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
  const els = useRef<(HTMLSpanElement | null)[]>([])
  return (
    <div className="absolute inset-0 overflow-hidden">
      <Canvas
        camera={{ position: [0, 0, 6], fov: 50 }}
        dpr={[1, 2]}
        gl={{ antialias: points.length < 3000, powerPreference: 'high-performance' }}
        aria-label="3D document universe"
      >
        <color attach="background" args={['#020617']} />
        <ambientLight intensity={0.9} />
        <directionalLight position={[5, 5, 5]} intensity={1.2} />
        <Points points={points} colorBy={colorBy} onOpen={onOpen} onHover={onHover} />
        <LabelProjector clusters={clusters} els={els} />
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
      <div className="pointer-events-none absolute inset-0">
        {clusters.map((c, i) => (
          <span
            key={c.id}
            ref={(el) => {
              els.current[i] = el
            }}
            className="absolute left-0 top-0 whitespace-nowrap rounded bg-slate-800/80 px-1.5 py-0.5 text-[11px] text-slate-200"
            style={{ display: 'none' }}
          >
            {c.label || `cluster ${c.id + 1}`} · {c.n}
          </span>
        ))}
      </div>
    </div>
  )
}
