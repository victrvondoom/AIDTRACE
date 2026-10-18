"use client"

// The hub's 3D capability graph (Three.js). Each node is a camera-facing card whose colour is the capability's LIVE state,
// each edge a dependency; hovering inspects a node and clicking opens its workspace in the same page. The scene is a rendering
// of /hub/capabilities, not a source of truth. It renders on demand when idle, pauses off-screen and in hidden tabs, honours
// prefers-reduced-motion (no spin, no particles), and disposes every GPU resource on unmount.

import { useEffect, useRef } from "react"
import * as THREE from "three"
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js"

import { layoutCapabilities, type Vec3 } from "@/lib/overview-layout"
import type { HubCapability } from "@/lib/lab-api"

export interface CapabilityGlobe3DProps {
  capabilities: HubCapability[]
  edges: { source: string; target: string; rel: string }[]
  /** The node being inspected (hover or keyboard focus); drawn enlarged with a halo. */
  inspectedId: string | null
  onInspect: (id: string | null) => void
  onOpen: (id: string) => void
  className?: string
}

const STATE_COLOR: Record<string, string> = { OPERATIONAL: "#34D399", LIMITED: "#FBBF24", UNAVAILABLE: "#F87171" }
const STATE_LABEL: Record<string, string> = { OPERATIONAL: "Operational", LIMITED: "Limited", UNAVAILABLE: "Unavailable" }
const KAIROS = "#FF6A3D"

function reducedMotion(): boolean {
  return typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true
}

function wrap(ctx: CanvasRenderingContext2D, text: string, maxWidth: number, maxLines: number): string[] {
  const words = text.split(/\s+/)
  const lines: string[] = []
  let line = ""
  for (const word of words) {
    const next = line ? `${line} ${word}` : word
    if (ctx.measureText(next).width > maxWidth && line) {
      lines.push(line)
      line = word
      if (lines.length === maxLines) break
    } else line = next
  }
  if (lines.length < maxLines && line) lines.push(line)
  if (lines.length === maxLines && words.join(" ").length > lines.join(" ").length) lines[maxLines - 1] = `${lines[maxLines - 1].replace(/[.,;\s]+$/, "")}…`
  return lines
}

function cardTexture(cap: HubCapability, inspected: boolean): THREE.CanvasTexture {
  const canvas = document.createElement("canvas")
  canvas.width = 512
  canvas.height = 256
  const ctx = canvas.getContext("2d")!
  const accent = cap.id === "overview" ? KAIROS : STATE_COLOR[cap.state] ?? "#94A3B8"
  ctx.fillStyle = inspected ? "#17233b" : "#0e1626"
  ctx.strokeStyle = accent
  ctx.lineWidth = inspected ? 8 : 4
  ctx.beginPath()
  ctx.roundRect(8, 8, 496, 240, 26)
  ctx.fill()
  ctx.stroke()
  ctx.fillStyle = accent
  ctx.beginPath()
  ctx.arc(46, 56, 14, 0, Math.PI * 2)
  ctx.fill()
  ctx.fillStyle = "#F8FAFC"
  ctx.font = "600 40px system-ui, -apple-system, 'Segoe UI', sans-serif"
  ctx.textBaseline = "middle"
  ctx.fillText(cap.name.length > 22 ? `${cap.name.slice(0, 21)}…` : cap.name, 74, 56)
  ctx.fillStyle = accent
  ctx.font = "700 24px system-ui, sans-serif"
  ctx.fillText((cap.id === "overview" ? "YOU ARE HERE" : (STATE_LABEL[cap.state] ?? cap.state)).toUpperCase(), 30, 112)
  ctx.fillStyle = "#CBD5E1"
  ctx.font = "400 25px system-ui, sans-serif"
  wrap(ctx, cap.detail, 450, 3).forEach((l, i) => ctx.fillText(l, 30, 156 + i * 32))
  const texture = new THREE.CanvasTexture(canvas)
  texture.colorSpace = THREE.SRGBColorSpace
  texture.anisotropy = 4
  return texture
}

