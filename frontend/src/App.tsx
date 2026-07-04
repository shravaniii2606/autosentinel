// @ts-nocheck
import { useState, useRef, useEffect } from 'react'
import { MapContainer, TileLayer, CircleMarker, Popup, Circle, useMap, useMapEvents } from 'react-leaflet'
import L from 'leaflet'
import axios from 'axios'
import 'leaflet/dist/leaflet.css'
import 'leaflet-draw/dist/leaflet.draw.css'
import 'leaflet-draw'


interface Zone {
  id: number | string
  lat: number
  lon: number
  area_sqm: number
  severity: string
  risk_score: number
  action: string
  violation_type: string
  bhuvan_land_type?: string
  osm_flags?: string[]
  legal_flags?: string[]
  risk_boost_total?: number
  legal_explanation?: string
  microsoft_confirmed: boolean
  construction_detected?: boolean
  objects_found?: string[]
  vision_confidence?: number
  crane_present?: boolean
  building_present?: boolean
  container_present?: boolean
  yolo_boxes?: YoloBox[]
}

interface YoloBox {
  label: string
  confidence: number
  x1: number
  y1: number
  x2: number
  y2: number
}

interface VisionFilters {
  verified: boolean
  crane: boolean
  building: boolean
  container: boolean
}

interface Summary {
  total: number
  severity_breakdown: {
    CRITICAL: number
    HIGH: number
    MEDIUM: number
    LOW: number
  }
  microsoft_confirmed: number
  area: string
  period: string
}

const severityColor: Record<string, string> = {
  CRITICAL: '#ef4444',
  HIGH: '#f97316',
  MEDIUM: '#eab308',
  LOW: '#22c55e'
}

const severityRadius: Record<string, number> = {
  CRITICAL: 14,
  HIGH: 10,
  MEDIUM: 7,
  LOW: 4
}

const violationColor: Record<string, string> = {
  FOREST_ENCROACHMENT: '#15803d',
  WATER_BODY_ENCROACHMENT: '#0284c7',
  AGRICULTURAL_LAND: '#ca8a04',
  PROTECTED_LAND: '#7c3aed',
  POSSIBLE_PERMIT_VIOLATION: '#db2777',
  UNVERIFIED_ZONE: '#6b7280'
}

const visionObjectLabels: Record<string, string> = {
  building: 'Building',
  crane: 'Crane',
  container: 'Container'
}

const visionObjectMarkerLabels: Record<string, string> = {
  building: 'BLD',
  crane: 'CRN',
  container: 'CNT'
}

const visionObjectColors: Record<string, string> = {
  building: '#f97316',
  crane: '#ef4444',
  container: '#eab308'
}

const defaultVisionFilters: VisionFilters = {
  verified: false,
  crane: false,
  building: false,
  container: false
}

function getDetectedObjects(zone: Zone | null) {
  if (!zone) return []

  const objects = new Set<string>(
    Array.isArray(zone.objects_found)
      ? zone.objects_found.map(obj => String(obj).toLowerCase())
      : []
  )

  if (zone.building_present) objects.add('building')
  if (zone.crane_present) objects.add('crane')
  if (zone.container_present) objects.add('container')

  return ['building', 'crane', 'container'].filter(obj => objects.has(obj))
}

function getVisionBoxes(zone: Zone | null) {
  return Array.isArray(zone?.yolo_boxes) ? zone!.yolo_boxes : []
}

function formatVisionConfidence(value?: number) {
  const confidence = Number(value || 0)
  const percent = confidence > 1 ? confidence : confidence * 100
  return `${Math.round(percent)}%`
}

function getVisionStatuses(zone: Zone | null) {
  if (!zone) return []

  const statuses = []
  if (zone.crane_present) statuses.push('Active Construction')
  if (zone.building_present) statuses.push('Structure Found')
  if (zone.container_present) statuses.push('Material Storage Detected')

  return statuses
}

function getRiskBadges(zone: Zone | null) {
  if (!zone) return []

  const badges = []
  if (zone.crane_present) badges.push({ label: 'LIVE CONSTRUCTION', className: 'bg-red-600 text-white' })
  if (zone.building_present) badges.push({ label: 'STRUCTURE DETECTED', className: 'bg-slate-200 text-slate-900' })
  if (zone.container_present) badges.push({ label: 'MATERIALS FOUND', className: 'bg-slate-200 text-slate-900' })

  return badges
}

function normalizeYoloLabel(label: string) {
  const normalized = String(label || '').toLowerCase()
  if (normalized.includes('crane')) return 'crane'
  if (normalized.includes('container')) return 'container'
  if (normalized.includes('building') || normalized.includes('structure')) return 'building'
  return normalized
}


