"use client"

// Satellite-imagery 3D globe for GreenChain, rendered by CesiumJS (WebGL). It draws the same SupplyScenario the
// SVG InteractiveGlobe draws and keeps the same selection contract, so the two are interchangeable. Positions are
// country-level approximations, so each supplier is a point inside a translucent disc, never a pinned factory.
// CesiumJS is loaded on demand, its assets are served from /cesium (see scripts/copy-cesium-assets.mjs), and the
// viewer is destroyed on unmount. Without WebGL the caller falls back to the SVG globe via `onUnsupported`.

import { useEffect, useMemo, useRef, useState } from "react"
import type * as CesiumNS from "cesium"

import { arcPoints, pointAlong, type ArcPoint } from "@/lib/greenchain/globe-arcs"
import { imageryOptions, type ImageryKey } from "@/lib/greenchain/cesium-imagery"
import type {
  SupplyScenario,
  SupplyScenarioSelectableNodeId,
} from "@/lib/greenchain/supply-chain-scenario"
import { cn } from "@/lib/greenchain/utils"

type Cesium = typeof CesiumNS

/** The slice of a Cesium view this component uses. It is built on CesiumWidget, not Viewer: the Viewer's toolbar widgets use Knockout,
 *  which compiles bindings with `new Function` and would force 'unsafe-eval' into the Content-Security-Policy. */
interface GlobeViewer {
  scene: CesiumNS.Scene
  camera: CesiumNS.Camera
  imageryLayers: CesiumNS.ImageryLayerCollection
  dataSources: CesiumNS.DataSourceCollection
  terrainProvider: CesiumNS.TerrainProvider
  screenSpaceEventHandler: CesiumNS.ScreenSpaceEventHandler
  isDestroyed(): boolean
  destroy(): void
}

export interface CesiumGlobeProps {
  bestEcoManufacturerByComponent: Record<string, string>
  className?: string
  hoveredNodeId: SupplyScenarioSelectableNodeId | null
  onHoverNode: (nodeId: SupplyScenarioSelectableNodeId | null) => void
  onSelectNode: (nodeId: SupplyScenarioSelectableNodeId | null) => void
  onUnsupported?: (reason: string) => void
  routeVisibleByComponent: Record<string, boolean>
  scenario: SupplyScenario
  selectedNodeId: SupplyScenarioSelectableNodeId | null
}

const ION_TOKEN = process.env.NEXT_PUBLIC_CESIUM_ION_TOKEN ?? ""
const GOOD = "#34D399"
const MODERATE = "#FBBF24"
const HIGH = "#F87171"
const DESTINATION = "#7DD3FC"
const ecoHex = (score: number) => (score < 40 ? GOOD : score < 60 ? MODERATE : HIGH)

export function webglAvailable(): boolean {
  try {
    const canvas = document.createElement("canvas")
    return Boolean(canvas.getContext("webgl2") ?? canvas.getContext("webgl"))
  } catch {
    return false
  }
}

function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true
}

function ensureWidgetCss() {
  if (document.getElementById("cesium-widgets-css")) return
  const link = document.createElement("link")
  link.id = "cesium-widgets-css"
  link.rel = "stylesheet"
  link.href = "/cesium/Widgets/widgets.css"
  document.head.appendChild(link)
}

// CesiumJS is served as its prebuilt bundle (see scripts/copy-cesium-assets.mjs) and loaded once with a script tag. It is not
// imported through the app bundler: Turbopack's production build of the package fails to parse. The `cesium` import above is types only.
let cesiumLoad: Promise<Cesium> | null = null
function loadCesium(): Promise<Cesium> {
  const w = window as unknown as { CESIUM_BASE_URL: string; Cesium?: Cesium }
  w.CESIUM_BASE_URL = "/cesium"
  ensureWidgetCss()
  if (w.Cesium) return Promise.resolve(w.Cesium)
  cesiumLoad ??= new Promise<Cesium>((resolve, reject) => {
    const script = document.createElement("script")
    script.src = "/cesium/Cesium.js"
    script.async = true
    script.onload = () => (w.Cesium ? resolve(w.Cesium) : reject(new Error("CesiumJS did not initialise.")))
    script.onerror = () => {
      cesiumLoad = null
      script.remove()
      reject(new Error("CesiumJS could not be loaded."))
    }
    document.head.appendChild(script)
  })
  return cesiumLoad
}