export function CapabilityGlobe3D({ capabilities, edges, inspectedId, onInspect, onOpen, className }: CapabilityGlobe3DProps) {
  const hostRef = useRef<HTMLDivElement | null>(null)
  const api = useRef({ onInspect, onOpen })
  const sceneState = useRef<{ update: (caps: HubCapability[], inspected: string | null) => void } | null>(null)
  const latest = useRef({ capabilities, inspectedId })

  useEffect(() => {
    api.current = { onInspect, onOpen }
  }, [onInspect, onOpen])

  // Build the scene once per edge-set / node-set change; texture and highlight updates go through sceneState.update.
  const idsKey = capabilities.map((c) => c.id).join("|")
  const edgesKey = edges.map((e) => `${e.source}>${e.target}`).join("|")

  useEffect(() => {
    latest.current = { capabilities, inspectedId }
    sceneState.current?.update(capabilities, inspectedId)
  }, [capabilities, inspectedId])

  useEffect(() => {
    const host = hostRef.current
    if (!host) return
    const motion = !reducedMotion()
    const positions = layoutCapabilities(latest.current.capabilities.map((c) => c.id))
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "high-performance" })
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
    renderer.setClearColor(0x000000, 0)
    host.appendChild(renderer.domElement)
    renderer.domElement.style.display = "block"
    renderer.domElement.setAttribute("aria-hidden", "true")

    const scene = new THREE.Scene()
    scene.fog = new THREE.Fog(0x070b14, 14, 30)
    const camera = new THREE.PerspectiveCamera(50, 1, 0.1, 100)
    camera.position.set(0, 3.2, 12.5)
    const controls = new OrbitControls(camera, renderer.domElement)
    controls.enableDamping = true
    controls.dampingFactor = 0.08
    controls.minDistance = 5
    controls.maxDistance = 30
    controls.autoRotate = motion
    controls.autoRotateSpeed = 0.45
    controls.enablePan = false

    // Star field: purely ambient depth cue, fixed seed so it never flickers between renders.
    const starGeo = new THREE.BufferGeometry()
    const stars = new Float32Array(600 * 3)
    let seed = 7
    const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647)
    for (let i = 0; i < 600; i += 1) {
      const r = 16 + rnd() * 10, a = rnd() * Math.PI * 2, b = Math.acos(2 * rnd() - 1)
      stars.set([r * Math.sin(b) * Math.cos(a), r * Math.cos(b), r * Math.sin(b) * Math.sin(a)], i * 3)
    }
    starGeo.setAttribute("position", new THREE.BufferAttribute(stars, 3))
    const starMat = new THREE.PointsMaterial({ color: 0x8aa0c8, size: 0.05, transparent: true, opacity: 0.7 })
    scene.add(new THREE.Points(starGeo, starMat))

    // Nodes.
    const sprites = new Map<string, THREE.Sprite>()
    const textures = new Map<string, THREE.CanvasTexture>()
    const halo = new THREE.Sprite(new THREE.SpriteMaterial({ color: 0xffffff, transparent: true, opacity: 0.0, depthWrite: false }))
    halo.scale.set(3.3, 1.8, 1)
    scene.add(halo)
    // The canvas is wide, so the sphere is stretched sideways: cards spread out instead of stacking in depth.
    const place = (id: string): THREE.Vector3 => {
      const [x, y, z] = positions[id] ?? ([0, 0, 0] as Vec3)
      return new THREE.Vector3(x * 1.7, y * 0.9, z * 0.8)
    }
    const setCard = (cap: HubCapability, inspected: boolean) => {
      let sprite = sprites.get(cap.id)
      if (!sprite) {
        sprite = new THREE.Sprite(new THREE.SpriteMaterial({ transparent: true, depthWrite: false }))
        sprite.position.copy(place(cap.id))
        sprite.userData.id = cap.id
        scene.add(sprite)
        sprites.set(cap.id, sprite)
      }
      textures.get(cap.id)?.dispose()
      const texture = cardTexture(cap, inspected)
      textures.set(cap.id, texture)
      const material = sprite.material as THREE.SpriteMaterial
      material.map = texture
      material.needsUpdate = true
      const scale = cap.id === "overview" ? 3.2 : inspected ? 3.1 : 2.7
      sprite.scale.set(scale, scale / 2, 1)
    }

    // Edges: faint dependency lines plus a brighter set for the inspected node, with flow particles on those.
    const edgeMaterial = new THREE.LineBasicMaterial({ color: 0x4a5d82, transparent: true, opacity: 0.38 })
    const hotMaterial = new THREE.LineBasicMaterial({ color: 0xffa27d, transparent: true, opacity: 0.95 })
    const toBuffer = (pairs: [string, string][]) => {
      const arr = new Float32Array(pairs.length * 6)
      pairs.forEach(([a, b], i) => arr.set([...place(a).toArray(), ...place(b).toArray()], i * 6))
      const g = new THREE.BufferGeometry()
      g.setAttribute("position", new THREE.BufferAttribute(arr, 3))
      return g
    }
    const ids = new Set(latest.current.capabilities.map((c) => c.id))
    const dependency = edges.filter((e) => ids.has(e.source) && ids.has(e.target)).map((e) => [e.source, e.target] as [string, string])
    const hostEdges = [...ids].filter((id) => id !== "overview").map((id) => ["overview", id] as [string, string])
    const baseLines = new THREE.LineSegments(toBuffer([...hostEdges, ...dependency]), edgeMaterial)
    scene.add(baseLines)
    let hotLines: THREE.LineSegments | null = null
    let hotPairs: [string, string][] = []
    const flowGeo = new THREE.BufferGeometry()
    const flow = new THREE.Points(flowGeo, new THREE.PointsMaterial({ color: 0xffffff, size: 0.11, transparent: true, opacity: 0.95 }))
    scene.add(flow)

    let currentInspected: string | null = null
    const highlight = (id: string | null) => {
      hotLines?.geometry.dispose()
      if (hotLines) scene.remove(hotLines)
      hotLines = null
      hotPairs = id ? [...hostEdges, ...dependency].filter(([a, b]) => a === id || b === id) : []
      if (hotPairs.length) {
        hotLines = new THREE.LineSegments(toBuffer(hotPairs), hotMaterial)
        scene.add(hotLines)
      }
      const sprite = id ? sprites.get(id) : undefined
      const haloMat = halo.material as THREE.SpriteMaterial
      if (sprite) {
        halo.position.copy(sprite.position)
        haloMat.opacity = 0.16
      } else haloMat.opacity = 0
    }

    // Rendering: continuous only while motion is allowed and the scene is visible; otherwise on demand.
    let visible = true
    let raf = 0
    let clock = 0
    let rendering = false
    const render = () => {
      rendering = true
      controls.update()
      if (motion && hotPairs.length) {
        const pts = new Float32Array(hotPairs.length * 3 * 2)
        hotPairs.forEach(([a, b], i) => {
          const pa = place(a), pb = place(b)
          for (let k = 0; k < 2; k += 1) {
            const t = (clock * 0.35 + i * 0.17 + k * 0.5) % 1
            pts.set([pa.x + (pb.x - pa.x) * t, pa.y + (pb.y - pa.y) * t, pa.z + (pb.z - pa.z) * t], (i * 2 + k) * 3)
          }
        })
        flowGeo.setAttribute("position", new THREE.BufferAttribute(pts, 3))
        flow.visible = true
      } else flow.visible = false
      renderer.render(scene, camera)
      rendering = false
    }
    const loop = () => {
      raf = 0
      if (!visible || document.hidden) return
      clock += 0.016
      render()
      // controls.update() emits "change", which may already have scheduled the next frame; never schedule a second one.
      if (motion && !raf) raf = requestAnimationFrame(loop)
    }
    const invalidate = () => {
      if (!raf && !rendering) raf = requestAnimationFrame(loop)
    }
    controls.addEventListener("change", invalidate)
    let userMoved = false
    controls.addEventListener("start", () => { userMoved = true; invalidate() })

    sceneState.current = {
      update: (caps, inspected) => {
        for (const cap of caps) setCard(cap, cap.id === inspected)
        if (inspected !== currentInspected) {
          currentInspected = inspected
          highlight(inspected)
        }
        invalidate()
      },
    }

    // Pointer interaction: hover inspects, a click that did not drag opens the workspace.
    const raycaster = new THREE.Raycaster()
    const pointer = new THREE.Vector2()
    const pick = (event: PointerEvent): string | null => {
      const rect = renderer.domElement.getBoundingClientRect()
      pointer.set(((event.clientX - rect.left) / rect.width) * 2 - 1, -(((event.clientY - rect.top) / rect.height) * 2 - 1))
      raycaster.setFromCamera(pointer, camera)
      const hit = raycaster.intersectObjects([...sprites.values()], false)[0]
      return hit ? (hit.object.userData.id as string) : null
    }
    let down: { x: number; y: number } | null = null
    const onMove = (e: PointerEvent) => {
      if (down) return
      const id = pick(e)
      renderer.domElement.style.cursor = id ? "pointer" : "grab"
      api.current.onInspect(id)
    }
    const onDown = (e: PointerEvent) => { down = { x: e.clientX, y: e.clientY } }
    const onUp = (e: PointerEvent) => {
      const moved = down ? Math.hypot(e.clientX - down.x, e.clientY - down.y) : 99
      down = null
      if (moved > 5) return
      const id = pick(e)
      if (id) api.current.onOpen(id)
    }
    const onLeave = () => api.current.onInspect(null)
    renderer.domElement.addEventListener("pointermove", onMove)
    renderer.domElement.addEventListener("pointerdown", onDown)
    renderer.domElement.addEventListener("pointerup", onUp)
    renderer.domElement.addEventListener("pointerleave", onLeave)

    const resize = () => {
      const w = Math.max(host.clientWidth, 1), h = Math.max(host.clientHeight, 1)
      renderer.setSize(w, h, false)
      renderer.domElement.style.width = "100%"
      renderer.domElement.style.height = "100%"
      camera.aspect = w / h
      // A narrow canvas (a phone) needs the camera further back to keep the side cards in frame; never override a user's own zoom.
      if (!userMoved) camera.position.setLength(Math.min(controls.maxDistance, 12.5 * Math.max(1, 1.75 / camera.aspect)))
      camera.updateProjectionMatrix()
      invalidate()
    }
    const resizeObserver = new ResizeObserver(resize)
    resizeObserver.observe(host)
    const intersection = new IntersectionObserver(([entry]) => { visible = entry.isIntersecting; if (visible) invalidate() })
    intersection.observe(host)
    const onVisibility = () => { if (!document.hidden) invalidate() }
    document.addEventListener("visibilitychange", onVisibility)
    resize()
    sceneState.current.update(latest.current.capabilities, latest.current.inspectedId)

    return () => {
      cancelAnimationFrame(raf)
      raf = 0
      sceneState.current = null
      document.removeEventListener("visibilitychange", onVisibility)
      resizeObserver.disconnect()
      intersection.disconnect()
      renderer.domElement.removeEventListener("pointermove", onMove)
      renderer.domElement.removeEventListener("pointerdown", onDown)
      renderer.domElement.removeEventListener("pointerup", onUp)
      renderer.domElement.removeEventListener("pointerleave", onLeave)
      controls.dispose()
      for (const sprite of sprites.values()) (sprite.material as THREE.SpriteMaterial).dispose()
      for (const t of textures.values()) t.dispose()
      ;(halo.material as THREE.SpriteMaterial).dispose()
      baseLines.geometry.dispose()
      hotLines?.geometry.dispose()
      flowGeo.dispose()
      starGeo.dispose()
      edgeMaterial.dispose()
      hotMaterial.dispose()
      starMat.dispose()
      ;(flow.material as THREE.PointsMaterial).dispose()
      renderer.dispose()
      renderer.forceContextLoss()
      renderer.domElement.remove()
    }
    // The scene is rebuilt only when the node or edge set changes; state updates flow through sceneState.update.
  }, [idsKey, edgesKey]) // eslint-disable-line react-hooks/exhaustive-deps

  return <div ref={hostRef} className={className} />
}