function ImageSlider({ beforeUrl, afterUrl, boxes = [] }: { beforeUrl: string, afterUrl: string, boxes?: YoloBox[] }) {
  const [sliderPos, setSliderPos] = useState(50)
  const [containerSize, setContainerSize] = useState({ width: 0, height: 0 })
  const [imageSize, setImageSize] = useState({ width: 0, height: 0 })
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!containerRef.current) return

    const updateSize = () => {
      if (!containerRef.current) return
      const rect = containerRef.current.getBoundingClientRect()
      setContainerSize({ width: rect.width, height: rect.height })
    }

    updateSize()
    const observer = new ResizeObserver(updateSize)
    observer.observe(containerRef.current)
    return () => observer.disconnect()
  }, [])

  const updateSlider = (clientX: number) => {
    if (!containerRef.current) return
    const rect = containerRef.current.getBoundingClientRect()
    const x = ((clientX - rect.left) / rect.width) * 100
    setSliderPos(Math.max(0, Math.min(100, x)))
  }

  const handleMouseMove = (e: React.MouseEvent) => updateSlider(e.clientX)
  const handleTouchMove = (e: React.TouchEvent) => {
    if (e.touches[0]) updateSlider(e.touches[0].clientX)
  }

  const getBoxStyle = (box: YoloBox) => {
    if (!containerSize.width || !containerSize.height || !imageSize.width || !imageSize.height) {
      return null
    }

    const raw = [box.x1, box.y1, box.x2, box.y2].map(Number)
    if (raw.some(value => !Number.isFinite(value))) return null

    const [x1Raw, y1Raw, x2Raw, y2Raw] = raw
    const normalized = Math.max(x1Raw, y1Raw, x2Raw, y2Raw) <= 1
    const sourceX1 = normalized ? x1Raw * imageSize.width : x1Raw
    const sourceY1 = normalized ? y1Raw * imageSize.height : y1Raw
    const sourceX2 = normalized ? x2Raw * imageSize.width : x2Raw
    const sourceY2 = normalized ? y2Raw * imageSize.height : y2Raw

    const scale = Math.max(containerSize.width / imageSize.width, containerSize.height / imageSize.height)
    const renderedWidth = imageSize.width * scale
    const renderedHeight = imageSize.height * scale
    const offsetX = (containerSize.width - renderedWidth) / 2
    const offsetY = (containerSize.height - renderedHeight) / 2

    const left = offsetX + Math.min(sourceX1, sourceX2) * scale
    const top = offsetY + Math.min(sourceY1, sourceY2) * scale
    const width = Math.abs(sourceX2 - sourceX1) * scale
    const height = Math.abs(sourceY2 - sourceY1) * scale

    if (width <= 0 || height <= 0) return null

    return { left, top, width, height }
  }

  const fullImageWidth = containerSize.width ? `${containerSize.width}px` : '100%'

  return (
    <div
      ref={containerRef}
      className="relative w-full h-48 overflow-hidden rounded-lg cursor-col-resize select-none"
      onMouseMove={handleMouseMove}
      onTouchMove={handleTouchMove}
      onClick={(e) => updateSlider(e.clientX)}
    >
      {/* After image (bottom) */}
      <img
        src={afterUrl}
        alt="After 2023"
        className="absolute inset-0 w-full h-full object-cover"
        onLoad={(e) => setImageSize({
          width: e.currentTarget.naturalWidth,
          height: e.currentTarget.naturalHeight
        })}
      />

      <div className="absolute inset-0 overflow-hidden pointer-events-none z-[1]">
        {boxes.map((box, index) => {
          const boxStyle = getBoxStyle(box)
          if (!boxStyle) return null

          const label = normalizeYoloLabel(box.label)
          const color = visionObjectColors[label] || '#38bdf8'

          return (
            <div
              key={`${box.label}-${index}`}
              className="absolute border-2 rounded-sm shadow-[0_0_0_1px_rgba(0,0,0,0.75)]"
              style={{
                left: `${boxStyle.left}px`,
                top: `${boxStyle.top}px`,
                width: `${boxStyle.width}px`,
                height: `${boxStyle.height}px`,
                borderColor: color
              }}
            >
              <span
                className="absolute left-0 top-0 max-w-full truncate px-1 py-0.5 text-[10px] font-bold uppercase leading-none text-slate-900"
                style={{ backgroundColor: color }}
              >
                {visionObjectLabels[label] || box.label} {formatVisionConfidence(box.confidence)}
              </span>
            </div>
          )
        })}
      </div>

      {/* Before image (top, clipped) */}
      <div
        className="absolute inset-0 overflow-hidden z-[2]"
        style={{ width: `${sliderPos}%` }}
      >
        <img
          src={beforeUrl}
          alt="Before 2019"
          className="absolute inset-0 h-full object-cover"
          style={{ width: fullImageWidth, maxWidth: 'none' }}
        />
      </div>

      {/* Slider line */}
      <div
        className="absolute top-0 bottom-0 w-0.5 bg-sky-50 z-10"
        style={{ left: `${sliderPos}%` }}
      >
        <div className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-8 h-8 bg-sky-50 rounded-full flex items-center justify-center shadow-lg">
          <span className="text-slate-900 text-xs font-bold">◀▶</span>
        </div>
      </div>

      {/* Labels */}
      <div className="absolute bottom-2 left-2 bg-slate-900/80 text-white text-xs px-2 py-0.5 rounded z-10">
        2019
      </div>
      <div className="absolute bottom-2 right-2 bg-slate-900/80 text-white text-xs px-2 py-0.5 rounded z-10">
        2023
      </div>
    </div>
  )
}
function ZoneImages({ zoneId, lat, lon, boxes = [] }: { zoneId: number | string, lat: number, lon: number, boxes?: YoloBox[] }) {
  const [images, setImages] = useState<{
    has_images: boolean
    before_url: string | null
    after_url: string | null
  } | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    setImages(null)
    
    // Try live-images endpoint for any zone
    axios.get(`http://localhost:8000/zones/${zoneId}/live-images`, {
      params: { lat, lon }
    })
      .then(res => {
        setImages(res.data)
        setLoading(false)
      })
      .catch(() => {
        setLoading(false)
      })
  }, [zoneId, lat, lon])

  if (loading) {
    return (
      <div className="mt-3 p-3 bg-sky-50 rounded text-xs text-slate-500 text-center animate-pulse">
        Fetching satellite imagery...
      </div>
    )
  }

  if (!images || !images.has_images) {
    return (
      <div className="mt-3 p-2 bg-sky-50 rounded text-xs text-slate-500 text-center">
        Satellite imagery unavailable for this zone
      </div>
    )
  }

  return (
    <div className="mt-3">
      <p className="text-xs text-slate-500 mb-2">SATELLITE EVIDENCE — drag to compare</p>
      <ImageSlider
        beforeUrl={images.before_url!}
        afterUrl={images.after_url!}
        boxes={boxes}
      />
    </div>
  )
}
function LiveScanPanel({ onZonesReceived }: { onZonesReceived: (zones: Zone[]) => void }) {
  const [scanning, setScanning] = useState(false)
  const [scanStatus, setScanStatus] = useState<{
  active: boolean
  progress: string
  jobId: string | null
} >({ active: false, progress: '', jobId: null })
  const [progress, setProgress] = useState('')
  const [jobId, setJobId] = useState<string | null>(null)
  const [drawnBounds, setDrawnBounds] = useState<any>(null)
  const pollRef = useRef<any>(null)
  useEffect(() => {
    const handler = (e: any) => {
      setDrawnBounds(e.detail)
    }
    window.addEventListener('bbox-drawn', handler)
    return () => window.removeEventListener('bbox-drawn', handler)
  }, [])

  const startScan = async () => {
    if (!drawnBounds) {
      alert('Draw an area on the map first using the Pen tool')
      return
    }
    setScanning(true)
    setProgress('Starting scan...')

    try {
      const res = await axios.post('http://localhost:8000/process_bbox', drawnBounds)
      const id = res.data.job_id
      setJobId(id)

      // Poll every 5 seconds
      pollRef.current = setInterval(async () => {
        const status = await axios.get(`http://localhost:8000/jobs/${id}`)
        setProgress(status.data.progress)

        if (status.data.status === 'done' && status.data.result) {
          clearInterval(pollRef.current)
          setScanning(false)
          onZonesReceived(status.data.result)
          setProgress(`Done — ${status.data.result.length} zones found`)
        } else if (status.data.status === 'error') {
          clearInterval(pollRef.current)
          setScanning(false)
          setProgress(`Failed: ${status.data.error}`)
        }
      }, 5000)
    } catch (err) {
      setScanning(false)
      setProgress('Request failed')
    }
  }

  return (
    <div className="p-4 border-b border-slate-200 bg-sky-50 rounded-lg">
      <p className="text-xs text-slate-500 mb-2 font-medium tracking-wider">LIVE SCAN</p>
      <p className="text-xs text-slate-500 mb-3">
        {drawnBounds
          ? `Area selected: ${drawnBounds.north.toFixed(3)}°N, ${drawnBounds.west.toFixed(3)}°W`
          : 'Draw an area on the map using the Pen tool'}
      </p>
      <button
        onClick={startScan}
        disabled={scanning || !drawnBounds}
        className="w-full py-2 rounded text-xs font-bold transition-colors disabled:opacity-50 text-white"
        style={{ backgroundColor: scanning ? '#2563eb' : '#0284c7' }}
      >
        {scanning ? 'Scanning...' : 'Scan Selected Area'}
      </button>
      {progress && (
        <div className="mt-2 p-2 bg-sky-50 rounded">
          <p className="text-xs text-blue-600">{progress}</p>
          {scanning && (
            <div className="mt-1 h-1 bg-sky-100 rounded overflow-hidden">
              <div className="h-full bg-blue-500 animate-pulse" style={{ width: '60%' }} />
            </div>
          )}
        </div>
      )}
    </div>
  )
}
export default function App() {
  const [drawMode, setDrawMode] = useState<'none'|'circle'|'pen'>('none')
  const [circleCenter, setCircleCenter] = useState<[number, number] | null>(null)
  const [circleRadius, setCircleRadius] = useState<number | null>(null) // meters
  const [drawnGeoJSON, setDrawnGeoJSON] = useState<any | null>(null)
  const [circleDrawn, setCircleDrawn] = useState(false)
  const [zones, setZones] = useState<Zone[]>([])
  const [summary, setSummary] = useState<Summary | null>(null)
  const [selectedZone, setSelectedZone] = useState<Zone | null>(null)
  const [severityFilter, setSeverityFilter] = useState<string>('ALL')
  const [violationFilter, setViolationFilter] = useState<string>('ALL')
  const [visionFilters, setVisionFilters] = useState<VisionFilters>(defaultVisionFilters)
  const [scanStatus, setScanStatus] = useState<{
    active: boolean
    progress: string
    jobId: string | null
  }>({ active: false, progress: '', jobId: null })
  const [mapInstance, setMapInstance] = useState<any>(null)
  const [coordinateLat, setCoordinateLat] = useState<string>('')
  const [coordinateLng, setCoordinateLng] = useState<string>('')

  const liveSummary = {
    total: zones.length,
    severity_breakdown: {
      CRITICAL: zones.filter(z => z.severity === 'CRITICAL').length,
      HIGH: zones.filter(z => z.severity === 'HIGH').length,
      MEDIUM: zones.filter(z => z.severity === 'MEDIUM').length,
      LOW: zones.filter(z => z.severity === 'LOW').length,
    }
  }

  useEffect(() => {
    axios.get('http://localhost:8000/zones').then(res => setZones(res.data.zones))
    axios.get('http://localhost:8000/zones/summary').then(res => setSummary(res.data))
  }, [])

  const filtered = zones.filter(z => {
    const sev = severityFilter === 'ALL' || z.severity === severityFilter
    const vio = violationFilter === 'ALL' || z.violation_type === violationFilter
    const vision =
      (!visionFilters.verified || Boolean(z.construction_detected)) &&
      (!visionFilters.crane || Boolean(z.crane_present)) &&
      (!visionFilters.building || Boolean(z.building_present)) &&
      (!visionFilters.container || Boolean(z.container_present))
    // If a circle is drawn, also filter by distance
    if (circleCenter && circleRadius != null) {
      const toRad = (deg: number) => deg * Math.PI / 180
      const R = 6371000 // meters
      const dLat = toRad(z.lat - circleCenter[0])
      const dLon = toRad(z.lon - circleCenter[1])
      const a = Math.sin(dLat/2) * Math.sin(dLat/2) + Math.cos(toRad(circleCenter[0])) * Math.cos(toRad(z.lat)) * Math.sin(dLon/2) * Math.sin(dLon/2)
      const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a))
      const dist = R * c
      return sev && vio && vision && dist <= circleRadius
    }
    return sev && vio && vision
  })

  const selectedObjects = getDetectedObjects(selectedZone)
  const selectedStatuses = getVisionStatuses(selectedZone)
  const selectedRiskBadges = getRiskBadges(selectedZone)
  const selectedBoxes = getVisionBoxes(selectedZone)
  const toggleVisionFilter = (key: keyof VisionFilters) => {
    setVisionFilters(prev => ({ ...prev, [key]: !prev[key] }))
  }

  const flyToCoordinates = () => {
    const lat = Number(coordinateLat)
    const lng = Number(coordinateLng)

    if (!Number.isFinite(lat) || !Number.isFinite(lng)) {
      alert('Please enter valid latitude and longitude values.')
      return
    }
    if (!mapInstance) return

    mapInstance.flyTo([lat, lng], 14, { duration: 1 })
    setSelectedZone(null)
    setDrawnGeoJSON(null)
    setCircleCenter(null)
    setCircleRadius(null)
  }

  return (
    <div className="flex h-screen bg-sky-50 text-slate-900 overflow-hidden">

      {/* Sidebar */}
      <div className="w-96 flex-shrink-0 bg-sky-50 border-r border-slate-200 flex flex-col overflow-y-auto">

        {/* Header */}
        <div className="p-5 border-b border-slate-200">
          <div className="flex items-center gap-2 mb-1">
            <div className="w-2 h-2 rounded-full bg-blue-500 animate-pulse"/>
            <h1 className="text-lg font-bold text-slate-900">AutoSentinel</h1>
          </div>
          <p className="text-xs text-slate-500">Unauthorized Construction Detection System</p>
          {summary && (
            <p className="text-xs text-slate-500 mt-1">
              {summary.area} · {summary.period}
            </p>
          )}
        </div>

        {/* Summary cards */}
        <div className="p-4 border-b border-slate-200">
  <p className="text-xs text-slate-500 mb-3 font-medium tracking-wider">DETECTION SUMMARY</p>
  <div className="grid grid-cols-2 gap-2">
    {Object.entries(liveSummary.severity_breakdown).map(([level, count]) => (
      <div
        key={level}
        onClick={() => setSeverityFilter(severityFilter === level ? 'ALL' : level)}
        className="bg-sky-50 rounded-lg p-3 cursor-pointer hover:bg-sky-100 transition-colors"
        style={{ borderLeft: `3px solid ${severityColor[level]}` }}
      >
        <div className="text-2xl font-bold" style={{ color: severityColor[level] }}>
          {count}
        </div>
        <div className="text-xs text-slate-500 mt-0.5">{level}</div>
      </div>
    ))}
  </div>
  <div className="mt-2 bg-sky-50 rounded-lg p-3">
    <div className="text-2xl font-bold text-slate-900">{liveSummary.total}</div>
    <div className="text-xs text-slate-500">
      Total Flagged Zones
      {zones.length > 931 && (
        <span className="text-green-400 ml-2">+{zones.length - 931} live</span>
      )}
    </div>
  </div>
</div>
<div className="mt-2 bg-sky-50 rounded-lg p-3">
  <div className="text-2xl font-bold text-blue-600">{summary?.microsoft_confirmed || 0}</div>
  <div className="text-xs text-slate-500">Microsoft AI Verified</div>
</div>
        {/* Coordinate jump */}
        <div className="p-4 border-b border-slate-200">
          <p className="text-xs text-slate-500 mb-2 font-medium tracking-wider">GO TO COORDINATES</p>
          <div className="grid grid-cols-2 gap-2">
            <input
              type="text"
              value={coordinateLat}
              onChange={e => setCoordinateLat(e.target.value)}
              placeholder="Latitude"
              className="w-full rounded-md border border-slate-300 bg-sky-50 px-3 py-2 text-sm text-slate-900 focus:outline-none focus:border-blue-500"
            />
            <input
              type="text"
              value={coordinateLng}
              onChange={e => setCoordinateLng(e.target.value)}
              placeholder="Longitude"
              className="w-full rounded-md border border-slate-300 bg-sky-50 px-3 py-2 text-sm text-slate-900 focus:outline-none focus:border-blue-500"
            />
          </div>
          <button
            onClick={flyToCoordinates}
            className="mt-3 w-full rounded-md bg-blue-600 px-3 py-2 text-xs font-semibold uppercase tracking-wide text-white transition-colors hover:bg-blue-500"
          >
            Center map
          </button>
          {selectedZone && (
            <button
              onClick={() => {
                setCoordinateLat(String(selectedZone.lat))
                setCoordinateLng(String(selectedZone.lon))
                setTimeout(flyToCoordinates, 0)
              }}
              className="mt-2 w-full rounded-md border border-blue-500 bg-sky-50 px-3 py-2 text-xs font-semibold uppercase tracking-wide text-blue-600 transition-colors hover:bg-blue-100"
            >
              Use selected zone coordinates
            </button>
          )}
        </div>

        {/* Severity filter */}
        <div className="p-4 border-b border-slate-200">
          <p className="text-xs text-slate-500 mb-2 font-medium tracking-wider">FILTER BY SEVERITY</p>
          <div className="flex flex-wrap gap-1.5">
            {['ALL', 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'].map(level => (
              <button
                key={level}
                onClick={() => setSeverityFilter(level)}
                className="text-xs px-3 py-1 rounded-full transition-colors"
                style={{
                  backgroundColor: severityFilter === level
                    ? (severityColor[level] || '#6366f1')
                    : '#374151',
                  color: 'white'
                }}
              >
                {level}
              </button>
            ))}
          </div>
        </div>

        {/* Violation type filter */}
        <div className="p-4 border-b border-slate-200">
          <p className="text-xs text-slate-500 mb-2 font-medium tracking-wider">FILTER BY VIOLATION</p>
          <div className="flex flex-wrap gap-1.5">
            {['ALL', 'FOREST_ENCROACHMENT', 'AGRICULTURAL_LAND', 'UNVERIFIED_ZONE'].map(type => (
              <button
                key={type}
                onClick={() => setViolationFilter(type)}
                className="text-xs px-2 py-1 rounded-full transition-colors"
                style={{
                  backgroundColor: violationFilter === type
                    ? (violationColor[type] || '#6366f1')
                    : '#374151',
                  color: 'white'
                }}
              >
                {type.replace(/_/g, ' ')}
              </button>
            ))}
          </div>
        </div>
        {/* Vision filters */}
        <div className="p-4 border-b border-slate-200">
          <p className="text-xs text-slate-500 mb-2 font-medium tracking-wider">FILTER BY VISION</p>
          <div className="flex flex-wrap gap-1.5">
            {[
              { key: 'verified', label: 'Vision Verified' },
              { key: 'crane', label: 'Crane Detected' },
              { key: 'building', label: 'Building Detected' },
              { key: 'container', label: 'Container Detected' },
            ].map(filter => (
              <button
                key={filter.key}
                onClick={() => toggleVisionFilter(filter.key as keyof VisionFilters)}
                className="text-xs px-2 py-1 rounded-full transition-colors"
                style={{
                  backgroundColor: visionFilters[filter.key as keyof VisionFilters]
                    ? '#0f766e'
                    : '#374151',
                  color: 'white'
                }}
              >
                {filter.label}
              </button>
            ))}
          </div>
        </div>

    {selectedZone?.microsoft_confirmed && (
  <div className="text-xs px-2 py-1 rounded mb-3 inline-block bg-blue-600 text-white ml-2">
    ✓ Microsoft Verified
  </div>
)}

        {/* Selected zone detail */}
        {selectedZone && (
          <div className="p-4 border-b border-slate-200">
            <p className="text-xs text-slate-500 mb-2 font-medium tracking-wider">SELECTED ZONE</p>
            <div
              className="rounded-lg p-4 bg-sky-50"
              style={{ borderLeft: `3px solid ${severityColor[selectedZone.severity]}` }}
            >
              {/* Severity + score */}
              <div className="flex justify-between items-center mb-3">
                <span
                  className="text-xs font-bold px-2 py-1 rounded"
                  style={{ backgroundColor: severityColor[selectedZone.severity] }}
                >
                  {selectedZone.severity}
                </span>
                <span className="text-sm font-bold text-white">
                  {selectedZone.risk_score}/100
                </span>
              </div>

              {/* Violation type */}
              <div
                className="text-xs px-2 py-1 rounded mb-3 inline-block"
                style={{ backgroundColor: violationColor[selectedZone.violation_type] || '#374151' }}
              >
                {selectedZone.violation_type.replace(/_/g, ' ')}
              </div>

              <div className="mb-3 space-y-2">
                <div className="flex flex-wrap gap-1.5">
                  {selectedZone.construction_detected && (
                    <span className="text-xs font-bold px-2 py-1 rounded bg-emerald-600 text-white">
                      Vision Verified
                    </span>
                  )}
                  {selectedZone.crane_present && (
                    <span className="text-xs font-bold px-2 py-1 rounded bg-orange-600 text-white">
                      Active Construction
                    </span>
                  )}
                </div>

                <div className="rounded bg-sky-50 border border-slate-200 p-2">
                  <div className="flex justify-between text-xs">
                    <span className="text-slate-500">Vision confidence</span>
                    <span className="font-bold text-slate-900">
                      {formatVisionConfidence(selectedZone.vision_confidence)}
                    </span>
                  </div>
                  {selectedObjects.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-1.5">
                      {selectedObjects.map(obj => (
                        <span
                          key={obj}
                          className="text-xs px-2 py-1 rounded bg-sky-50 text-slate-900"
                        >
                          {visionObjectLabels[obj]}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              <div className="mt-3 rounded bg-sky-50 border border-slate-200 p-3 text-xs space-y-2">
                <div className="flex justify-between text-slate-500">
                  <span>Bhuvan Land Type</span>
                  <span className="font-semibold text-slate-900">
                    {selectedZone.bhuvan_land_type || 'Unverified'}
                  </span>
                </div>
                <div className="flex justify-between text-slate-500">
                  <span>OSM overlays</span>
                  <span className="font-semibold text-slate-900">
                    {selectedZone.osm_flags?.map(flag => flag.replace(/_/g, ' ')).join(', ') || 'None'}
                  </span>
                </div>
                <div className="flex justify-between text-slate-500">
                  <span>Risk boost</span>
                  <span className="font-semibold text-slate-900">
                    {selectedZone.risk_boost_total?.toFixed(1) ?? '0.0'}
                  </span>
                </div>
              </div>
              {selectedZone.legal_explanation && (
                <div className="mt-3 rounded bg-sky-50 border border-slate-200 p-3 text-xs text-slate-700">
                  <p className="font-semibold text-slate-900 mb-1">Legal confidence</p>
                  <p>{selectedZone.legal_explanation}</p>
                </div>
              )}

              {/* Details */}
              <div className="space-y-1.5 text-xs text-slate-500">
                <div className="flex justify-between">
                  <span className="text-slate-500">Area</span>
                  <span>{(selectedZone.area_sqm / 10000).toFixed(2)} hectares</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Coordinates</span>
                  <span>{selectedZone.lat.toFixed(4)}, {selectedZone.lon.toFixed(4)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Zone ID</span>
                  <span>#{selectedZone.id}</span>
                </div>
              </div>

              {/* Action */}
              <div className="mt-3 p-2 bg-sky-50 border border-blue-200 rounded text-xs text-blue-700">
                {selectedZone.action}
              </div>
             {/* Download report button */}

  <a href={`http://localhost:8000/zones/${selectedZone.id}/report`}
  target="_blank"
  rel="noopener noreferrer"
  className="mt-3 w-full block text-center bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold py-2 px-4 rounded transition-colors"
>
  Download Official Report (PDF)
</a>
              {/* Before/After slider */}
<ZoneImages zoneId={selectedZone.id} lat={selectedZone.lat} lon={selectedZone.lon} />
            </div>
          </div>
        )}

        {/* Zone count */}
        <div className="p-4 mt-auto">
          <p className="text-xs text-slate-500">
            Showing {filtered.length} of {zones.length} zones
          </p>
        </div>
      </div>

      {/* Map */}
      <div className="flex-1 relative">
        <MapContainer
          center={[19.42, 72.85]}
          zoom={12}
          className="h-full w-full"
          style={{ background: '#1a1a2e' }}
        >
          <MapInstanceSetter onCreated={setMapInstance} />
          <TileLayer
  url="https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}"
  attribution="© Google"
  maxZoom={21}
/>
          <TileLayer
            url="https://bhuvan-vec1.nrsc.gov.in/bhuvan/wms"
            layers="lulc50k"
            format="image/png"
            transparent={true}
            opacity={0.5}
            attribution="ISRO Bhuvan LULC"
          />
          {filtered.map(zone => (
            <CircleMarker
              key={zone.id}
              center={[zone.lat, zone.lon]}
              radius={severityRadius[zone.severity]}
              pathOptions={{
                color: severityColor[zone.severity],
                fillColor: severityColor[zone.severity],
                fillOpacity: zone.severity === 'CRITICAL' ? 0.9 : 0.6,
                weight: zone.severity === 'CRITICAL' ? 2 : 1
              }}
              eventHandlers={{
                click: () => setSelectedZone(zone)
              }}
            >
              <Popup>
                <div style={{ fontSize: '12px', minWidth: '150px' }}>
                  <strong style={{ color: severityColor[zone.severity] }}>
                    {zone.severity}
                  </strong>
                  <br />
                  {zone.violation_type.replace(/_/g, ' ')}
                  <br />
                  Area: {(zone.area_sqm / 10000).toFixed(2)} ha
                  <br />
                  Score: {zone.risk_score}/100
                </div>
              </Popup>
            </CircleMarker>
          ))}
          {/* Pulsing markers for critical zones */}
          {filtered.filter(z => z.severity === 'CRITICAL').map(z => (
            <PulsingMarker key={`pulse-${z.id}`} lat={z.lat} lng={z.lon} />
          ))}

          {/* Drawn circle preview */}
          {circleCenter && circleRadius != null && (
            <Circle center={circleCenter} radius={circleRadius} pathOptions={{ color: '#3b82f6', fillOpacity: 0.08 }} />
          )}
          {/* drawn polygon preview (if any) */}
          {drawnGeoJSON && (
            <GeoJsonLayer data={drawnGeoJSON} />
          )}
     
          {/* Map instance setter */}
          <MapInstanceSetter onCreated={setMapInstance} />
          {/* Map draw handler: mousedown -> drag -> mouseup */}
          <MapDrawHandler
            drawMode={drawMode}
            onStart={(latlng) => {
              setCircleCenter([latlng.lat, latlng.lng])
              setCircleRadius(0)
            }}
            onMove={(radiusMeters) => {
              setCircleRadius(radiusMeters)
            }}
            onEnd={() => {
              setDrawMode('none')
            }}
            onFinish={(geojson) => {
              // receive polygon GeoJSON from freehand pen
              setDrawnGeoJSON(geojson)
              // exit draw mode
              setDrawMode('none')
            }}
          />
          {/* Leaflet Draw control */}
          <DrawControl
            drawMode={drawMode}
            onDraw={(g)=>{
              setDrawnGeoJSON(g)
              setCircleCenter(null)
              setCircleRadius(null)
              setCircleDrawn(false)
            }}
            onCircleDraw={(center, radius) => {
              setDrawnGeoJSON(null)
              setCircleCenter(center)
              setCircleRadius(radius)
              setCircleDrawn(true)
            }}
          />
        </MapContainer>

        {/* Map overlay — stats */}
        <div className="absolute top-4 right-4 bg-sky-50/90 backdrop-blur rounded-lg p-3 z-[1000] shadow-sm border border-slate-200">
          <p className="text-xs text-slate-500">Active filters</p>
          <p className="text-sm font-bold text-slate-900">{filtered.length} zones visible</p>
        </div>
        {/* Draw controls at bottom */}
        <div className="absolute left-4 bottom-4 z-[1100]">
          <div className="flex gap-2">
            <button
              onClick={() => {
                // toggle pen draw mode; clear previous shapes
                if (drawMode !== 'pen') {
                  setCircleCenter(null)
                  setCircleRadius(null)
                }
                setDrawMode(drawMode === 'pen' ? 'none' : 'pen')
              }}
              className={`px-3 py-2 rounded-md font-medium ${drawMode === 'pen' ? 'bg-blue-600 text-white' : 'bg-slate-200 text-slate-900 hover:bg-slate-300'}`}
            >
              {drawMode === 'pen' ? 'Drawing (pen) — drag to draw' : 'Pen'}
            </button>
            <button
              onClick={() => {
                // reset draw UI
                setCircleCenter(null); setCircleRadius(null); setDrawMode('none')
                setDrawnGeoJSON(null)
                setSelectedZone(null)
                setSeverityFilter('ALL')
                setViolationFilter('ALL')
                // clear any pen-drawn layers
                try {
                  const g = (window as any).drawnLayerGroup
                  if (g && g.clearLayers) g.clearLayers()
                } catch {}

                // reload original zones + summary from backend
                axios.get('http://localhost:8000/zones')
                  .then(res => setZones(res.data.zones))
                  .catch(() => {})
                axios.get('http://localhost:8000/zones/summary')
                  .then(res => setSummary(res.data))
                  .catch(() => {})
              }}
              className="px-3 py-2 rounded-md font-medium bg-slate-200 text-slate-900 hover:bg-slate-300"
            >
              Clear
            </button>
            {circleCenter && circleRadius != null && (
              <div className="flex items-center gap-1">
                <button
                  onClick={() => {
                    setCircleRadius(prev => Math.max(50, (prev || 0) - 50))
                    setCircleDrawn(true)
                  }}
                  className="px-3 py-2 rounded-md font-medium bg-slate-200 text-slate-900 hover:bg-slate-300"
                >
                  −
                </button>
                <span className="px-3 py-2 rounded-md bg-slate-200 text-slate-900 text-xs font-medium">
                  {(circleRadius/1000).toFixed(2)} km
                </span>
                <button
                  onClick={() => {
                    setCircleRadius(prev => (prev || 0) + 50)
                    setCircleDrawn(true)
                  }}
                  className="px-3 py-2 rounded-md font-medium bg-slate-200 text-slate-900 hover:bg-slate-300"
                >
                  +
                </button>
              </div>
            )}
            
 
            <button
  onClick={() => {
  if (!drawnGeoJSON) return
  setScanStatus({ active: true, progress: 'Initializing satellite scan...', jobId: null })
  
  axios.post('http://localhost:8000/zones/query', drawnGeoJSON).then(res => {
    const jobId = res.data.job_id
    if (!jobId) return
    setScanStatus({ active: true, progress: 'Connecting to Google Earth Engine...', jobId })

    const poll = setInterval(() => {
      axios.get(`http://localhost:8000/jobs/${jobId}`).then(r => {
        setScanStatus({ active: true, progress: r.data.progress || 'Processing...', jobId })

        if (r.data.status === 'done' && r.data.result) {
          clearInterval(poll)
          setZones(prev => [...prev, ...r.data.result])
          setScanStatus({ active: false, progress: `Complete — ${r.data.result.length} new zones found`, jobId })
          setTimeout(() => setScanStatus({ active: false, progress: '', jobId: null }), 5000)
        } else if (r.data.status === 'error') {
          clearInterval(poll)
          setScanStatus({ active: false, progress: `Failed: ${r.data.error}`, jobId: null })
        }
      })
    }, 5000)
  }).catch(() => {
    setScanStatus({ active: false, progress: 'Request failed', jobId: null })
  })
}}
  className="px-3 py-2 rounded-md font-medium bg-blue-600 text-white hover:bg-blue-700"
>
  Get Data
</button>
          </div>
          {/* Scan progress overlay */}
{(scanStatus.active || scanStatus.progress) && (
  <div className="absolute bottom-20 left-1/2 -translate-x-1/2 z-[1200] min-w-80">
    <div className={`rounded-xl px-5 py-4 shadow-2xl border ${
      scanStatus.active
        ? 'bg-sky-50/95 border-blue-500/50'
        : scanStatus.progress.startsWith('Complete')
        ? 'bg-sky-50/95 border-green-500/50'
        : 'bg-sky-50/95 border-red-500/50'
    }`}>
      <div className="flex items-center gap-3">
        {scanStatus.active ? (
          <div className="w-4 h-4 rounded-full border-2 border-blue-400 border-t-transparent animate-spin flex-shrink-0" />
        ) : scanStatus.progress.startsWith('Complete') ? (
          <div className="w-4 h-4 rounded-full bg-green-500 flex-shrink-0" />
        ) : (
          <div className="w-4 h-4 rounded-full bg-red-500 flex-shrink-0" />
        )}
        <div>
          <p className={`text-sm font-medium ${
            scanStatus.active ? 'text-blue-600'
            : scanStatus.progress.startsWith('Complete') ? 'text-green-600'
            : 'text-red-600'
          }`}>
            {scanStatus.active ? 'Live Satellite Scan Running' : scanStatus.progress.startsWith('Complete') ? 'Scan Complete' : 'Scan Failed'}
          </p>
          <p className="text-xs text-slate-500 mt-0.5">{scanStatus.progress}</p>
        </div>
      </div>

      {/* Progress steps */}
      {scanStatus.active && (
        <div className="mt-3 space-y-1.5">
          {[
            'Connecting to Google Earth Engine...',
            'Fetching 2019 satellite imagery...',
            'Fetching 2023 satellite imagery...',
            'Running NDBI change detection...',
            'Downloading results from GEE...',
            'Extracting flagged zones...',
          ].map((step, i) => {
            const steps = [
              'Connecting',
              'Fetching 2019',
              'Fetching 2023',
              'Running NDBI',
              'Downloading',
              'Extracting',
            ]
            const currentIdx = steps.findIndex(s => scanStatus.progress.includes(s))
            const done = currentIdx > i
            const active = currentIdx === i

            return (
              <div key={i} className="flex items-center gap-2">
                <div className={`w-2 h-2 rounded-full flex-shrink-0 ${
                  done ? 'bg-green-500'
                  : active ? 'bg-blue-400 animate-pulse'
                  : 'bg-slate-300'
                }`} />
                <p className={`text-xs ${
                  done ? 'text-green-600'
                  : active ? 'text-blue-600'
                  : 'text-slate-500'
                }`}>{step}</p>
              </div>
            )
          })}
        </div>
      )}
    </div>
  </div>
)}
        </div>
      </div>
    </div>
  )
}

  function GeoJsonLayer({ data }: { data: any }) {
    // simple component to render geojson via Leaflet layer
    const map = (window as any).mapInstance as any
    useEffect(() => {
      if (!map) return
      const layer = (window as any).L.geoJSON(data as any, { style: { color: '#3b82f6', weight: 2, fillOpacity: 0.05 } }).addTo(map)
      return () => { map.removeLayer(layer) }
    }, [data])
    return null
  }

  function DrawControl({ drawMode, onDraw }: { drawMode: 'none'|'circle'|'pen'|'rectangle', onDraw: (geojson: any|null) => void }) {
    const map = useMap()
    useEffect(() => {
      ;(window as any).mapInstance = map
      const drawnItems = new (window as any).L.FeatureGroup()
      map.addLayer(drawnItems)

      const drawControl = new (L.Control as any).Draw({
        // Use option objects instead of booleans for nested option groups.
        // Passing `true` previously caused leaflet-draw to attempt to set
        // properties on a boolean (TypeError). Empty objects enable defaults.
        edit: { featureGroup: drawnItems, edit: {}, remove: {} },
        draw: {
          polygon: {},
          polyline: false,
          rectangle: {},
          circle: false,
          marker: false,
          circlemarker: false
        },
        circle: {
          shapeOptions: { color: '#3b82f6', weight: 2, fillOpacity: 0.1 },
          showRadius: true,
          metric: true
        }
      })

      map.on(((window as any).L.Draw.Event).CREATED, function (e: any) {
        const layer = e.layer
        drawnItems.clearLayers()
        drawnItems.addLayer(layer)
        // If user drew a rectangle, trigger backend pipeline for that bbox
        const geojson = layer.toGeoJSON()
        const type = e.layerType || (geojson && geojson.geometry && geojson.geometry.type)
        if (type === 'Rectangle' || type === 'Polygon') {
          // For rectangles created by leaflet-draw, layer.getBounds() is available
          if (layer.getBounds) {
            const b = layer.getBounds()
            const minLat = b.getSouth()
            const minLng = b.getWest()
            const maxLat = b.getNorth()
            const maxLng = b.getEast()
            const bboxDetail = {
              minx: minLng,
              miny: minLat,
              maxx: maxLng,
              maxy: maxLat,
              west: minLng,
              south: minLat,
              east: maxLng,
              north: maxLat
            }
            window.dispatchEvent(new CustomEvent('bbox-drawn', { detail: bboxDetail }))
            // POST bbox to backend to start processing
            axios.post('http://localhost:8000/process_bbox', bboxDetail).then(res => {
              const jobId = res.data.job_id
              const poll = setInterval(() => {
                axios.get(`http://localhost:8000/jobs/${jobId}`).then(r => {
                  if (r.data.status === 'done' && r.data.result) {
                    clearInterval(poll)
                    setZones(r.data.result)
                    axios.get('http://localhost:8000/zones/summary').then(s => setSummary(s.data)).catch(() => {})
                    onDraw(r.data.result)
                  } else if (r.data.status === 'error') {
                    clearInterval(poll)
                    alert('Processing failed: ' + (r.data.error || 'unknown'))
                  }
                }).catch(() => {})
              }, 5000)
            }).catch(err => {
              alert('Failed to start processing: ' + err)
            })
            return
          }
        }
        onDraw(geojson)
      })

      map.on(((window as any).L.Draw.Event).DELETED, function () {
        drawnItems.clearLayers()
        onDraw(null)
      })

      // toggle control (only enable leaflet-draw when explicitly requested)
      if (drawMode === 'rectangle') {
        map.addControl(drawControl)
      }

      return () => {
        try { map.removeControl(drawControl) } catch {}
        map.removeLayer(drawnItems)
      }
    }, [map, drawMode])
    return null
  }

  function MapDrawHandler({ drawMode, onStart, onMove, onEnd, onFinish }:{ drawMode:'none'|'circle'|'pen', onStart:(latlng:{lat:number,lng:number})=>void, onMove:(radius:number)=>void, onEnd:()=>void, onFinish?: (geojson:any)=>void }) {
    const startRef = useRef<{lat:number,lng:number}|null>(null)
    const drawingRef = useRef<{layer?: L.Polyline, latlngs: L.LatLng[]} | null>(null)
    const map = useMap()

    useMapEvents({
      mousedown(e:any) {
        if (drawMode === 'pen') {
          // ensure a dedicated layer group exists for drawn shapes
          if (!(window as any).drawnLayerGroup) {
            try {
              const g = new L.FeatureGroup()
              map.addLayer(g)
              ;(window as any).drawnLayerGroup = g
            } catch {}
          }

          // disable map interactions so drawing doesn't pan/zoom the map
          try { map.dragging.disable() } catch {}
          try { map.doubleClickZoom.disable() } catch {}
          try { map.scrollWheelZoom.disable() } catch {}
          try { map.touchZoom.disable && map.touchZoom.disable() } catch {}

          // start freehand
          drawingRef.current = { latlngs: [e.latlng] }
          const poly = L.polyline([e.latlng], { color: '#3b82f6', weight: 2 })
          try { (window as any).drawnLayerGroup.addLayer(poly) } catch { poly.addTo(map) }
          drawingRef.current.layer = poly
          return
        }
        if (drawMode !== 'circle') return
        startRef.current = e.latlng
        onStart(e.latlng)
      },
      mousemove(e:any) {
        if (drawMode === 'pen' && drawingRef.current) {
          drawingRef.current.latlngs.push(e.latlng)
          drawingRef.current.layer!.setLatLngs(drawingRef.current.latlngs)
          return
        }
        if (drawMode !== 'circle' || !startRef.current) return
        const a = startRef.current
        const b = e.latlng
        const toRad = (deg: number) => deg * Math.PI / 180
        const R = 6371000
        const dLat = toRad(b.lat - a.lat)
        const dLon = toRad(b.lng - a.lng)
        const aa = Math.sin(dLat/2) * Math.sin(dLat/2) + Math.cos(toRad(a.lat)) * Math.cos(toRad(b.lat)) * Math.sin(dLon/2) * Math.sin(dLon/2)
        const c = 2 * Math.atan2(Math.sqrt(aa), Math.sqrt(1-aa))
        const dist = R * c
        onMove(dist)
      },
      mouseup(_e:any) {
        if (drawMode === 'pen' && drawingRef.current) {
          // finalize polygon (close ring)
          const latlngs = drawingRef.current.latlngs
          // remove small or accidental strokes
          if (latlngs.length > 2) {
            const poly = L.polygon(latlngs, { color: '#3b82f6', weight: 2, fillOpacity: 0.05 })
            // replace the temporary polyline with polygon
            drawingRef.current.layer!.remove()
            try { (window as any).drawnLayerGroup.addLayer(poly) } catch { poly.addTo(map) }
            const geo = poly.toGeoJSON()
            if (onFinish) onFinish(geo)
          } else {
            // not enough points, clean up
            drawingRef.current.layer!.remove()
          }
          drawingRef.current = null
          // re-enable map interactions
          try { map.dragging.enable() } catch {}
          try { map.doubleClickZoom.enable() } catch {}
          try { map.scrollWheelZoom.enable() } catch {}
          try { map.touchZoom.enable && map.touchZoom.enable() } catch {}
          return
        }
        if (drawMode !== 'circle' || !startRef.current) return
        // final move already reported; clear start and finish
        startRef.current = null
        onEnd()
      }
    })
    return null
  }

  function MapInstanceSetter({ onCreated }: { onCreated: (map: any) => void }) {
    const map = useMap()
    useEffect(() => {
      onCreated(map)
    }, [map, onCreated])
    return null
  }

  function PulsingMarker({ lat, lng }: { lat: number, lng: number }) {
    const map = useMap()
    useEffect(() => {
      const html = `<div class="pulse-container"><div class="pulse-ring"></div><div class="pulse-dot"></div></div>`
      const icon = L.divIcon({ className: 'pulse-icon', html, iconSize: [24,24], iconAnchor: [12,12] })
      const m = L.marker([lat, lng], { icon, interactive: false })
      m.addTo(map)
      return () => { try { map.removeLayer(m) } catch {} }
    }, [lat, lng, map])
    return null
  }
