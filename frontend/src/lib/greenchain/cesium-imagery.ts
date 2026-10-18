// Satellite and base-map sources for the Cesium globe. Kept free of Cesium imports so the catalogue, the CSP
// allow-list and the date logic can be tested without WebGL.

export type ImageryKey = "esri" | "viirs" | "bluemarble" | "offline" | "ion"

export interface ImageryOption {
  key: ImageryKey
  label: string
  /** Credit shown in Cesium's attribution bar; providers require it. */
  attribution: string
  /** `remote` needs the network; `bundled` ships with the app and works offline. */
  kind: "remote" | "bundled"
  /** XYZ template ({z}/{y}/{x}) for remote tile sources. Absent for bundled and ion sources. */
  template?: string
  maximumLevel: number
  /** Honest one-line description including licensing caveats. */
  note: string
}

/** Hosts the browser may fetch satellite tiles from. next.config.ts allow-lists exactly these. */
export const SATELLITE_TILE_ORIGINS = ["https://services.arcgisonline.com", "https://gibs.earthdata.nasa.gov"] as const

/** GIBS publishes a day's composite after the day ends, so ask for yesterday (UTC). */
export function latestViirsDate(now: Date = new Date()): string {
  const d = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() - 1))
  return d.toISOString().slice(0, 10)
}

export function imageryOptions(now: Date = new Date(), ionEnabled = false): ImageryOption[] {
  const viirsDate = latestViirsDate(now)
  const options: ImageryOption[] = [
    {
      key: "esri",
      label: "High-res satellite",
      attribution: "Imagery © Esri, Maxar, Earthstar Geographics and the GIS User Community",
      kind: "remote",
      template: "https://services.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
      maximumLevel: 19,
      note: "Esri World Imagery: sub-metre in many regions. Attribution required; confirm Esri's terms before commercial use.",
    },
    {
      key: "viirs",
      label: `Daily true colour (${viirsDate})`,
      attribution: "NASA EOSDIS GIBS / VIIRS Suomi NPP corrected reflectance",
      kind: "remote",
      template: `https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/VIIRS_SNPP_CorrectedReflectance_TrueColor/default/${viirsDate}/GoogleMapsCompatible_Level9/{z}/{y}/{x}.jpg`,
      maximumLevel: 9,
      note: "NASA's most recent full-day satellite composite (about 250 m per pixel). Open data; clouds are real.",
    },
    {
      key: "bluemarble",
      label: "Blue Marble relief",
      attribution: "NASA EOSDIS GIBS / Blue Marble Next Generation with shaded relief and bathymetry",
      kind: "remote",
      template: "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/BlueMarble_ShadedRelief_Bathymetry/default/GoogleMapsCompatible_Level8/{z}/{y}/{x}.jpeg",
      maximumLevel: 8,
      note: "NASA cloud-free composite with shaded relief and ocean depth. Open data.",
    },
    {
      key: "offline",
      label: "Offline base map",
      attribution: "Natural Earth II, public domain (bundled with CesiumJS)",
      kind: "bundled",
      maximumLevel: 2,
      note: "Bundled low-resolution map. Used automatically when satellite tiles cannot be reached.",
    },
  ]
  if (ionEnabled) {
    options.splice(1, 0, {
      key: "ion",
      label: "Cesium ion world imagery + terrain",
      attribution: "Cesium ion (Bing Maps / Sentinel-2 and Cesium World Terrain)",
      kind: "remote",
      maximumLevel: 19,
      note: "Needs the NEXT_PUBLIC_CESIUM_ION_TOKEN configured for this deployment; adds 3D terrain.",
    })
  }
  return options
}

export function originOf(template: string): string {
  return new URL(template.replace("{z}", "0").replace("{y}", "0").replace("{x}", "0")).origin
}
