import { useState, useEffect } from 'react'
import { MapContainer, TileLayer, CircleMarker, Popup } from 'react-leaflet'
import axios from 'axios'
import 'leaflet/dist/leaflet.css'

interface Zone {
  id: number
  lat: number
  lon: number
  area_sqm: number
  severity: string
  risk_score: number
  action: string
  violation_type: string
}

interface Summary {
  total: number
  severity_breakdown: {
    CRITICAL: number
    HIGH: number
    MEDIUM: number
    LOW: number
  }
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
import { useRef } from 'react'

function ImageSlider({ beforeUrl, afterUrl }: { beforeUrl: string, afterUrl: string }) {
  const [sliderPos, setSliderPos] = useState(50)
  const containerRef = useRef<HTMLDivElement>(null)

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!containerRef.current) return
    const rect = containerRef.current.getBoundingClientRect()
    const x = ((e.clientX - rect.left) / rect.width) * 100
    setSliderPos(Math.max(0, Math.min(100, x)))
  }

  return (
    <div
      ref={containerRef}
      className="relative w-full h-48 overflow-hidden rounded-lg cursor-col-resize select-none"
      onMouseMove={handleMouseMove}
    >
      {/* After image (bottom) */}
      <img
        src={afterUrl}
        alt="After 2023"
        className="absolute inset-0 w-full h-full object-cover"
      />

      {/* Before image (top, clipped) */}
      <div
        className="absolute inset-0 overflow-hidden"
        style={{ width: `${sliderPos}%` }}
      >
        <img
          src={beforeUrl}
          alt="Before 2019"
          className="absolute inset-0 h-full object-cover"
          style={{ width: `${10000 / sliderPos}%`, maxWidth: 'none' }}
        />
      </div>

      {/* Slider line */}
      <div
        className="absolute top-0 bottom-0 w-0.5 bg-white z-10"
        style={{ left: `${sliderPos}%` }}
      >
        <div className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-8 h-8 bg-white rounded-full flex items-center justify-center shadow-lg">
          <span className="text-gray-800 text-xs font-bold">◀▶</span>
        </div>
      </div>

      {/* Labels */}
      <div className="absolute bottom-2 left-2 bg-black/60 text-white text-xs px-2 py-0.5 rounded z-10">
        2019
      </div>
      <div className="absolute bottom-2 right-2 bg-black/60 text-white text-xs px-2 py-0.5 rounded z-10">
        2023
      </div>
    </div>
  )
}
function ZoneImages({ zoneId }: { zoneId: number }) {
  const [images, setImages] = useState<{
    has_images: boolean
    before_url: string | null
    after_url: string | null
  } | null>(null)

  useEffect(() => {
    axios.get(`http://localhost:8000/zones/${zoneId}/images`)
      .then(res => setImages(res.data))
  }, [zoneId])

  if (!images || !images.has_images) {
    return (
      <div className="mt-3 p-2 bg-gray-700/50 rounded text-xs text-gray-400 text-center">
        Satellite images available for Critical zones only
      </div>
    )
  }

  return (
    <div className="mt-3">
      <p className="text-xs text-gray-500 mb-2">SATELLITE EVIDENCE — drag to compare</p>
      <ImageSlider
        beforeUrl={images.before_url!}
        afterUrl={images.after_url!}
      />
    </div>
  )
}
export default function App() {
  const [zones, setZones] = useState<Zone[]>([])
  const [summary, setSummary] = useState<Summary | null>(null)
  const [selectedZone, setSelectedZone] = useState<Zone | null>(null)
  const [severityFilter, setSeverityFilter] = useState<string>('ALL')
  const [violationFilter, setViolationFilter] = useState<string>('ALL')

  useEffect(() => {
    axios.get('http://localhost:8000/zones').then(res => setZones(res.data.zones))
    axios.get('http://localhost:8000/zones/summary').then(res => setSummary(res.data))
  }, [])

  const filtered = zones.filter(z => {
    const sev = severityFilter === 'ALL' || z.severity === severityFilter
    const vio = violationFilter === 'ALL' || z.violation_type === violationFilter
    return sev && vio
  })

  return (
    <div className="flex h-screen bg-gray-950 text-white overflow-hidden">

      {/* Sidebar */}
      <div className="w-96 flex-shrink-0 bg-gray-900 border-r border-gray-800 flex flex-col overflow-y-auto">

        {/* Header */}
        <div className="p-5 border-b border-gray-800">
          <div className="flex items-center gap-2 mb-1">
            <div className="w-2 h-2 rounded-full bg-red-500 animate-pulse"/>
            <h1 className="text-lg font-bold text-white">AutoSentinel</h1>
          </div>
          <p className="text-xs text-gray-400">Unauthorized Construction Detection System</p>
          {summary && (
            <p className="text-xs text-gray-500 mt-1">
              {summary.area} · {summary.period}
            </p>
          )}
        </div>

        {/* Summary cards */}
        {summary && (
          <div className="p-4 border-b border-gray-800">
            <p className="text-xs text-gray-500 mb-3 font-medium tracking-wider">DETECTION SUMMARY</p>
            <div className="grid grid-cols-2 gap-2">
              {Object.entries(summary.severity_breakdown).map(([level, count]) => (
                <div
                  key={level}
                  onClick={() => setSeverityFilter(severityFilter === level ? 'ALL' : level)}
                  className="bg-gray-800 rounded-lg p-3 cursor-pointer hover:bg-gray-700 transition-colors"
                  style={{ borderLeft: `3px solid ${severityColor[level]}` }}
                >
                  <div className="text-2xl font-bold" style={{ color: severityColor[level] }}>
                    {count}
                  </div>
                  <div className="text-xs text-gray-400 mt-0.5">{level}</div>
                </div>
              ))}
            </div>
            <div className="mt-2 bg-gray-800 rounded-lg p-3">
              <div className="text-2xl font-bold text-white">{summary.total}</div>
              <div className="text-xs text-gray-400">Total Flagged Zones</div>
            </div>
          </div>
        )}

        {/* Severity filter */}
        <div className="p-4 border-b border-gray-800">
          <p className="text-xs text-gray-500 mb-2 font-medium tracking-wider">FILTER BY SEVERITY</p>
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
        <div className="p-4 border-b border-gray-800">
          <p className="text-xs text-gray-500 mb-2 font-medium tracking-wider">FILTER BY VIOLATION</p>
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

        {/* Selected zone detail */}
        {selectedZone && (
          <div className="p-4 border-b border-gray-800">
            <p className="text-xs text-gray-500 mb-2 font-medium tracking-wider">SELECTED ZONE</p>
            <div
              className="rounded-lg p-4 bg-gray-800"
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

              {/* Details */}
              <div className="space-y-1.5 text-xs text-gray-300">
                <div className="flex justify-between">
                  <span className="text-gray-500">Area</span>
                  <span>{(selectedZone.area_sqm / 10000).toFixed(2)} hectares</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Coordinates</span>
                  <span>{selectedZone.lat.toFixed(4)}, {selectedZone.lon.toFixed(4)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-500">Zone ID</span>
                  <span>#{selectedZone.id}</span>
                </div>
              </div>

              {/* Action */}
              <div className="mt-3 p-2 bg-yellow-900/30 border border-yellow-700/50 rounded text-xs text-yellow-300">
                {selectedZone.action}
              </div>
             {/* Download report button */}

  <a href={`http://localhost:8000/zones/${selectedZone.id}/report`}
  target="_blank"
  rel="noopener noreferrer"
  className="mt-3 w-full block text-center bg-red-600 hover:bg-red-700 text-white text-xs font-bold py-2 px-4 rounded transition-colors"
>
  Download Official Report (PDF)
</a>
              {/* Before/After slider */}
<ZoneImages zoneId={selectedZone.id} />
            </div>
          </div>
        )}

        {/* Zone count */}
        <div className="p-4 mt-auto">
          <p className="text-xs text-gray-600">
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
          <TileLayer
            url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
            attribution="© OpenStreetMap © CARTO"
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
        </MapContainer>

        {/* Map overlay — stats */}
        <div className="absolute top-4 right-4 bg-gray-900/90 backdrop-blur rounded-lg p-3 z-[1000]">
          <p className="text-xs text-gray-400">Active filters</p>
          <p className="text-sm font-bold text-white">{filtered.length} zones visible</p>
        </div>
      </div>
    </div>
  )
}