async function buildImagery(C: Cesium, key: ImageryKey, options: ReturnType<typeof imageryOptions>) {
  const option = options.find((o) => o.key === key) ?? options[0]
  if (option.key === "offline") {
    return C.TileMapServiceImageryProvider.fromUrl(C.buildModuleUrl("Assets/Textures/NaturalEarthII"), {
      credit: option.attribution,
    })
  }
  if (option.key === "ion") {
    return C.IonImageryProvider.fromAssetId(2)
  }
  return new C.UrlTemplateImageryProvider({
    url: option.template!,
    maximumLevel: option.maximumLevel,
    credit: option.attribution,
  })
}

interface Picked {
  kind: "supplier" | "route" | "destination"
  id: string
}

export function CesiumGlobe({
  bestEcoManufacturerByComponent,
  className,
  hoveredNodeId,
  onHoverNode,
  onSelectNode,
  onUnsupported,
  routeVisibleByComponent,
  scenario,
  selectedNodeId,
}: CesiumGlobeProps) {
  const hostRef = useRef<HTMLDivElement | null>(null)
  const creditRef = useRef<HTMLDivElement | null>(null)
  const viewerRef = useRef<GlobeViewer | null>(null)
  const cesiumRef = useRef<Cesium | null>(null)
  const sourceRef = useRef<CesiumNS.CustomDataSource | null>(null)
  const layerRef = useRef<CesiumNS.ImageryLayer | null>(null)
  const fallbackRef = useRef(false)
  const selectedRef = useRef(selectedNodeId)
  const hoveredRef = useRef(hoveredNodeId)
  const callbacks = useRef({ onHoverNode, onSelectNode })
  const [ready, setReady] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [imagery, setImagery] = useState<ImageryKey>("esri")
  const [notice, setNotice] = useState<string | null>(null)
  const [tip, setTip] = useState<{ x: number; y: number; text: string } | null>(null)
  const [spin, setSpin] = useState(false)
  const [lighting, setLighting] = useState(false)

  const options = useMemo(() => imageryOptions(new Date(), ION_TOKEN.length > 0), [])
  const activeOption = options.find((o) => o.key === imagery) ?? options[0]

  useEffect(() => {
    callbacks.current = { onHoverNode, onSelectNode }
    selectedRef.current = selectedNodeId
    hoveredRef.current = hoveredNodeId
    viewerRef.current?.scene.requestRender()
  }, [onHoverNode, onSelectNode, selectedNodeId, hoveredNodeId])

  // Create the viewer once.
  useEffect(() => {
    let cancelled = false
    const host = hostRef.current
    if (!host) return
    if (!webglAvailable()) {
      onUnsupported?.("WebGL is not available in this browser.")
      return
    }
    loadCesium()
      .then(async (C) => {
        if (cancelled || !hostRef.current) return
        cesiumRef.current = C
        if (ION_TOKEN) C.Ion.defaultAccessToken = ION_TOKEN
        const widget = new C.CesiumWidget(hostRef.current, {
          baseLayer: false,
          creditContainer: creditRef.current ?? undefined,
          requestRenderMode: true,
          maximumRenderTimeChange: Infinity,
          msaaSamples: 4,
        })
        const dataSources = new C.DataSourceCollection()
        const display = new C.DataSourceDisplay({ scene: widget.scene, dataSourceCollection: dataSources })
        const removeTick = widget.clock.onTick.addEventListener(() => {
          if (!display.update(widget.clock.currentTime)) widget.scene.requestRender()
        })
        const viewer: GlobeViewer = {
          scene: widget.scene,
          camera: widget.camera,
          imageryLayers: widget.imageryLayers,
          dataSources,
          get terrainProvider() { return widget.scene.terrainProvider },
          set terrainProvider(provider: CesiumNS.TerrainProvider) { widget.scene.terrainProvider = provider },
          screenSpaceEventHandler: widget.screenSpaceEventHandler,
          isDestroyed: () => widget.isDestroyed(),
          destroy: () => {
            removeTick()
            display.destroy()
            dataSources.destroy()
            widget.destroy()
          },
        }
        viewerRef.current = viewer
        const scene = viewer.scene
        scene.globe.baseColor = C.Color.fromCssColorString("#0b1220")
        scene.globe.showGroundAtmosphere = true
        scene.globe.enableLighting = false
        if (scene.skyAtmosphere) scene.skyAtmosphere.show = true
        scene.highDynamicRange = false
        scene.screenSpaceCameraController.minimumZoomDistance = 250_000
        scene.screenSpaceCameraController.maximumZoomDistance = 60_000_000
        viewer.screenSpaceEventHandler.removeInputAction(C.ScreenSpaceEventType.LEFT_DOUBLE_CLICK)
        if (ION_TOKEN) {
          try {
            viewer.terrainProvider = await C.createWorldTerrainAsync()
          } catch {
            /* terrain is optional */
          }
        }
        const source = new C.CustomDataSource("supply-chain")
        sourceRef.current = source
        await viewer.dataSources.add(source)
        const handler = new C.ScreenSpaceEventHandler(scene.canvas)
        const pick = (position: CesiumNS.Cartesian2): Picked | null => {
          const hit = scene.pick(position)
          const entity = hit?.id as CesiumNS.Entity | undefined
          const key = typeof entity?.id === "string" ? entity.id : null
          if (!key) return null
          const [kind, ...rest] = key.split(":")
          if (kind === "supplier" || kind === "route" || kind === "destination") return { kind, id: rest.join(":") }
          return null
        }
        handler.setInputAction((e: { position: CesiumNS.Cartesian2 }) => {
          const hit = pick(e.position)
          if (!hit) return callbacks.current.onSelectNode(null)
          callbacks.current.onSelectNode(hit.id as SupplyScenarioSelectableNodeId)
        }, C.ScreenSpaceEventType.LEFT_CLICK)
        handler.setInputAction((e: { endPosition: CesiumNS.Cartesian2 }) => {
          const hit = pick(e.endPosition)
          scene.canvas.style.cursor = hit ? "pointer" : "grab"
          callbacks.current.onHoverNode(hit ? (hit.id as SupplyScenarioSelectableNodeId) : null)
          if (hit) {
            const prop = source.entities.getById(`${hit.kind}:${hit.id}`)?.properties?.getValue(C.JulianDate.now()) as { tip?: string } | undefined
            setTip(prop?.tip ? { x: e.endPosition.x, y: e.endPosition.y, text: prop.tip } : null)
          } else setTip(null)
        }, C.ScreenSpaceEventType.MOUSE_MOVE)
        ;(viewer as unknown as { __handler: CesiumNS.ScreenSpaceEventHandler }).__handler = handler
        setReady(true)
      })
      .catch((e: unknown) => {
        if (cancelled) return
        setError(e instanceof Error ? e.message : "The 3D globe could not start.")
        onUnsupported?.("The 3D globe could not start.")
      })
    return () => {
      cancelled = true
      const viewer = viewerRef.current
      if (viewer && !viewer.isDestroyed()) {
        ;(viewer as unknown as { __handler?: CesiumNS.ScreenSpaceEventHandler }).__handler?.destroy()
        viewer.destroy()
      }
      viewerRef.current = null
      sourceRef.current = null
      layerRef.current = null
      setReady(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- the viewer is created exactly once per mount
  }, [])

  // Swap the imagery layer whenever the choice changes; a stale load is discarded if the choice changes again mid-flight.
  useEffect(() => {
    const C = cesiumRef.current
    const viewer = viewerRef.current
    if (!ready || !C || !viewer) return
    let cancelled = false
    ;(async () => {
      try {
        const provider = await buildImagery(C, imagery, options)
        if (cancelled || viewer.isDestroyed()) return
        if (layerRef.current) viewer.imageryLayers.remove(layerRef.current, true)
        layerRef.current = viewer.imageryLayers.addImageryProvider(provider, 0)
        if (imagery !== "offline") {
          let failures = 0
          provider.errorEvent.addEventListener(() => {
            failures += 1
            if (failures >= 4 && !fallbackRef.current && !viewer.isDestroyed()) {
              fallbackRef.current = true
              setNotice("Satellite tiles could not be reached, so the bundled offline base map is shown.")
              setImagery("offline")
            }
          })
        }
        viewer.scene.requestRender()
      } catch (e) {
        if (cancelled) return
        setNotice(`Could not load ${imagery} imagery (${e instanceof Error ? e.message : "unknown error"}).`)
        if (imagery !== "offline") setImagery("offline")
      }
    })()
    return () => {
      cancelled = true
    }
  }, [ready, imagery, options])

  useEffect(() => {
    const viewer = viewerRef.current
    if (viewer && !viewer.isDestroyed()) {
      viewer.scene.globe.enableLighting = lighting
      viewer.scene.requestRender()
    }
  }, [lighting, ready])

  // Rebuild entities when the scenario or the visible routes change.
  useEffect(() => {
    const C = cesiumRef.current
    const source = sourceRef.current
    const viewer = viewerRef.current
    if (!ready || !C || !source || !viewer) return
    source.entities.removeAll()
    const dest = scenario.destination
    const destPos = C.Cartesian3.fromDegrees(dest.location.lng, dest.location.lat, 0)
    source.entities.add({
      id: `destination:${scenario.product.id}`,
      position: new C.ConstantPositionProperty(destPos),
      point: { pixelSize: 13, color: C.Color.fromCssColorString(DESTINATION), outlineColor: C.Color.WHITE, outlineWidth: 2, disableDepthTestDistance: Number.POSITIVE_INFINITY },
      label: { text: dest.label, font: "600 13px system-ui, sans-serif", fillColor: C.Color.WHITE, outlineColor: C.Color.BLACK, outlineWidth: 3, style: C.LabelStyle.FILL_AND_OUTLINE, pixelOffset: new C.Cartesian2(0, -22), disableDepthTestDistance: Number.POSITIVE_INFINITY },
      properties: { tip: `Destination: ${dest.label}, ${dest.location.country}` },
    })
    const anchors: CesiumNS.Cartesian3[] = [destPos]
    for (const m of scenario.manufacturers) {
      const color = C.Color.fromCssColorString(ecoHex(m.ecoScore))
      const pos = C.Cartesian3.fromDegrees(m.location.lng, m.location.lat, 0)
      anchors.push(pos)
      const best = bestEcoManufacturerByComponent[m.componentId] === m.id
      const state = () => (selectedRef.current === m.id ? 2 : hoveredRef.current === m.id ? 1 : 0)
      source.entities.add({
        id: `supplier:${m.id}`,
        position: new C.ConstantPositionProperty(pos),
        point: {
          pixelSize: new C.CallbackProperty(() => [11, 15, 20][state()] + (best ? 2 : 0), false),
          color,
          outlineColor: new C.CallbackProperty(() => (state() ? C.Color.WHITE : C.Color.fromCssColorString("#0b1220")), false),
          outlineWidth: 2,
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        },
        ellipse: {
          semiMajorAxis: 320_000,
          semiMinorAxis: 320_000,
          material: new C.ColorMaterialProperty(new C.CallbackProperty(() => color.withAlpha([0.1, 0.18, 0.28][state()]), false)),
          height: 0,
        },
        label: {
          text: `${m.name.replace("Illustrative ", "")}${m.isCurrent ? " (incumbent)" : ""}`,
          font: "600 12px system-ui, sans-serif",
          fillColor: C.Color.WHITE,
          outlineColor: C.Color.BLACK,
          outlineWidth: 3,
          style: C.LabelStyle.FILL_AND_OUTLINE,
          pixelOffset: new C.Cartesian2(0, 20),
          distanceDisplayCondition: new C.DistanceDisplayCondition(0, 28_000_000),
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        },
        properties: {
          tip: `${m.name}: eco score ${m.ecoScore.toFixed(0)} (lower is better), ${m.location.country}. Country-level position, not a verified facility.`,
        },
      })
    }
    for (const route of scenario.routes) {
      if (routeVisibleByComponent[route.componentId] === false) continue
      const m = scenario.manufacturers.find((x) => x.id === route.manufacturerId)
      if (!m) continue
      const points: ArcPoint[] = arcPoints(m.location, dest.location)
      const color = C.Color.fromCssColorString(ecoHex(m.ecoScore))
      const best = bestEcoManufacturerByComponent[m.componentId] === m.id
      const active = () => selectedRef.current === m.id || hoveredRef.current === m.id
      source.entities.add({
        id: `route:${m.id}`,
        polyline: {
          positions: C.Cartesian3.fromDegreesArrayHeights(points.flatMap((p) => [p.lng, p.lat, p.height])),
          width: new C.CallbackProperty(() => (active() ? 6 : best ? 4.5 : 3), false),
          material: new C.PolylineGlowMaterialProperty({
            glowPower: 0.22,
            color: new C.CallbackProperty(() => color.withAlpha(active() ? 1 : best ? 0.9 : m.isCurrent ? 0.7 : 0.45), false),
          }),
        },
        properties: { tip: `Route from ${m.location.country} to ${dest.location.country} (${m.name})` },
      })
      if (!prefersReducedMotion()) {
        const offset = (route.id.length % 7) / 7
        source.entities.add({
          id: `pulse:${route.id}`,
          position: new C.CallbackPositionProperty((_time, result) => {
            const p = pointAlong(points, (performance.now() / 9000 + offset) % 1)
            return C.Cartesian3.fromDegrees(p.lng, p.lat, p.height, undefined, result)
          }, false),
          point: { pixelSize: 6, color: C.Color.WHITE.withAlpha(0.95), disableDepthTestDistance: Number.POSITIVE_INFINITY },
        })
      }
    }
    const bounds = C.BoundingSphere.fromPoints(anchors)
    viewer.camera.flyToBoundingSphere(bounds, {
      duration: 0,
      offset: new C.HeadingPitchRange(0, -Math.PI / 2.3, Math.max(bounds.radius * 3.2, 9_000_000)),
    })
    viewer.scene.requestRender()
  }, [ready, scenario, bestEcoManufacturerByComponent, routeVisibleByComponent])

  // Animate only while the globe is on screen, the tab is visible, and motion is allowed.
  useEffect(() => {
    const viewer = viewerRef.current
    const host = hostRef.current
    if (!ready || !viewer || !host || prefersReducedMotion()) return
    let onScreen = true
    const observer = new IntersectionObserver(([entry]) => {
      onScreen = entry.isIntersecting
    })
    observer.observe(host)
    const timer = window.setInterval(() => {
      if (!onScreen || document.hidden || viewer.isDestroyed()) return
      if (spin) viewer.camera.rotate(cesiumRef.current!.Cartesian3.UNIT_Z, -0.0009)
      viewer.scene.requestRender()
    }, 40)
    return () => {
      window.clearInterval(timer)
      observer.disconnect()
    }
  }, [ready, spin])

  // Focus the camera on whatever supplier is selected.
  useEffect(() => {
    const C = cesiumRef.current
    const viewer = viewerRef.current
    if (!ready || !C || !viewer || !selectedNodeId) return
    const m = scenario.manufacturers.find((x) => x.id === selectedNodeId)
    if (!m) return
    const a = C.Cartesian3.fromDegrees(m.location.lng, m.location.lat, 0)
    const b = C.Cartesian3.fromDegrees(scenario.destination.location.lng, scenario.destination.location.lat, 0)
    const bounds = C.BoundingSphere.fromPoints([a, b])
    viewer.camera.flyToBoundingSphere(bounds, {
      duration: prefersReducedMotion() ? 0 : 1.4,
      offset: new C.HeadingPitchRange(0, -Math.PI / 2.4, Math.max(bounds.radius * 3.4, 6_500_000)),
    })
  }, [ready, selectedNodeId, scenario])

  const resetView = () => {
    const C = cesiumRef.current
    const viewer = viewerRef.current
    if (!C || !viewer) return
    const pts = [
      ...scenario.manufacturers.map((m) => C.Cartesian3.fromDegrees(m.location.lng, m.location.lat, 0)),
      C.Cartesian3.fromDegrees(scenario.destination.location.lng, scenario.destination.location.lat, 0),
    ]
    const bounds = C.BoundingSphere.fromPoints(pts)
    viewer.camera.flyToBoundingSphere(bounds, { duration: 1, offset: new C.HeadingPitchRange(0, -Math.PI / 2.3, Math.max(bounds.radius * 3.2, 9_000_000)) })
    onSelectNode(null)
  }

  if (error) {
    return (
      <div role="alert" className={cn("grid place-items-center p-6 text-caption text-muted", className)}>
        The 3D satellite globe could not start: {error}
      </div>
    )
  }

  return (
    <div className={cn("relative isolate overflow-hidden bg-[#050912]", className)}>
      <div ref={hostRef} className="size-full" role="application" aria-label="Satellite globe of supplier locations and shipping routes. The supplier table below is the keyboard-accessible alternative." />
      {!ready && <p role="status" className="absolute inset-0 grid place-items-center text-caption text-muted">Starting satellite globe…</p>}
      {tip && <div className="pointer-events-none absolute z-10 max-w-[260px] rounded-sm border border-line bg-surface/95 px-2 py-1 text-micro text-ink shadow" style={{ left: tip.x + 14, top: tip.y + 14 }}>{tip.text}</div>}
      <div className="absolute left-2 top-2 z-10 flex max-w-[calc(100%-7rem)] flex-wrap gap-1" role="group" aria-label="Globe imagery">
        {options.map((o) => (
          <button key={o.key} type="button" aria-pressed={imagery === o.key} title={o.note}
            onClick={() => { fallbackRef.current = false; setNotice(null); setImagery(o.key) }}
            className={cn("min-h-8 border px-2 text-micro", imagery === o.key ? "border-ink bg-surface-2 font-semibold text-ink" : "border-line bg-surface/90 text-muted hover:bg-surface-2")}>
            {o.label}
          </button>
        ))}
      </div>
      <div className="absolute right-2 top-2 z-10 flex flex-col gap-1">
        <button type="button" onClick={resetView} className="min-h-8 border border-line bg-surface/90 px-2 text-micro text-ink hover:bg-surface-2">Reset view</button>
        <button type="button" aria-pressed={spin} onClick={() => setSpin((s) => !s)} className="min-h-8 border border-line bg-surface/90 px-2 text-micro text-ink hover:bg-surface-2">{spin ? "Stop spin" : "Spin"}</button>
        <button type="button" aria-pressed={lighting} onClick={() => setLighting((s) => !s)} className="min-h-8 border border-line bg-surface/90 px-2 text-micro text-ink hover:bg-surface-2">Day / night</button>
      </div>
      <div className="pointer-events-none absolute bottom-6 left-2 z-10 max-w-[70%] space-y-1 text-micro text-white [text-shadow:0_1px_2px_#000]">
        <p className="flex flex-wrap gap-x-3">
          <span><i className="mr-1 inline-block size-2 rounded-full" style={{ background: GOOD }} />lower impact</span>
          <span><i className="mr-1 inline-block size-2 rounded-full" style={{ background: MODERATE }} />moderate</span>
          <span><i className="mr-1 inline-block size-2 rounded-full" style={{ background: HIGH }} />higher impact</span>
          <span><i className="mr-1 inline-block size-2 rounded-full" style={{ background: DESTINATION }} />destination</span>
        </p>
        <p>Discs mark country-level positions; a supplier&apos;s real facility may be hundreds of kilometres away.</p>
        {notice && <p role="status" className="text-amber-200">{notice}</p>}
      </div>
      <div ref={creditRef} className="absolute bottom-0 right-0 z-10 max-w-full bg-black/50 px-1 text-[10px] text-white" aria-label={`Imagery credit: ${activeOption.attribution}`} />
    </div>
  )
}
