// Great-circle route arcs for the Cesium globe. Pure maths (no Cesium import) so it is unit-tested without WebGL.

export interface GeoPoint {
  lat: number
  lng: number
}

export interface ArcPoint extends GeoPoint {
  /** Metres above the ellipsoid. */
  height: number
}

const EARTH_RADIUS_KM = 6371.0088
const toRad = (deg: number) => (deg * Math.PI) / 180
const toDeg = (rad: number) => (rad * 180) / Math.PI

export function greatCircleDistanceKm(a: GeoPoint, b: GeoPoint): number {
  const dLat = toRad(b.lat - a.lat)
  const dLng = toRad(b.lng - a.lng)
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(a.lat)) * Math.cos(toRad(b.lat)) * Math.sin(dLng / 2) ** 2
  return 2 * EARTH_RADIUS_KM * Math.asin(Math.min(1, Math.sqrt(h)))
}

/**
 * Points along the great circle from `a` to `b`, lifted into an arc so a route reads as a path above the surface.
 * The lift is `peakFraction` of the ground distance, capped, and follows sin(pi*t) so both ends touch the surface.
 */
export function arcPoints(
  a: GeoPoint,
  b: GeoPoint,
  { segments = 64, peakFraction = 0.14, maxPeakMeters = 1_900_000 } = {}
): ArcPoint[] {
  const distanceKm = greatCircleDistanceKm(a, b)
  if (distanceKm < 1) {
    return [
      { ...a, height: 0 },
      { ...b, height: 0 },
    ]
  }
  const angular = distanceKm / EARTH_RADIUS_KM
  const peak = Math.min(maxPeakMeters, distanceKm * 1000 * peakFraction)
  const lat1 = toRad(a.lat)
  const lng1 = toRad(a.lng)
  const lat2 = toRad(b.lat)
  const lng2 = toRad(b.lng)
  const sinAngular = Math.sin(angular)
  const points: ArcPoint[] = []
  for (let i = 0; i <= segments; i += 1) {
    const t = i / segments
    // Spherical linear interpolation between the two unit vectors.
    const wa = Math.sin((1 - t) * angular) / sinAngular
    const wb = Math.sin(t * angular) / sinAngular
    const x = wa * Math.cos(lat1) * Math.cos(lng1) + wb * Math.cos(lat2) * Math.cos(lng2)
    const y = wa * Math.cos(lat1) * Math.sin(lng1) + wb * Math.cos(lat2) * Math.sin(lng2)
    const z = wa * Math.sin(lat1) + wb * Math.sin(lat2)
    points.push({
      lat: toDeg(Math.atan2(z, Math.hypot(x, y))),
      lng: toDeg(Math.atan2(y, x)),
      height: Math.sin(Math.PI * t) * peak,
    })
  }
  return points
}

/** The point a fraction `t` (0..1) of the way along an arc, interpolated between its vertices. */
export function pointAlong(points: ArcPoint[], t: number): ArcPoint {
  if (points.length === 0) throw new Error("pointAlong needs at least one point")
  if (points.length === 1) return points[0]
  const clamped = Math.min(1, Math.max(0, t))
  const scaled = clamped * (points.length - 1)
  const index = Math.min(points.length - 2, Math.floor(scaled))
  const local = scaled - index
  const p = points[index]
  const q = points[index + 1]
  // Segments are short, but never interpolate the long way round the antimeridian.
  let dLng = q.lng - p.lng
  if (dLng > 180) dLng -= 360
  if (dLng < -180) dLng += 360
  return {
    lat: p.lat + (q.lat - p.lat) * local,
    lng: p.lng + dLng * local,
    height: p.height + (q.height - p.height) * local,
  }
}
