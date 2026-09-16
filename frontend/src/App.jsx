import { useEffect, useMemo, useState } from "react"
import { Navigate, NavLink, Route, Routes, useNavigate, useParams } from "react-router-dom"
import {
  Activity, ArrowRight, Box, CheckCircle2, Clock3, Compass, LayoutDashboard,
  LogIn, MapPin, Package, RefreshCw, Search, Truck, UserRound, Users, XCircle,
  Zap, Menu, Plus, Navigation, ShieldCheck
} from "lucide-react"

const API = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000"

async function request(path, options = {}) {
  const token = localStorage.getItem("routesync_token")
  const headers = { "Content-Type": "application/json", ...(options.headers || {}) }
  if (token) headers.Authorization = `Bearer ${token}`
  const response = await fetch(`${API}${path}`, { ...options, headers })
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(data.detail || "Request failed")
  return data
}

const statusLabel = s => s.replaceAll("_", " ").replace(/\b\w/g, c => c.toUpperCase())

function Shell({ user, onLogout, children }) {
  const [open, setOpen] = useState(false)
  const links = [
    ["/", "Dashboard", LayoutDashboard],
    ["/deliveries", "Deliveries", Package],
    ["/drivers", "Drivers", Truck],
    ["/assignments", "Assignments", Activity]
  ]
  if (user.role === "customer") links.splice(2, 1)
  return (
    <div className="app-shell">
      <aside className={open ? "sidebar open" : "sidebar"}>
        <div className="brand"><div className="brand-mark"><Navigation size={20}/></div><div><strong>RouteSync</strong><span>Delivery Operations</span></div></div>
        <nav>{links.map(([to, label, Icon]) => <NavLink key={to} to={to} end={to === "/"} onClick={() => setOpen(false)}><Icon size={18}/>{label}</NavLink>)}</nav>
        <div className="side-card"><Zap size={18}/><div><b>Dispatch Engine</b><span>Distance + workload based recommendations</span></div></div>
        <button className="logout" onClick={onLogout}><LogIn size={18}/> Sign out</button>
      </aside>
      <main className="main">
        <header className="topbar"><button className="mobile-menu" onClick={() => setOpen(!open)}><Menu/></button><div><span className="eyebrow">OPERATIONS CENTER</span><h1>RouteSync</h1></div><div className="user-chip"><div className="avatar">{user.name[0]}</div><div><b>{user.name}</b><span>{user.role}</span></div></div></header>
        {children}
      </main>
    </div>
  )
}

