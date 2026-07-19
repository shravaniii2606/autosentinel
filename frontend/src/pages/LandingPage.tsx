const capabilities = [
  {
    number: '01',
    title: 'Satellite change detection',
    text: 'Compare Sentinel-2 imagery year over year using NDBI change detection, so new built surfaces stand out from the surrounding terrain.',
  },
  {
    number: '02',
    title: 'Legal risk cross-reference',
    text: 'Match construction alerts against forest, agricultural and protected-land categories to focus inspection resources where the legal exposure is highest.',
  },
  {
    number: '03',
    title: 'Building footprint verification',
    text: 'Cross-check flagged areas against Microsoft global building footprints to help distinguish a real structure from a transient image signal.',
  },
  {
    number: '04',
    title: 'Voice-enabled AI assistant',
    text: 'Ask why a zone is high risk, review scan evidence in plain language, and retain context from earlier investigations.',
  },
]

const workflow = [
  ['01', 'Draw an area on the map', 'Outline a ward, parcel or suspected site in the live map.'],
  ['02', 'Satellite scan runs', 'AutoSentinel compares recent Sentinel-2 imagery against the prior year.'],
  ['03', 'Zones are prioritised', 'New construction is scored by severity and land-use risk.'],
  ['04', 'Investigate with evidence', 'Download a PDF report or question the AI assistant about the scan.'],
]