function Login({ onLogin }) {
  const [email, setEmail] = useState("admin@routesync.com")
  const [password, setPassword] = useState("Admin@123")
  const [error, setError] = useState("")
  const [loading, setLoading] = useState(false)
  async function submit(e) {
    e.preventDefault()
    setError("")
    setLoading(true)
    try {
      const token = await request("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) })
      localStorage.setItem("routesync_token", token.access_token)
      onLogin()
    } catch (err) {
      setError(err.message)
    } finally { setLoading(false) }
  }
  return <div className="login-page">
    <div className="login-visual"><div className="login-glow"/><div className="brand large"><div className="brand-mark"><Navigation/></div><div><strong>RouteSync</strong><span>Delivery Operations Platform</span></div></div><h2>From dispatch to doorstep.</h2><p>Manage deliveries, coordinate drivers, monitor status transitions and optimize routes from one operational workspace.</p><div className="flow"><span>Order</span><ArrowRight/><span>Dispatch</span><ArrowRight/><span>Track</span><ArrowRight/><span>Deliver</span></div></div>
    <form className="login-card" onSubmit={submit}><div className="login-icon"><ShieldCheck/></div><h2>Welcome back</h2><p>Sign in to RouteSync</p>{error && <div className="error">{error}</div>}<label>Email<input value={email} onChange={e => setEmail(e.target.value)} type="email"/></label><label>Password<input value={password} onChange={e => setPassword(e.target.value)} type="password"/></label><button className="primary wide" disabled={loading}>{loading ? "Signing in..." : "Sign in"} <ArrowRight size={18}/></button><div className="demo-box"><b>Demo accounts</b><span>Admin: admin@routesync.com / Admin@123</span><span>Driver: driver@routesync.com / Driver@123</span><span>Customer: customer@routesync.com / Customer@123</span></div></form>
  </div>
}

function Stat({ icon: Icon, label, value, detail }) {
  return <div className="stat-card"><div className="stat-icon"><Icon size={19}/></div><span>{label}</span><strong>{value}</strong><small>{detail}</small></div>
}

function Dashboard({ user }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState("")
  async function load() { try { setData(await request("/dashboard/summary")); setError("") } catch (e) { setError(e.message) } }
  useEffect(() => { load() }, [])
  const statuses = data?.statuses || {}
  return <Page title="Operations dashboard" subtitle="Monitor delivery activity, driver availability and fulfillment progress." action={<button className="secondary" onClick={load}><RefreshCw size={16}/> Refresh</button>}>
    {error && <div className="error">{error}</div>}
    <div className="stats-grid">
      <Stat icon={Truck} label="Total drivers" value={data?.total_drivers ?? "—"} detail={`${data?.online_drivers ?? 0} currently online`}/>
      <Stat icon={Package} label="Total deliveries" value={data?.total_deliveries ?? "—"} detail={`${data?.active_deliveries ?? 0} active`}/>
      <Stat icon={Activity} label="Assignments" value={data?.assignments ?? "—"} detail="Recorded in system"/>
      <Stat icon={CheckCircle2} label="Completed" value={data?.completed_deliveries ?? "—"} detail="Delivered successfully"/>
    </div>
    <div className="grid-two">
      <section className="panel"><div className="panel-head"><div><span className="eyebrow">LIFECYCLE</span><h3>Delivery pipeline</h3></div><Compass size={20}/></div><div className="pipeline">{Object.entries(statuses).map(([key, value]) => <div className="pipeline-row" key={key}><span>{statusLabel(key)}</span><div className="bar"><i style={{width: `${data?.total_deliveries ? Math.max(4, value / data.total_deliveries * 100) : 0}%`}}/></div><b>{value}</b></div>)}</div></section>
      <section className="panel"><div className="panel-head"><div><span className="eyebrow">WORKFLOW</span><h3>How RouteSync works</h3></div><Zap size={20}/></div><div className="workflow"><div><span>01</span><b>Create delivery</b><small>Capture pickup, drop-off, package and priority.</small></div><div><span>02</span><b>Dispatch driver</b><small>Compare distance and active workload.</small></div><div><span>03</span><b>Track lifecycle</b><small>Move the order from assignment to delivery.</small></div></div></section>
    </div>
  </Page>
}

function Page({ title, subtitle, action, children }) {
  return <section className="page"><div className="page-head"><div><span className="eyebrow">ROUTESYNC</span><h2>{title}</h2><p>{subtitle}</p></div>{action}</div>{children}</section>
}

function Deliveries({ user }) {
  const [items, setItems] = useState([])
  const [search, setSearch] = useState("")
  const [status, setStatus] = useState("")
  const [showCreate, setShowCreate] = useState(false)
  const [loading, setLoading] = useState(false)
  async function load() { setLoading(true); try { setItems(await request(`/deliveries?search=${encodeURIComponent(search)}${status ? `&status=${status}` : ""}`)) } finally { setLoading(false) } }
  useEffect(() => { load() }, [status])
  return <Page title={user.role === "customer" ? "My deliveries" : "Delivery operations"} subtitle="Create, search and monitor delivery orders through their full lifecycle." action={user.role !== "driver" && <button className="primary" onClick={() => setShowCreate(true)}><Plus size={17}/> New delivery</button>}>
    <div className="toolbar"><div className="search"><Search size={17}/><input placeholder="Search pickup, drop-off or package..." value={search} onChange={e => setSearch(e.target.value)} onKeyDown={e => e.key === "Enter" && load()}/></div><select value={status} onChange={e => setStatus(e.target.value)}><option value="">All statuses</option>{["pending","assigned","accepted","pickup_started","picked_up","in_transit","delivered"].map(s => <option key={s} value={s}>{statusLabel(s)}</option>)}</select><button className="secondary" onClick={load}><RefreshCw size={16}/>{loading ? "Loading" : "Refresh"}</button></div>
    <div className="table-wrap"><table><thead><tr><th>ID</th><th>Route</th><th>Package</th><th>Priority</th><th>Status</th><th></th></tr></thead><tbody>{items.map(d => <tr key={d.id}><td>#{d.id}</td><td><b>{d.pickup_address}</b><small className="muted">to {d.dropoff_address}</small></td><td>{d.package_description}<small className="muted">{d.package_weight} kg</small></td><td><span className={`badge ${d.priority}`}>{d.priority}</span></td><td><span className={`badge ${d.status}`}>{statusLabel(d.status)}</span></td><td><NavLink className="icon-link" to={`/deliveries/${d.id}`}><ArrowRight size={17}/></NavLink></td></tr>)}</tbody></table>{!items.length && <div className="empty">No deliveries found.</div>}</div>
    {showCreate && <CreateDelivery onClose={() => setShowCreate(false)} onCreated={load}/>}
  </Page>
}

function CreateDelivery({ onClose, onCreated }) {
  const [form, setForm] = useState({ pickup_address:"Andheri East, Mumbai", pickup_latitude:19.1197, pickup_longitude:72.8468, dropoff_address:"Bandra West, Mumbai", dropoff_latitude:19.0607, dropoff_longitude:72.8362, package_description:"Documents", package_weight:1, priority:"normal" })
  const [error, setError] = useState("")
  const update = (k, v) => setForm(x => ({...x, [k]: v}))
  async function submit(e) { e.preventDefault(); try { await request("/deliveries",{method:"POST",body:JSON.stringify({...form,pickup_latitude:Number(form.pickup_latitude),pickup_longitude:Number(form.pickup_longitude),dropoff_latitude:Number(form.dropoff_latitude),dropoff_longitude:Number(form.dropoff_longitude),package_weight:Number(form.package_weight)})}); onCreated(); onClose() } catch(e) { setError(e.message) } }
  return <div className="modal-backdrop"><form className="modal" onSubmit={submit}><div className="modal-head"><div><span className="eyebrow">NEW ORDER</span><h3>Create delivery</h3></div><button type="button" className="icon-button" onClick={onClose}><XCircle/></button></div>{error && <div className="error">{error}</div>}<div className="form-grid"><label>Pickup address<input value={form.pickup_address} onChange={e=>update("pickup_address",e.target.value)}/></label><label>Drop-off address<input value={form.dropoff_address} onChange={e=>update("dropoff_address",e.target.value)}/></label><label>Pickup latitude<input type="number" step="any" value={form.pickup_latitude} onChange={e=>update("pickup_latitude",e.target.value)}/></label><label>Pickup longitude<input type="number" step="any" value={form.pickup_longitude} onChange={e=>update("pickup_longitude",e.target.value)}/></label><label>Drop-off latitude<input type="number" step="any" value={form.dropoff_latitude} onChange={e=>update("dropoff_latitude",e.target.value)}/></label><label>Drop-off longitude<input type="number" step="any" value={form.dropoff_longitude} onChange={e=>update("dropoff_longitude",e.target.value)}/></label><label>Package description<input value={form.package_description} onChange={e=>update("package_description",e.target.value)}/></label><label>Weight (kg)<input type="number" step="0.1" value={form.package_weight} onChange={e=>update("package_weight",e.target.value)}/></label><label>Priority<select value={form.priority} onChange={e=>update("priority",e.target.value)}><option>normal</option><option>high</option><option>urgent</option></select></label></div><div className="modal-actions"><button type="button" className="secondary" onClick={onClose}>Cancel</button><button className="primary">Create delivery</button></div></form></div>
}

function Drivers() {
  const [items, setItems] = useState([])
  const [search, setSearch] = useState("")
  async function load() { setItems(await request(`/drivers?search=${encodeURIComponent(search)}`)) }
  useEffect(() => { load() }, [])
  return <Page title="Driver fleet" subtitle="Monitor driver availability, vehicles and current coordinates." action={<button className="secondary" onClick={load}><RefreshCw size={16}/> Refresh</button>}><div className="toolbar"><div className="search"><Search size={17}/><input placeholder="Search driver, vehicle or status..." value={search} onChange={e=>setSearch(e.target.value)} onKeyDown={e=>e.key==="Enter"&&load()}/></div></div><div className="driver-grid">{items.map(d=><div className="driver-card" key={d.id}><div className="driver-top"><div className="avatar large-avatar">{d.name[0]}</div><div><h3>{d.name}</h3><span>{d.email}</span></div><span className={`dot ${d.status}`}/></div><div className="driver-route"><Truck size={17}/><div><b>{d.vehicle_type}</b><span>{d.vehicle_number}</span></div></div><div className="driver-location"><MapPin size={16}/><span>{d.current_latitude.toFixed(4)}, {d.current_longitude.toFixed(4)}</span></div><div className="driver-footer"><span className={`badge ${d.status}`}>{statusLabel(d.status)}</span><small>Driver #{d.id}</small></div></div>)}</div></Page>
}

function Assignments() {
  const [items, setItems] = useState([])
  const [drivers, setDrivers] = useState([])
  const [deliveries, setDeliveries] = useState([])
  const [form, setForm] = useState({driver_id:"",delivery_id:""})
  const [message, setMessage] = useState("")
  async function load() { const [a,d,ds]=await Promise.all([request("/assignments"),request("/drivers"),request("/deliveries?status=pending")]); setItems(a); setDrivers(d.filter(x=>x.status==="online")); setDeliveries(ds) }
  useEffect(()=>{load()},[])
  async function assign(e) { e.preventDefault(); setMessage(""); try { await request("/assignments",{method:"POST",body:JSON.stringify({driver_id:Number(form.driver_id),delivery_id:Number(form.delivery_id)})}); setForm({driver_id:"",delivery_id:""}); setMessage("Driver assigned successfully."); load() } catch(e){setMessage(e.message)}}
  return <Page title="Dispatch center" subtitle="Assign available drivers and review the assignment lifecycle." action={<button className="secondary" onClick={load}><RefreshCw size={16}/> Refresh</button>}><div className="dispatch-grid"><form className="panel dispatch-form" onSubmit={assign}><div className="panel-head"><div><span className="eyebrow">MANUAL DISPATCH</span><h3>Assign a driver</h3></div><Truck size={20}/></div><label>Pending delivery<select required value={form.delivery_id} onChange={e=>setForm({...form,delivery_id:e.target.value})}><option value="">Select delivery</option>{deliveries.map(d=><option value={d.id} key={d.id}>#{d.id} · {d.pickup_address} → {d.dropoff_address}</option>)}</select></label><label>Online driver<select required value={form.driver_id} onChange={e=>setForm({...form,driver_id:e.target.value})}><option value="">Select driver</option>{drivers.map(d=><option value={d.id} key={d.id}>{d.name} · {d.vehicle_number}</option>)}</select></label><button className="primary wide">Create assignment <ArrowRight size={17}/></button>{message && <div className={message.includes("success") ? "success" : "error"}>{message}</div>}</form><section className="panel"><div className="panel-head"><div><span className="eyebrow">RECENT</span><h3>Assignment history</h3></div><Activity size={20}/></div><div className="assignment-list">{items.slice(0,8).map(a=><div className="assignment" key={a.id}><div className="assignment-icon"><Truck size={17}/></div><div><b>#{a.delivery_id} · {a.driver_name}</b><span>{a.pickup} → {a.dropoff}</span></div><span className={`badge ${a.status}`}>{statusLabel(a.status)}</span></div>)}</div></section></div></Page>
}

function DeliveryDetail({ user }) {
  const { id } = useParams()
  const [data,setData]=useState(null)
  const [error,setError]=useState("")
  async function load(){try{setData(await request(`/deliveries/${id}`));setError("")}catch(e){setError(e.message)}}
  useEffect(()=>{load()},[id])
  async function status(next){try{await request(`/deliveries/${id}/status`,{method:"PATCH",body:JSON.stringify({action:next})});load()}catch(e){setError(e.message)}}
  if(error) return <Page title="Delivery details" subtitle=""><div className="error">{error}</div></Page>
  if(!data) return <Page title="Loading..." subtitle="Fetching delivery details."/>
  const d=data.delivery
  const next = {pending:"assigned",assigned:"accepted",accepted:"pickup_started",pickup_started:"picked_up",picked_up:"in_transit",in_transit:"delivered"}[d.status]
  return <Page title={`Delivery #${d.id}`} subtitle={`${d.pickup_address} → ${d.dropoff_address}`} action={<button className="secondary" onClick={load}><RefreshCw size={16}/> Refresh</button>}><div className="detail-grid"><section className="panel"><div className="route-hero"><div><span className="eyebrow">CURRENT STATUS</span><h3>{statusLabel(d.status)}</h3><span className={`badge ${d.priority}`}>{d.priority} priority</span></div><div className="route-line"><div><MapPin/><span>Pickup</span><b>{d.pickup_address}</b></div><div className="line"/><div><Navigation/><span>Drop-off</span><b>{d.dropoff_address}</b></div></div></div>{user.role !== "customer" && next && <button className="primary" onClick={()=>status(next)}>Move to {statusLabel(next)} <ArrowRight size={17}/></button>}</section><section className="panel"><div className="panel-head"><div><span className="eyebrow">ASSIGNMENT</span><h3>Driver</h3></div><Truck size={20}/></div>{data.driver ? <div className="assigned-driver"><div className="avatar large-avatar">{data.driver.name[0]}</div><div><b>{data.driver.name}</b><span>{data.driver.vehicle_type} · {data.driver.vehicle_number}</span><span>{data.driver.status}</span></div></div> : <div className="empty small">No driver assigned yet.</div>}</section><section className="panel timeline-panel"><div className="panel-head"><div><span className="eyebrow">AUDIT TRAIL</span><h3>Delivery timeline</h3></div><Clock3 size={20}/></div><div className="timeline">{data.events.map(e=><div className="timeline-item" key={e.id}><span className="timeline-dot"/><div><b>{statusLabel(e.status)}</b><span>{e.note}</span><small>{new Date(e.created_at).toLocaleString()}</small></div></div>)}</div></section><section className="panel"><div className="panel-head"><div><span className="eyebrow">ROUTE</span><h3>Location data</h3></div><MapPin size={20}/></div><div className="coordinate-card"><div><span>Pickup</span><b>{d.pickup_latitude.toFixed(4)}, {d.pickup_longitude.toFixed(4)}</b></div><ArrowRight/><div><span>Drop-off</span><b>{d.dropoff_latitude.toFixed(4)}, {d.dropoff_longitude.toFixed(4)}</b></div></div></section></div></Page>
}

export default function App() {
  const [user,setUser]=useState(null)
  const [checking,setChecking]=useState(true)
  async function loadUser(){try{setUser(await request("/auth/me"))}catch{localStorage.removeItem("routesync_token");setUser(null)}finally{setChecking(false)}}
  useEffect(()=>{loadUser()},[])
  function logout(){localStorage.removeItem("routesync_token");setUser(null)}
  if(checking) return <div className="loading-screen">Loading RouteSync...</div>
  if(!user) return <Login onLogin={loadUser}/>
  return <Shell user={user} onLogout={logout}><Routes><Route path="/" element={<Dashboard user={user}/>}/><Route path="/deliveries" element={<Deliveries user={user}/>}/><Route path="/deliveries/:id" element={<DeliveryDetail user={user}/>}/>{user.role !== "customer" && <Route path="/drivers" element={<Drivers/>}/>} {user.role === "admin" && <Route path="/assignments" element={<Assignments/>}/>}<Route path="*" element={<Navigate to="/" replace/>}/></Routes></Shell>
}