export default function LandingPage() {
  return (
    <main className="min-h-screen bg-[#07100f] text-slate-100 selection:bg-amber-400 selection:text-slate-950">
      <header className="border-b border-white/10 bg-[#07100f]/95">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-5 py-4 sm:px-8">
          <a href="/" className="flex items-center gap-3" aria-label="AutoSentinel home">
            <span className="grid h-8 w-8 place-items-center border border-amber-400/80 bg-amber-400/10">
              <span className="h-3 w-3 border border-amber-300 bg-amber-400" />
            </span>
            <span className="text-sm font-semibold tracking-[0.18em] text-white">AUTOSENTINEL</span>
          </a>
          <a href="/dashboard" className="border border-amber-400 bg-amber-400 px-4 py-2 text-xs font-bold tracking-[0.12em] text-slate-950 transition hover:bg-amber-300">
            OPEN DASHBOARD
          </a>
        </div>
      </header>

      <section className="relative overflow-hidden border-b border-white/10">
        <div className="pointer-events-none absolute inset-0 opacity-30 [background-image:linear-gradient(rgba(148,163,184,.12)_1px,transparent_1px),linear-gradient(90deg,rgba(148,163,184,.12)_1px,transparent_1px)] [background-size:48px_48px]" />
        <div className="relative mx-auto grid max-w-7xl gap-12 px-5 py-18 sm:px-8 lg:grid-cols-[1.02fr_.98fr] lg:items-center lg:py-28">
          <div>
            <p className="mb-5 font-mono text-xs tracking-[0.18em] text-amber-300">SATELLITE INTELLIGENCE FOR LAND AUTHORITIES</p>
            <h1 className="max-w-3xl text-4xl font-semibold tracking-tight text-white sm:text-5xl lg:text-6xl">
              Find unauthorised construction before it becomes irreversible.
            </h1>
            <p className="mt-6 max-w-2xl text-base leading-7 text-slate-300 sm:text-lg">
              AutoSentinel compares Sentinel-2 imagery year over year to surface new construction, rank its risk, and give municipal officers evidence they can act on.
            </p>
            <div className="mt-9 flex flex-col gap-3 sm:flex-row">
              <a href="/dashboard" className="inline-flex justify-center bg-amber-400 px-5 py-3 text-sm font-bold text-slate-950 transition hover:bg-amber-300">SCAN AN AREA</a>
            </div>
            <div className="mt-10 flex flex-wrap gap-x-7 gap-y-3 font-mono text-xs text-slate-400">
              <span>INPUT: SENTINEL-2</span><span>METHOD: NDBI CHANGE</span><span>OUTPUT: ACTIONABLE ZONES</span>
            </div>
          </div>

          <div className="border border-slate-600 bg-[#0b1716] p-3 shadow-2xl shadow-black/30">
            <div className="mb-3 flex items-center justify-between border-b border-white/10 pb-3 font-mono text-[10px] tracking-wider text-slate-400">
              <span>COMPARISON / ILLUSTRATIVE PLACEHOLDER</span><span>DELTA: + BUILT SURFACE</span>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <SatellitePanel label="BASELINE / PRIOR YEAR" variant="before" />
              <SatellitePanel label="CURRENT / THIS YEAR" variant="after" />
            </div>
            <div className="mt-3 flex items-center justify-between border-t border-white/10 pt-3 font-mono text-[10px] text-slate-400">
              <span>AREA: [PLACEHOLDER]</span><span className="text-amber-300">HIGH SEVERITY SIGNAL</span>
            </div>
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-5 py-20 sm:px-8">
        <p className="font-mono text-xs tracking-[0.16em] text-amber-300">WORKFLOW</p>
        <h2 className="mt-3 max-w-2xl text-3xl font-semibold text-white">From a drawn boundary to an inspection-ready record.</h2>
        <div className="mt-11 grid gap-5 md:grid-cols-2 lg:grid-cols-4">
          {workflow.map(([number, title, text], index) => (
            <article key={number} className="relative border border-white/10 bg-[#0a1514] p-6">
              <span className="font-mono text-xs text-amber-300">{number}</span>
              <div className="my-5 h-px bg-slate-700"><div className="h-px bg-amber-400" style={{ width: `${(index + 1) * 25}%` }} /></div>
              <h3 className="text-lg font-semibold text-white">{title}</h3>
              <p className="mt-3 text-sm leading-6 text-slate-400">{text}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="border-y border-white/10 bg-[#0a1514]">
        <div className="mx-auto max-w-7xl px-5 py-20 sm:px-8">
          <div className="flex flex-col justify-between gap-5 md:flex-row md:items-end">
            <div>
              <p className="font-mono text-xs tracking-[0.16em] text-amber-300">CAPABILITIES</p>
              <h2 className="mt-3 text-3xl font-semibold text-white">Evidence built for the way enforcement teams work.</h2>
            </div>
            <p className="max-w-xl text-sm leading-6 text-slate-400">Each alert brings image change, land-use context, verification signals and a clear path to documentation into one investigation workflow.</p>
          </div>
          <div className="mt-10 grid gap-4 md:grid-cols-2">
            {capabilities.map((capability) => <CapabilityCard key={capability.number} {...capability} />)}
          </div>
        </div>
      </section>

      <section className="mx-auto max-w-7xl px-5 py-20 sm:px-8">
        <div className="grid gap-10 lg:grid-cols-[.8fr_1.2fr] lg:items-center">
          <div>
            <p className="font-mono text-xs tracking-[0.16em] text-amber-300">LIVE MAP WORKSPACE</p>
            <h2 className="mt-3 text-3xl font-semibold text-white">Draw, scan, prioritise.</h2>
            <p className="mt-5 text-base leading-7 text-slate-300">Start from any area of interest. Browse known violation zones or draw a new boundary and return to a ranked list of construction signals with severity, land-use and verification context.</p>
            <a href="/dashboard" className="mt-8 inline-flex border border-amber-400 px-5 py-3 text-sm font-bold text-amber-300 transition hover:bg-amber-400 hover:text-slate-950">GO TO LIVE DASHBOARD</a>
          </div>
          <MapPreview />
        </div>
      </section>

      <footer className="border-t border-white/10 bg-[#050a0a]">
        <div className="mx-auto flex max-w-7xl flex-col gap-8 px-5 py-12 sm:px-8 md:flex-row md:items-center md:justify-between">
          <div>
            <p className="font-mono text-xs tracking-[0.16em] text-amber-300">READY FOR FIELD REVIEW</p>
            <h2 className="mt-3 text-2xl font-semibold text-white">Bring satellite evidence into your enforcement workflow.</h2>
          </div>
        </div>
        <div className="border-t border-white/10 py-5 text-center font-mono text-[10px] tracking-wider text-slate-500">AUTOSENTINEL / CONSTRUCTION INTELLIGENCE</div>
      </footer>
    </main>
  )
}

function SatellitePanel({ label, variant }: { label: string; variant: 'before' | 'after' }) {
  const isAfter = variant === 'after'
  return <div className="overflow-hidden border border-white/10 bg-[#172925]">
    <div className={`relative aspect-[4/5] overflow-hidden ${isAfter ? 'bg-[#27342d]' : 'bg-[#1b332c]'}`}>
      <div className="absolute inset-0 opacity-60 [background-image:linear-gradient(115deg,transparent_20%,rgba(125,157,87,.65)_20%,rgba(125,157,87,.65)_38%,transparent_38%,transparent_58%,rgba(84,111,71,.7)_58%,rgba(84,111,71,.7)_76%,transparent_76%)]" />
      <div className="absolute -left-8 top-[45%] h-12 w-[125%] rotate-[-12deg] border-y border-[#9a835a]/70 bg-[#83734c]/50" />
      <div className="absolute inset-0 opacity-25 [background-image:linear-gradient(rgba(255,255,255,.3)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,.3)_1px,transparent_1px)] [background-size:18px_18px]" />
      {isAfter && <><span className="absolute left-[39%] top-[25%] h-[23%] w-[29%] border-2 border-amber-300 bg-slate-300/70" /><span className="absolute left-[43%] top-[29%] h-[8%] w-[19%] bg-slate-600/80" /><span className="absolute left-[31%] top-[18%] border-x-5 border-b-7 border-x-transparent border-b-amber-400" /></>}
    </div>
    <p className="border-t border-white/10 px-3 py-2 font-mono text-[9px] tracking-wider text-slate-400">{label}</p>
  </div>
}

function CapabilityCard({ number, title, text }: { number: string; title: string; text: string }) {
  return <article className="border border-white/10 bg-[#07100f] p-6 transition hover:border-amber-400/60"><p className="font-mono text-xs text-amber-300">{number}</p><h3 className="mt-8 text-xl font-semibold text-white">{title}</h3><p className="mt-3 max-w-xl text-sm leading-6 text-slate-400">{text}</p></article>
}

function MapPreview() {
  return <div className="relative min-h-90 overflow-hidden border border-slate-600 bg-[#12231f] p-5">
    <div className="absolute inset-0 opacity-35 [background-image:linear-gradient(31deg,transparent_47%,#8a7a59_48%,#8a7a59_50%,transparent_51%),linear-gradient(111deg,transparent_40%,#557061_41%,#557061_43%,transparent_44%),linear-gradient(rgba(148,163,184,.2)_1px,transparent_1px),linear-gradient(90deg,rgba(148,163,184,.2)_1px,transparent_1px)] [background-size:auto,auto,44px_44px,44px_44px]" />
    <div className="relative flex items-center justify-between font-mono text-[10px] text-slate-300"><span>MAP / STATIC PREVIEW</span><span>ZOOM 14</span></div>
    <div className="absolute left-[20%] top-[25%] h-29 w-45 rotate-[-9deg] border-2 border-amber-300 bg-amber-400/10" />
    <div className="absolute left-[29%] top-[39%] grid h-7 w-7 place-items-center rounded-full border border-amber-200 bg-amber-400 text-[10px] font-bold text-slate-950">H</div>
    <div className="absolute bottom-5 left-5 right-5 flex flex-wrap items-center justify-between gap-3 border border-white/10 bg-[#07100f]/90 px-4 py-3 font-mono text-[10px]"><span className="text-slate-400">[PLACEHOLDER] SELECTED AREA</span><span className="text-amber-300">1 HIGH-RISK ZONE</span></div>
  </div>
}
